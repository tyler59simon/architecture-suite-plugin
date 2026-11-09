"""Record skill/package/install evidence in reports/ from checks actually executed here.

Builds the host archives, installs every host (project and user scope) into a temporary
directory, verifies the ten skills and runtime are present, and writes
reports/skill-manifest.json, host-packages.json and installation.json.
"""

import hashlib
import json
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
sys.path.insert(0, str(SKILLS / "architecture-suite-runtime/scripts"))
from architecture_suite.distribution import (  # noqa: E402
    AGENT_BEHAVIOUR, HOSTS, RUNTIME_NAME, VERSION, install_host, package_hosts, skill_names,
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree(folder):
    return {
        p.relative_to(folder).as_posix(): digest(p)
        for p in sorted(Path(folder).rglob("*"))
        if p.is_file()
        and not any(x in {"__pycache__", "build", "dist", ".venv"} or x.endswith(".egg-info") for x in p.parts)
        and p.suffix != ".pyc"
    }


def main():
    names = skill_names(SKILLS)
    (ROOT / "reports/skill-manifest.json").write_text(
        json.dumps(
            {
                "version": VERSION,
                "skills": names,
                "runtime": RUNTIME_NAME,
                "files": {n: tree(SKILLS / n) for n in [*names, RUNTIME_NAME]},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    out = ROOT / "dist/hosts"
    out.mkdir(parents=True, exist_ok=True)
    package_hosts(SKILLS, out)
    packages = {}
    for host in HOSTS:
        archive = out / f"{host}.zip"
        with zipfile.ZipFile(archive) as z:
            members = z.namelist()
            prefix = "skills" if host in {"claude", "factory"} else HOSTS[host]
            assert all(f"{prefix}/{n}/SKILL.md" in members for n in names), host
            assert any(m.startswith(f"{prefix}/{RUNTIME_NAME}/scripts/") for m in members)
            plugin = [m for m in members if m.endswith("plugin.json")]
        packages[f"{host}.zip"] = {
            "files": len(members),
            "skills": names,
            "plugin_manifest": plugin[0] if plugin else None,
            "status": AGENT_BEHAVIOUR[host],
            "sha256": digest(archive),
        }
    (ROOT / "reports/host-packages.json").write_text(json.dumps(packages, indent=2), encoding="utf-8")
    installs = {}
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        for host in HOSTS:
            for scope in ("project", "user"):
                base = temp / host / scope
                folder = install_host(
                    SKILLS, host, scope, project=base if scope == "project" else None,
                    home=base if scope == "user" else None,
                )
                assert sorted(skill_names(folder)) == names, (host, scope)
                installed = tree(folder / RUNTIME_NAME)
                # Installs add the repository's LICENSE/NOTICE to the runtime folder.
                assert {"LICENSE", "NOTICE"} <= set(installed), (host, scope)
                for legal in ("LICENSE", "NOTICE"):
                    installed.pop(legal)
                assert installed == tree(SKILLS / RUNTIME_NAME), (host, scope)
                installs[f"{host}/{scope}"] = {
                    "skills": len(names),
                    "runtime_matches_source": True,
                    "relative_folder": folder.relative_to(base).as_posix(),
                }
    (ROOT / "reports/installation.json").write_text(
        json.dumps(
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "version": VERSION,
                "method": "tools/record_packages.py: install into temporary directories; no live agent session",
                "installs": installs,
                "agent_behavior": AGENT_BEHAVIOUR,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("recorded", len(packages), "packages and", len(installs), "installs")


if __name__ == "__main__":
    main()
