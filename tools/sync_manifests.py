"""Write the repository-root plugin manifests from the single version source (distribution.VERSION).

    python tools/sync_manifests.py           # write the manifests
    python tools/sync_manifests.py --check   # exit 1 listing manifests that differ; write nothing
"""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/architecture-suite-runtime/scripts"))
from architecture_suite.distribution import marketplace_manifest, plugin_manifest  # noqa: E402


def outputs(root=ROOT):
    """Return {path: bytes} for each manifest."""
    return {
        root / directory / name: (json.dumps(data, indent=2) + "\n").encode("utf-8")
        for directory, name, data in (
            (".claude-plugin", "plugin.json", plugin_manifest("claude")),
            (".claude-plugin", "marketplace.json", marketplace_manifest()),
            (".factory-plugin", "plugin.json", plugin_manifest("factory")),
        )
    }


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if files differ; write nothing")
    args = parser.parse_args(argv)
    files = outputs(root)
    if args.check:
        differing = [
            path.relative_to(root).as_posix()
            for path, data in files.items()
            if not path.is_file() or path.read_bytes() != data
        ]
        for path in differing:
            print("differs:", path, file=sys.stderr)
        return 1 if differing else 0
    for path, data in files.items():
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
