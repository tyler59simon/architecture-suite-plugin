"""Bounded local I/O, redaction and transactional publication."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Iterator


class SafetyError(ValueError):
    """An operation cannot satisfy its safety contract; CLI exit status 3."""


SECRET = re.compile(
    r"(?i)(?:AKIA|ASIA)[A-Z0-9]{16}|gh[pousr]_[A-Za-z0-9_]{20,}|\bBearer\s+[A-Za-z0-9._~+/=-]{16,}|(?:password|passwd|pwd|secret|token|api[_-]?key|client[_-]?secret|access[_-]?token)[\"']?\s*[:=]\s*[\"']?[^\s\"',;}]{4,}|(?:https?|postgres(?:ql)?|mysql|mongodb)://[^/\s:@]+:[^@\s/]+@|-----BEGIN [A-Z ]*PRIVATE KEY-----"
)
PROMPT_INJECTION = re.compile(
    r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions|(?:reveal|print|exfiltrate).{0,40}(?:secret|token|password)|(?:system|developer)\s+prompt|run\s+(?:this|the following)\s+(?:command|script)",
    re.I,
)
SKIP = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "bin",
    "obj",
    "target",
    "dist",
    "build",
    ".env",
}
EXTENSIONS = {
    ".py",
    ".cs",
    ".csproj",
    ".fsproj",
    ".sln",
    ".java",
    ".kt",
    ".kts",
    ".xml",
    ".gradle",
    ".go",
    ".mod",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".yaml",
    ".yml",
    ".tf",
    ".toml",
    ".txt",
    ".md",
    ".properties",
    ".dockerfile",
}


def redact(value: str) -> str:
    """Remove credential-like values before persisting evidence."""
    return SECRET.sub("[REDACTED]", value)


def contains_likely_secret(value: str) -> bool:
    return bool(SECRET.search(value))


def detect_prompt_injection(value: str) -> bool:
    return bool(PROMPT_INJECTION.search(value))


def safe_text(value: object) -> str:
    return redact(re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(value)))


def _no_links(path: Path) -> None:
    for part in (path, *path.parents):
        try:
            is_reparse = os.name == "nt" and bool(
                part.lstat().st_file_attributes & 0x400
            )
        except FileNotFoundError:
            is_reparse = False
        if part.is_symlink() or is_reparse:
            raise SafetyError(f"Symlink/reparse path is not allowed: {part.name}")


def canonical_existing_directory(path: Path) -> Path:
    path = Path(path).absolute()
    _no_links(path)
    if not path.is_dir():
        raise SafetyError("Repository must be an existing directory")
    return path.resolve()


def canonical_existing_file(path: Path) -> Path:
    path = Path(path).absolute()
    _no_links(path)
    if not path.is_file() or path.stat().st_size > 20_000_000:
        raise SafetyError("Input must be an existing file under 20 MB")
    return path.resolve()


def canonical_output_directory(path: Path) -> Path:
    path = Path(path).absolute()
    _no_links(path)
    resolved = path.resolve()
    if resolved in {Path(resolved.anchor), Path.home().resolve(), Path.cwd().resolve()}:
        raise SafetyError("Choose a dedicated output directory")
    if resolved.exists() and not resolved.is_dir():
        raise SafetyError("Output directory is a file")
    if resolved.exists():
        for item in resolved.rglob("*"):
            _no_links(item)
    return resolved


def contained_path(root: Path, relative: str) -> Path:
    path = root / relative
    if (
        Path(relative).is_absolute()
        or ".." in Path(relative).parts
        or path.resolve() == root.resolve()
        or not path.resolve().is_relative_to(root.resolve())
    ):
        raise SafetyError("Artifact path escapes output root")
    _no_links(path)
    return path


def require_write_authorization(
    output: Path, confirm_write: bool, confirm_overwrite: bool
) -> None:
    if not confirm_write:
        raise SafetyError("Writing requires --confirm-write; inspect --dry-run first")
    if (
        output.exists()
        and (output.is_file() or any(output.iterdir()))
        and not confirm_overwrite
    ):
        raise SafetyError("Existing output requires --confirm-overwrite")


OUTPUT_MANIFEST = ".architecture-suite-manifest.json"
OUTPUT_MANIFEST_VERSION = "architecture-output-manifest/v1"
_DIGEST = re.compile(r"[0-9a-f]{64}")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_output_manifest(root: Path) -> dict:
    """Owner sections of a previous publication; empty when there is no manifest."""
    path = root / OUTPUT_MANIFEST
    if not path.exists():
        return {}
    _no_links(path)
    malformed = SafetyError(
        f"Malformed {OUTPUT_MANIFEST}; remove it or choose another output directory"
    )
    if not path.is_file() or path.stat().st_size > 5_000_000:
        raise malformed
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise malformed from exc
    owners = data.get("owners") if isinstance(data, dict) else None
    if data.get("schema_version") != OUTPUT_MANIFEST_VERSION or not isinstance(owners, dict):
        raise malformed
    for section in owners.values():
        files = section.get("files") if isinstance(section, dict) else None
        if not isinstance(files, dict):
            raise malformed
        for relative, digest in files.items():
            if (
                not isinstance(relative, str)
                or relative == OUTPUT_MANIFEST
                or not isinstance(digest, str)
                or not _DIGEST.fullmatch(digest)
            ):
                raise malformed
            contained_path(root, relative)  # no escapes, absolute paths or links
    return owners


def ownership_changes(output: Path, owner: str, files) -> dict:
    """Files `owner` generated last time that this run no longer produces.

    Unchanged ones are removed on publication; edited ones are kept and reported as
    conflicts. Files no manifest lists are never touched.
    """
    output = Path(output)
    if not output.is_dir():
        return {"remove": [], "conflicts": []}
    produced = set(files)
    remove, conflicts = [], []
    previous = _read_output_manifest(output).get(owner, {}).get("files", {})
    for relative, digest in sorted(previous.items()):
        path = contained_path(output, relative)
        if relative in produced or not path.is_file():
            continue
        (remove if _digest(path) == digest else conflicts).append(relative)
    return {"remove": remove, "conflicts": conflicts}


def _claim_outputs(stage: Path, owner: str, command: str, files) -> None:
    """Retire this owner's stale outputs in the stage and record what it produced."""
    from . import __version__

    owners = _read_output_manifest(stage)
    for relative in ownership_changes(stage, owner, files)["remove"]:
        path = contained_path(stage, relative)
        path.unlink()
        parent = path.parent
        while parent != stage and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    produced = {}
    for relative in files:
        if relative == OUTPUT_MANIFEST:
            continue
        path = contained_path(stage, relative)
        if not path.is_file():
            raise SafetyError(f"Declared output was not written: {relative}")
        produced[relative] = _digest(path)
    for section in owners.values():  # a file belongs to the owner that last wrote it
        for relative in produced:
            section["files"].pop(relative, None)
    owners[owner] = {"command": command, "tool_version": __version__, "files": produced}
    manifest = {"schema_version": OUTPUT_MANIFEST_VERSION, "owners": owners}
    (stage / OUTPUT_MANIFEST).write_bytes(
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    )


