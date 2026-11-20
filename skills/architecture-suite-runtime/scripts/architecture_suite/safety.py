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
import stat
import subprocess
import sys
import tempfile
import time
from typing import Iterator


class SafetyError(ValueError):
    """An operation cannot satisfy its safety contract; CLI exit status 3."""


# `key=value` (config syntax) counts as a credential for any 4+ character value. A
# `key: value` pair counts only when the value is quoted, is a long opaque token (24+)
# or is 8+ characters with a digit somewhere (_DIGIT_VALUE), so type annotations
# (`password: str`) and prose ("session token: Redis-backed cache") do not match.
# Connection URI schemes: masked here and listed by the dependency inventory.
URI_SCHEMES = r"https?|postgres(?:ql)?|mysql|mongodb|rediss?|amqps?"
# A URI password ends at the last `@` before `/`, whitespace, `?`, `#` or an unescaped `"`,
# so a credentialed URL in compact JSON never runs into the next field. When that finds no
# `@`, a password that is empty or contains `/` (up to 256 characters, to keep matching
# linear) ends at the last `@` before whitespace, `?`, `#` or an unescaped `"`.
_KEYS = r"(?:password|passwd|pwd|secret|token|api[_-]?key|client[_-]?secret|access[_-]?token)[\"']?\s*"
_TOKENS = (
    r"(?i)(?:AKIA|ASIA)[A-Z0-9]{16}|gh[pousr]_[A-Za-z0-9_]{20,}|\bBearer\s+[A-Za-z0-9._~+/=-]{16,}"
    r"|" + _KEYS + r"(?:=\s*[\"']?[^\s\"',;}]{4,}"
    r"|:\s*(?:[\"'][^\s\"',;}]{4,}|[A-Za-z0-9_+/=.-]{24,}))"
)
# A digit-bearing `key: value` is found by its own scan: the value is consumed whole and
# checked for a digit afterwards. A lookahead for the digit rescanned the value at every
# `token:` it held (quadratic on repeated `token:` text), and a combined match hid any
# credentialed URI that started inside the value.
_DIGIT_VALUE = re.compile(r"(?i)" + _KEYS + r":\s*(?P<value>[^\s\"',;})]{8,}+)")
_URI_USER = rf"(?P<scheme>{URI_SCHEMES})://[^/\s:@?#\"]*+:"
_URI_PASSWORD = r"(?:[^\s/?#\"\\]|\\.)+@"
_URI_SLASH_PASSWORD = r"(?:[^\s?#\"\\]|\\.){0,256}@"
_PRIVATE_KEY = r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
SECRET = re.compile(
    rf"{_TOKENS}|{_URI_USER}(?:{_URI_PASSWORD}|{_URI_SLASH_PASSWORD})|{_PRIVATE_KEY}"
)
# Redaction masks the union of both patterns' matches (see _redact).
_SECRET_FIRST = re.compile(rf"{_TOKENS}|{_URI_USER}{_URI_PASSWORD}|{_PRIVATE_KEY}")
_SLASH_URI = re.compile(rf"(?i){_URI_USER}{_URI_SLASH_PASSWORD}")
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


def _mask(match: re.Match[str]) -> str:
    """A credentialed URI keeps its scheme and host; everything else is replaced whole."""
    scheme = match.groupdict().get("scheme")
    return f"{scheme}://[REDACTED]@" if scheme else "[REDACTED]"


def _digit_values(value: str) -> list[re.Match[str]]:
    return [m for m in _DIGIT_VALUE.finditer(value) if re.search(r"\d", m["value"])]


def contains_secret(value: str) -> bool:
    """True when redact would mask something in `value`."""
    return bool(SECRET.search(value) or _digit_values(value))


def _redact(value: str, keep_newlines: bool) -> str:
    """Mask the union of every match: overlapping matches become one masked span, so no
    match can cut another short and leave part of a secret in clear text."""
    first = list(_SECRET_FIRST.finditer(value))
    uri_starts = {m.start() for m in first if m["scheme"]}
    first += _digit_values(value)
    # Where the `/`-stopping URI form matched, its shorter reading of the password stands;
    # the search then resumes one character later so a URI after it gets its own match.
    matches, pos = list(first), 0
    while match := _SLASH_URI.search(value, pos):
        if match.start() in uri_starts:
            pos = match.start() + 1
        else:
            matches.append(match)
            pos = match.end()
    matches.sort(key=lambda m: (m.start(), -m.end()))
    out, pos, i = [], 0, 0
    while i < len(matches):
        lead, end = matches[i], matches[i].end()
        i += 1
        while i < len(matches) and matches[i].start() < end:
            end = max(end, matches[i].end())
            i += 1
        out += [value[pos : lead.start()], _mask(lead)]
        if keep_newlines:
            out.append("\n" * value.count("\n", lead.start(), end))
        pos = end
    out.append(value[pos:])
    return "".join(out)


def redact(value: str) -> str:
    """Remove credential-like values before persisting evidence."""
    return _redact(value, keep_newlines=False)


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


def canonical_existing_directory(path: Path, label: str = "") -> Path:
    path = Path(path).absolute()
    _no_links(path)
    if not path.is_dir():
        # A missing input is an input error (exit 2); links stay a safety error (exit 3).
        raise ValueError(f"{_prefix(label)}no such directory: {path.resolve()}")
    return path.resolve()


