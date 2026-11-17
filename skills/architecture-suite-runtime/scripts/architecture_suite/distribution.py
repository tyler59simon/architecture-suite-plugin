"""Deterministic multi-host packages, with no authenticated agent claims."""

from pathlib import Path
import shutil
import tempfile
from .safety import (
    canonical_output_directory,
    require_write_authorization,
    atomic_output_directory,
)

RUNTIME_NAME = "architecture-suite-runtime"
VERSION = "1.3.0"
PLUGIN_NAME = "architecture-suite"
DESCRIPTION = (
    "Offline evidence-backed C4 architecture diagrams: architecture-plan, c4-diagrams, "
    "reverse-engineer-c4, c4-system, c4-container, c4-component, c4-code, "
    "c4-overview, c4-aws and c4-gcp"
)
LICENSE = "Apache-2.0"
AUTHOR = {"name": "Tyler Simon"}
# Public GitHub repository URL, e.g. "https://github.com/<owner>/architecture-suite".
# homepage/repository are omitted from manifests while this is empty.
REPOSITORY = "https://github.com/tyler59simon/architecture-suite-plugin"
KEYWORDS = ["c4", "architecture", "diagrams", "planning", "drawio", "visio", "mermaid", "plantuml", "aws", "gcp", "offline"]
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
        # The stage starts empty so files dropped from the new version do not survive.
        with atomic_output_directory(target, seed_existing=False) as stage:
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
