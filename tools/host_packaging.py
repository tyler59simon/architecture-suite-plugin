"""Build the host archives and the release plugin tree. Maintainer tooling, not shipped.

Used by package_hosts.py, record_packages.py and the tests.
"""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/architecture-suite-runtime/scripts"))
from architecture_suite.distribution import (  # noqa: E402
    AGENT_BEHAVIOUR,
    HOSTS,
    NEWLINE,
    RUNTIME_NAME,
    _included,
    legal_files,
    marketplace_manifest,
    plugin_manifest,
    skill_names,
)


def untracked_skill_files(root):
    """Files under skills/ that git does not track and does not ignore.

    Returns [] outside a git checkout or when git is missing, so packaging still works from a
    source archive.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "skills/"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    return result.stdout.splitlines() if result.returncode == 0 else []


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
                legal_paths = [f"{prefix}/{RUNTIME_NAME}/{legal.name}"]
                if host in {"claude", "factory"}:
                    legal_paths.append(legal.name)
                for name in legal_paths:
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
