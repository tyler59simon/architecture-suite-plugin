"""Build local distributable archives and the release-branch plugin tree; never publish them.

    python tools/package_hosts.py

Writes dist/hosts/<host>.zip and dist/plugin/ (the slim marketplace + plugin that the
release workflow pushes to `architecture-suite-<version>` and `latest`).
Fails if a file under skills/ is untracked and not ignored (checked only in a git checkout),
so a stray local file cannot ship.
"""

from pathlib import Path
import sys

from host_packaging import package_hosts, untracked_skill_files, write_plugin_tree

root = Path(__file__).resolve().parents[1]


def main():
    stray = untracked_skill_files(root)
    if stray:
        print("Untracked files under skills/ would ship; add or remove them:", file=sys.stderr)
        for name in stray:
            print("  " + name, file=sys.stderr)
        return 1
    output = root / "dist/hosts"
    output.mkdir(parents=True, exist_ok=True)
    package_hosts(root / "skills", output)
    write_plugin_tree(root / "skills", root / "dist/plugin")
    print(output)
    print(root / "dist/plugin")
    return 0


if __name__ == "__main__":
    sys.exit(main())