def canonical_existing_file(path: Path, label: str = "") -> Path:
    path = Path(path).absolute()
    _no_links(path)
    if not path.is_file():
        raise ValueError(f"{_prefix(label)}no such file: {path.resolve()}")
    if path.stat().st_size > 20_000_000:
        raise ValueError(f"{_prefix(label)}file exceeds 20 MB: {path.resolve()}")
    return path.resolve()


def _prefix(label: str) -> str:
    return f"{label}: " if label else ""


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
    """Compare this run's files with what `owner` generated last time.

    `remove`: files no longer produced and unchanged; removed on publication.
    `conflicts`: files no longer produced but edited since; kept.
    `overwrites_edited`: files this run produces again that were edited since; the
    publication replaces them. Files no manifest lists are never touched.
    """
    output = Path(output)
    if not output.is_dir():
        return {"remove": [], "conflicts": [], "overwrites_edited": []}
    produced = set(files)
    remove, conflicts, overwrites = [], [], []
    previous = _read_output_manifest(output).get(owner, {}).get("files", {})
    for relative, digest in sorted(previous.items()):
        path = contained_path(output, relative)
        if not path.is_file():
            continue
        unchanged = _digest(path) == digest
        if relative in produced:
            if not unchanged:
                overwrites.append(relative)
            continue
        (remove if unchanged else conflicts).append(relative)
    return {"remove": remove, "conflicts": conflicts, "overwrites_edited": overwrites}


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


def _clear_readonly(func, path, _exc) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _remove_temporary(path: Path) -> None:
    """Delete a stage or backup folder, including read-only files (Windows)."""
    try:
        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=_clear_readonly)
        else:  # Python 3.11 has no onexc
            shutil.rmtree(path, onerror=_clear_readonly)
    except OSError as exc:
        # The publication itself already succeeded or failed; never mask that.
        print(
            f"architecture-suite: warning: could not remove temporary folder {path}: {exc}",
            file=sys.stderr,
        )


@contextmanager
def atomic_output_directory(
    output: Path,
    *,
    owner: str | None = None,
    command: str | None = None,
    files=(),
    seed_existing: bool = True,
) -> Iterator[Path]:
    """Stage all artifacts, preserve unrelated files, roll back if promotion fails.

    With an `owner`, the declared `files` are recorded in the output manifest and that
    owner's previously generated files that are no longer produced are retired. With
    `seed_existing=False` the stage starts empty, so the result holds only what the
    caller writes (used to replace an installed copy).
    """
    output = canonical_output_directory(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".architecture-stage-", dir=output.parent))
    backup = stage.with_name(stage.name + "-backup")
    keep_backup = False  # the backup is the only copy when it cannot be restored
    try:
        if seed_existing and output.exists():
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
                try:
                    backup.rename(output)
                except OSError as exc:
                    keep_backup = True
                    raise OSError(
                        f"Could not restore the previous output; it is kept at {backup}"
                    ) from exc
            raise
    finally:
        for temp in (stage, backup):
            if (
                not (temp == backup and keep_backup)
                and temp.exists()
                and temp.parent.resolve() == output.parent.resolve()
                and temp.name.startswith(".architecture-stage-")
            ):
                _remove_temporary(temp)


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


def redact_lines(value: str) -> str:
    """`redact`, but each replacement keeps the newlines it removes (line numbers stay valid)."""
    return _redact(value, keep_newlines=True)


class _RedactedText(str):
    """Redacted file text; `source` keeps the original for in-memory parsing only.

    Redaction can break syntax, so parsers read `source` and redact what they record.
    A redaction keeps the newlines it removes so line numbers match the file.
    """

    def __new__(cls, source: str):
        text = super().__new__(cls, redact_lines(source))
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
                # Open first (non-blocking, so a FIFO swapped in for the file cannot hang the
                # scan), then judge the opened file with fstat instead of a racy path stat().
                fd = os.open(
                    path,
                    os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0),
                )
                try:
                    # The descriptor is closed here, never by the file object, so a failing
                    # os.fdopen cannot leak it or close it twice.
                    with os.fdopen(fd, "rb", closefd=False) as handle:
                        info = os.fstat(fd)
                        if not stat.S_ISREG(info.st_mode):
                            result.skipped_files += 1
                            result.skipped.append(f"{relative}: not a regular file")
                            continue
                        size = info.st_size
                        if size > max_file_bytes:
                            result.skipped_files += 1
                            result.skipped_bytes += size
                            result.skipped.append(f"{relative}: file size limit")
                            continue
                        if result.bytes_read + size > max_total_bytes:
                            result.truncated = True
                            return result
                        # Read one byte past the budget so a file that grew after fstat()
                        # cannot exceed it.
                        budget = min(max_file_bytes, max_total_bytes - result.bytes_read)
                        data = handle.read(budget + 1)
                finally:
                    os.close(fd)
                if len(data) > max_file_bytes:
                    result.skipped_files += 1
                    result.skipped_bytes += len(data)
                    result.skipped.append(f"{relative}: file size limit")
                    continue
                if len(data) > budget:
                    result.truncated = True
                    return result
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
