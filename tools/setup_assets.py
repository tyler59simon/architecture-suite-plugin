"""Authorized setup downloads. Generation never calls this module."""

import hashlib
import io
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/architecture-suite-runtime/scripts/architecture_suite/assets"
AWS_URL = "https://d1.awsstatic.com/onedam/marketing-channels/website/public/shared/architecture-icon-release/Icon-package_07312026.5846e92413caa21490223536cc97f1269e44fa92.zip"


def download(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / "licenses").mkdir(exist_ok=True)
    for name in ("elk.bundled.js", "LICENSE.md"):
        source = (
            ROOT / "node_modules/elkjs" / ("lib" if name.endswith("js") else "") / name
        )
        shutil.copyfile(
            source,
            ASSETS / (name if name.endswith("js") else "licenses/ELK-LICENSE.md"),
        )
    # Pinned upstream font; Apache-2.0 permits embedding and redistribution.
    font_url = "https://raw.githubusercontent.com/googlefonts/roboto-2/v2.138/src/hinted/Roboto-Regular.ttf"
    (ASSETS / "font.ttf").write_bytes(download(font_url))
    (ASSETS / "licenses/FONT-LICENSE.txt").write_bytes(
        download(
            "https://raw.githubusercontent.com/googlefonts/roboto-2/v2.138/LICENSE"
        )
    )
    archive = download(AWS_URL)
    aws_dir = ASSETS / "aws"
    aws_dir.mkdir(exist_ok=True)
    catalog = {}
    for stale in aws_dir.glob("*.svg"):
        stale.unlink()
    seen = set()
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        for name in sorted(bundle.namelist()):
            # Keep all unique official SVGs, excluding macOS resource forks.
            if (
                name.endswith(".svg")
                and not name.startswith("__MACOSX/")
                and not Path(name).name.startswith("._")
            ):
                data = bundle.read(name)
                digest = hashlib.sha256(data).hexdigest()
                if digest in seen:
                    continue
                seen.add(digest)
                key = Path(name).stem.removesuffix("_64").removeprefix("Arch_")
                if key in catalog:
                    key += "-" + digest[:8]
                target = aws_dir / f"{key}.svg"
                target.write_bytes(data)
                catalog[key] = {"file": target.name, "archive_path": name}
    (ASSETS / "aws-catalog.json").write_text(
        json.dumps(catalog, indent=2), encoding="utf-8"
    )
    (ASSETS / "licenses/AWS-USAGE.md").write_text(
        "# AWS Architecture Icons\n\nOfficial package, released 2026-07-31.\nSource: "
        + AWS_URL
        + "\n\nAWS permits customers and partners to use the assets to create architecture diagrams. These are AWS trademarks, not covered by the runtime license. See https://aws.amazon.com/architecture/icons/ and https://aws.amazon.com/trademark-guidelines/ .\n",
        encoding="utf-8",
    )
    provenance = {
        "elk": {
            "version": "0.9.3",
            "source": "https://registry.npmjs.org/elkjs/-/elkjs-0.9.3.tgz",
            "license": "EPL-2.0",
        },
        "font": {"source": font_url, "license": "Apache-2.0"},
        "aws": {
            "source": AWS_URL,
            "release": "2026-07-31",
            "archive_sha256": hashlib.sha256(archive).hexdigest(),
            "services": len(catalog),
        },
    }
    previous = ASSETS / "provenance.json"
    if previous.exists():  # keep the offline-vendored GCP entry
        provenance.update(
            {
                k: v
                for k, v in json.loads(previous.read_text(encoding="utf-8")).items()
                if k == "gcp"
            }
        )
    previous.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    files = {
        p.relative_to(ASSETS).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(ASSETS.rglob("*"))
        if p.is_file() and p.name != "manifest.json"
    }
    (ASSETS / "manifest.json").write_text(json.dumps(files, indent=2), encoding="utf-8")
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
