"""Deterministic multi-host packages, with no authenticated agent claims."""

from pathlib import Path
import shutil
import tempfile
import zipfile
import json
from .safety import (
    canonical_output_directory,
    require_write_authorization,
    atomic_output_directory,
)

RUNTIME_NAME = "architecture-suite-runtime"
VERSION = "1.0.0"
PLUGIN_NAME = "architecture-suite"
DESCRIPTION = (
    "Offline evidence-backed C4 architecture diagrams: c4-diagrams, "
    "reverse-engineer-c4, c4-system, c4-container, c4-component, c4-code, "
    "c4-overview, c4-aws and c4-gcp"
)
LICENSE = "Apache-2.0"
AUTHOR = {"name": "Tyler Simon"}
# Public GitHub repository URL, e.g. "https://github.com/<owner>/architecture-suite".
# homepage/repository are omitted from manifests while this is empty.
REPOSITORY = "https://github.com/tyler59simon/architecture-suite-plugin"
KEYWORDS = ["c4", "architecture", "diagrams", "drawio", "mermaid", "aws", "gcp", "offline"]
# Repository-root legal files shipped with every package and install.
LEGAL_FILES = ("LICENSE", "NOTICE")
NEWLINE = chr(10)
EXCLUDED_PARTS = {"build", "dist", "__pycache__", ".venv"}
# What is known about agent behaviour per host; only Claude Code has an eval suite (evals/).
AGENT_BEHAVIOUR = {
    "claude": "package-validated; agent behaviour evaluated with claude plugin eval (evals/)",
    "factory": "package-validated; agent behaviour not separately evaluated",
    "codex": "package-validated; agent behaviour not separately evaluated",
    "copilot": "package-validated; agent behaviour not separately evaluated",
}

HOSTS = {
    "codex": ".agents/skills",
    "claude": ".claude/skills",
    "copilot": ".github/skills",
    "factory": ".factory/skills",
}


def skill_names(skills):
    """Skill folders (those with SKILL.md); the runtime folder is shared, not a skill."""
    return sorted(
        p.name for p in Path(skills).iterdir() if (p / "SKILL.md").is_file()
    )


def plugin_manifest(host, version=VERSION):
    manifest = {
        "name": PLUGIN_NAME,
        "version": version,
        "description": DESCRIPTION,
        "author": AUTHOR,
        "license": LICENSE,
        "keywords": KEYWORDS,
    }
    if REPOSITORY:
        manifest["homepage"] = REPOSITORY
        manifest["repository"] = REPOSITORY
    return manifest


def marketplace_manifest(version=VERSION):
    return {
        # Short on purpose: the name is part of the Windows plugin cache path, and official
        # AWS icon file names already come close to the 260-character MAX_PATH limit.
        "name": PLUGIN_NAME,
        "description": "Offline, evidence-backed C4 architecture diagram skills",
        "owner": AUTHOR,
        "plugins": [
            {
                "name": PLUGIN_NAME,
                "source": ".",
                "version": version,
                "description": DESCRIPTION,
            }
        ],
    }


def _included(path):
    """Filter a path relative to its skill folder."""
    return (
        not any(
            p in EXCLUDED_PARTS or p.endswith(".egg-info") for p in path.parts
        )
        and path.suffix != ".pyc"
    )


def legal_files(skills):
    """LICENSE/NOTICE from the repository root next to the skills folder."""
    root = Path(skills).resolve().parent
    return [root / name for name in LEGAL_FILES if (root / name).is_file()]


