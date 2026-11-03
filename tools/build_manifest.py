"""Rebuild assets/manifest.json (SHA-256 of every bundled runtime asset). Offline.

    python tools/build_manifest.py

Run after intentionally editing a bundled asset (schemas, catalogues, license notes).
Review the diff: the manifest is what `doctor` and every render verify against.
"""

import hashlib
import json
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / (
    "skills/architecture-suite-runtime/scripts/architecture_suite/assets"
)


def main():
    files = {
        p.relative_to(ASSETS).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(ASSETS.rglob("*"))
        if p.is_file() and p.name != "manifest.json"
    }
    (ASSETS / "manifest.json").write_bytes(json.dumps(files, indent=2).encode())
    print(f"{len(files)} assets")


if __name__ == "__main__":
    main()
