"""Set the package version in every place that records it, then regenerate the manifests.

    python tools/bump_version.py 1.3.0             # rewrite the files, run sync_manifests.py
    python tools/bump_version.py 1.3.0 --dry-run   # list the files that would change

Add the `## X.Y.Z` heading to CHANGELOG.md yourself; a test requires it.
"""

import argparse
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = "skills/architecture-suite-runtime/scripts"
VERSION_FORMAT = re.compile(r"\d+\.\d+\.\d+")

# (file, pattern with one group around the old version, replacement count)
LOCATIONS = (
    (f"{RUNTIME}/architecture_suite/__init__.py", r'(__version__ = ")({old})(")', 1),
    (f"{RUNTIME}/architecture_suite/distribution.py", r'(VERSION = ")({old})(")', 1),
    ("pyproject.toml", r'(?m)(^version = ")({old})(")', 1),
    (f"{RUNTIME}/pyproject.toml", r'(?m)(^version = ")({old})(")', 1),
    ("package.json", r'("version": ")({old})(")', 1),
    ("package-lock.json", r'("version": ")({old})(")', 2),
    ("README.md", r"(architecture-suite-)({old})(\b)", 1),
)


def current_version(root=ROOT):
    text = (root / LOCATIONS[0][0]).read_text(encoding="utf-8")
    return re.search(r'__version__ = "([^"]+)"', text).group(1)


def bump(new, root=ROOT, write=True):
    """Rewrite every version location; return the relative paths that changed."""
    old = current_version(root)
    changed = []
    for relative, pattern, count in LOCATIONS:
        path = root / relative
        text = path.read_bytes().decode("utf-8")
        updated, found = re.subn(
            pattern.replace("{old}", re.escape(old)), rf"\g<1>{new}\g<3>", text, count=count
        )
        if found != count:
            raise SystemExit(f"{relative}: expected {count} occurrence(s) of {old}, found {found}")
        if updated != text:
            changed.append(relative)
            if write:
                path.write_bytes(updated.encode("utf-8"))
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="new version, X.Y.Z")
    parser.add_argument("--dry-run", action="store_true", help="list the files; write nothing")
    args = parser.parse_args(argv)
    if not VERSION_FORMAT.fullmatch(args.version):
        raise SystemExit(f"version must look like X.Y.Z, got {args.version!r}")
    changed = bump(args.version, write=not args.dry_run)
    for relative in changed:
        print(("would change " if args.dry_run else "changed ") + relative)
    if args.dry_run:
        return 0
    result = subprocess.run([sys.executable, str(ROOT / "tools/sync_manifests.py")], check=False)
    print(f"Now add a '## {args.version}' heading to CHANGELOG.md.")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