def package_hosts(skills, output, hosts=None):
    """Package every skill plus the shared runtime for each host."""
    skills = Path(skills)
    output = Path(output)
    names = skill_names(skills)
    if not names:
        raise ValueError("No skills found")
    folders = [*names, *([RUNTIME_NAME] if (skills / RUNTIME_NAME).is_dir() else [])]
    for host in hosts or HOSTS:
        if host not in HOSTS:
            raise ValueError("Unknown host")
        prefix = "skills" if host in {"claude", "factory"} else HOSTS[host]
        with zipfile.ZipFile(
            output / (host + ".zip"), "w", compression=zipfile.ZIP_DEFLATED
        ) as bundle:
            for folder in folders:
                root = skills / folder
                for path in sorted(root.rglob("*")):
                    rel = path.relative_to(root)
                    if not path.is_file() or not _included(rel):
                        continue
                    info = zipfile.ZipInfo(
                        f"{prefix}/{folder}/{rel.as_posix()}",
                        date_time=(2026, 1, 1, 0, 0, 0),
                    )
                    info.compress_type = zipfile.ZIP_DEFLATED
                    bundle.writestr(info, path.read_bytes())
            for legal in legal_files(skills):
                # In the runtime folder for every layout; also at the root of plugin layouts.
                names = [f"{prefix}/{RUNTIME_NAME}/{legal.name}"]
                if host in {"claude", "factory"}:
                    names.append(legal.name)
                for name in names:
                    info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    bundle.writestr(info, legal.read_bytes())
            if host in {"claude", "factory"}:
                directory = ".claude-plugin" if host == "claude" else ".factory-plugin"
                info = zipfile.ZipInfo(
                    directory + "/plugin.json", date_time=(2026, 1, 1, 0, 0, 0)
                )
                bundle.writestr(
                    info, json.dumps(plugin_manifest(host), sort_keys=True, indent=2)
                )
            info = zipfile.ZipInfo("VALIDATION.json", date_time=(2026, 1, 1, 0, 0, 0))
            bundle.writestr(
                info,
                json.dumps(
                    {
                        "host": host,
                        "status": AGENT_BEHAVIOUR[host],
                        "skills": names,
                        "runtime": f"{prefix}/{RUNTIME_NAME}",
                    }
                ),
            )


def write_plugin_tree(skills, target):
    """Write the slim, self-contained marketplace + plugin published on the architecture-suite-<version> and latest branches.

    Holds only what a user needs: the skills, the shared runtime, LICENSE/NOTICE, README,
    CHANGELOG and the Claude/Factory manifests. Users add it with `/plugin marketplace add <owner>/<repo>#latest` (or a version branch).
    """
    skills = Path(skills)
    target = Path(target)
    if target.exists():
        shutil.rmtree(target)
    names = skill_names(skills)
    if not names:
        raise ValueError("No skills found")
    for folder in [*names, *([RUNTIME_NAME] if (skills / RUNTIME_NAME).is_dir() else [])]:
        for path in sorted((skills / folder).rglob("*")):
            rel = path.relative_to(skills / folder)
            if path.is_file() and _included(rel):
                destination = target / "skills" / folder / rel
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
    for legal in legal_files(skills):
        shutil.copyfile(legal, target / legal.name)
    # README and CHANGELOG for users; .gitattributes keeps checksummed assets byte-exact when the release
    # branch is cloned on Windows with core.autocrlf=true (as Claude Code's installer does).
    for name in ("README.md", "CHANGELOG.md", ".gitattributes"):
        source = skills.resolve().parent / name
        if source.is_file():
            shutil.copyfile(source, target / name)
    for directory, name, data in (
        (".claude-plugin", "plugin.json", plugin_manifest("claude")),
        (".claude-plugin", "marketplace.json", marketplace_manifest()),
        (".factory-plugin", "plugin.json", plugin_manifest("factory")),
    ):
        (target / directory).mkdir(parents=True, exist_ok=True)
        (target / directory / name).write_bytes(
            (json.dumps(data, indent=2) + NEWLINE).encode("utf-8")
        )
    return target


def install_host(skills, host, scope, project=None, home=None, overwrite=False):
    """Install every skill and the shared runtime as siblings in the host skills folder."""
    if host not in HOSTS or scope not in {"user", "project"}:
        raise ValueError("Invalid host/scope")
    if scope == "project" and project is None:
        raise ValueError("Project scope requires --project")
    skills = Path(skills)
    base = Path(project) if scope == "project" else Path(home or Path.home())
    folder = (
        HOSTS[host]
        if scope == "project"
        else {
            "codex": ".codex/skills",
            "claude": ".claude/skills",
            "copilot": ".copilot/skills",
            "factory": ".factory/skills",
        }[host]
    )
    names = skill_names(skills)
    targets = []
    for name in [*names, *([RUNTIME_NAME] if (skills / RUNTIME_NAME).is_dir() else [])]:
        target = canonical_output_directory(base / folder / name)
        require_write_authorization(target, True, overwrite)
        targets.append((name, target))
    for name, target in targets:
        # Backups stay outside any directory scanned for skills.
        if target.exists():
            backup = base / ".architecture-suite-backups" / host
            backup.mkdir(parents=True, exist_ok=True)
            destination = Path(tempfile.mkdtemp(dir=backup)) / name
            shutil.copytree(target, destination)
        with atomic_output_directory(target) as stage:
            shutil.copytree(
                skills / name,
                stage,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(
                    "__pycache__", "*.pyc", "*.egg-info", "build", "dist", ".venv"
                ),
            )
            if name == RUNTIME_NAME:
                for legal in legal_files(skills):
                    shutil.copyfile(legal, stage / legal.name)
    return base / folder