@contextmanager
def atomic_output_directory(
    output: Path, *, owner: str | None = None, command: str | None = None, files=()
) -> Iterator[Path]:
    """Stage all artifacts, preserve unrelated files, roll back if promotion fails.

    With an `owner`, the declared `files` are recorded in the output manifest and that
    owner's previously generated files that are no longer produced are retired.
    """
    output = canonical_output_directory(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".architecture-stage-", dir=output.parent))
    backup = stage.with_name(stage.name + "-backup")
    try:
        if output.exists():
            shutil.copytree(output, stage, dirs_exist_ok=True)
        yield stage
        if owner:
            _claim_outputs(stage, owner, command or owner, files)
        canonical_output_directory(output)
        if output.exists():
            output.rename(backup)
        try:
            stage.rename(output)
        except OSError:
            if backup.exists():
                backup.rename(output)
            raise
    finally:
        for temp in (stage, backup):
            if (
                temp.exists()
                and temp.parent.resolve() == output.parent.resolve()
                and temp.name.startswith(".architecture-stage-")
            ):
                shutil.rmtree(temp)


def run_bounded(
    command: list[str],
    *,
    input_text: str = "",
    timeout_seconds: float = 120.0,
    max_output_bytes: int = 20_000_000,
) -> str:
    if timeout_seconds <= 0 or max_output_bytes <= 0:
        raise SafetyError("Process limits must be positive")
    process = None
    with (
        tempfile.TemporaryFile() as stdin,
        tempfile.TemporaryFile() as stdout,
        tempfile.TemporaryFile() as stderr,
    ):
        stdin.write(input_text.encode("utf-8"))
        stdin.seek(0)
        start = time.monotonic()
        try:
            process = subprocess.Popen(
                command, stdin=stdin, stdout=stdout, stderr=stderr, shell=False
            )
            while True:
                if (
                    os.fstat(stdout.fileno()).st_size
                    + os.fstat(stderr.fileno()).st_size
                    > max_output_bytes
                ):
                    raise SafetyError("Subprocess output limit exceeded")
                remaining = timeout_seconds - (time.monotonic() - start)
                if remaining <= 0:
                    raise SafetyError(f"Local dependency timed out: {command[0]}")
                try:
                    process.wait(timeout=min(remaining, 0.05))
                    break
                except subprocess.TimeoutExpired:
                    continue
            if (
                os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size
                > max_output_bytes
            ):
                raise SafetyError("Subprocess output limit exceeded")
            stdout.seek(0)
            stderr.seek(0)
            if process.returncode:
                raise SafetyError(
                    f"Local subprocess failed: {safe_text(stderr.read(400).decode('utf-8', errors='replace'))}"
                )
            return stdout.read().decode("utf-8")
        except OSError as exc:
            raise SafetyError(f"Local dependency missing: {command[0]}") from exc
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()


