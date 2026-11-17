"""Rebuild assets/manifest.json (SHA-256 of every bundled runtime asset). Offline.

    python tools/build_manifest.py           # rewrite the manifest
    python tools/build_manifest.py --check   # exit 1 if it differs from the assets; write nothing

Run after intentionally editing a bundled asset (schemas, catalogues, license notes).
Review the diff: the manifest is what `doctor` and every render verify against.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ASSETS = Path(__file__).resolve().parents[1] / (
    "skills/architecture-suite-runtime/scripts/architecture_suite/assets"
)


def manifest_bytes(assets=ASSETS):
    # Sort by the POSIX string: Path ordering differs between Windows and Linux.
    paths = sorted(
        (p.relative_to(assets).as_posix(), p)
        for p in assets.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    )
    files = {name: hashlib.sha256(p.read_bytes()).hexdigest() for name, p in paths}
    return json.dumps(files, indent=2).encode(), len(files)


def main(argv=None, assets=ASSETS):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if differs; write nothing")
    args = parser.parse_args(argv)
    data, count = manifest_bytes(assets)
    target = assets / "manifest.json"
    if args.check:
        if target.is_file() and target.read_bytes() == data:
            return 0
        print("differs:", target.as_posix(), file=sys.stderr)
        return 1
    target.write_bytes(data)
    print(f"{count} assets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