class _RedactedText(str):
    """Redacted file text; `source` keeps the original for in-memory parsing only.

    Redaction can break syntax, so parsers read `source` and redact what they record.
    """

    def __new__(cls, source: str):
        text = super().__new__(cls, redact(source))
        text.source = source
        return text


@dataclass
class ScannedFile:
    path: Path
    relative_path: str
    text: str
    size: int


@dataclass
class ScanResult:
    files: tuple[ScannedFile, ...] = ()
    skipped_files: int = 0
    skipped_bytes: int = 0
    timed_out: bool = False
    prompt_injection_paths: tuple[str, ...] = ()
    skipped: list[str] = field(default_factory=list)
    bytes_read: int = 0
    truncated: bool = False

    @property
    def texts(self) -> dict[str, str]:
        return {file.relative_path: file.text for file in self.files}


def scan_repository(
    root: Path,
    *,
    max_files: int = 2_000,
    max_file_bytes: int = 1_000_000,
    max_total_bytes: int = 50_000_000,
    timeout_seconds: float = 45.0,
) -> ScanResult:
    root = canonical_existing_directory(root)
    if min(max_files, max_file_bytes, max_total_bytes, timeout_seconds) <= 0:
        raise SafetyError("Scan limits must be positive")
    result = ScanResult()
    start = time.monotonic()
    for directory, folders, files in os.walk(root, followlinks=False):
        allowed_folders = []
        for name in sorted(folders):
            if name in SKIP:
                continue
            try:
                _no_links(Path(directory) / name)
                allowed_folders.append(name)
            except SafetyError:
                result.skipped.append(
                    f"{(Path(directory) / name).relative_to(root).as_posix()}: symlink/reparse directory"
                )
        folders[:] = allowed_folders
        for name in sorted(files):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if time.monotonic() - start > timeout_seconds:
                result.timed_out = True
                result.truncated = True
                return result
            if len(result.files) >= max_files:
                result.truncated = True
                return result
            if name.startswith(".env") or (
                path.suffix.lower() not in EXTENSIONS
                and name not in {"Dockerfile", "go.mod"}
            ):
                continue
            try:
                _no_links(path)
                size = path.stat().st_size
                if size > max_file_bytes:
                    result.skipped_files += 1
                    result.skipped_bytes += size
                    result.skipped.append(f"{relative}: file size limit")
                    continue
                if result.bytes_read + size > max_total_bytes:
                    result.truncated = True
                    return result
                data = path.read_bytes()
                result.bytes_read += len(data)
                text = data.decode("utf-8-sig")
                if detect_prompt_injection(text):
                    result.prompt_injection_paths += (relative,)
                result.files += (ScannedFile(path, relative, _RedactedText(text), len(data)),)
            except (UnicodeError, OSError, SafetyError):
                result.skipped_files += 1
                result.skipped.append(
                    f"{relative}: unreadable, invalid UTF-8, or symlink"
                )
    return result
