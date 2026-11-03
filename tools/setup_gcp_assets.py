"""Rebuild the Google Cloud icon catalogue and checksums from the official downloads.

Usage: python tools/setup_gcp_assets.py --modern A:/Downloads/gcp-icons
           --legacy-zip A:/Downloads/google-cloud-legacy-icons.zip [--icons-out DIR]

Maintainer tool (offline; reads downloads you supply). Google Cloud icons are not
redistributed, so only our own data is written into the runtime assets:
  assets/gcp-catalog.json   service names, styles, source names and expected file names
  assets/manifest-gcp.json  SHA-256 per icon file
The icon files go to --icons-out (default ~/.architecture-suite/gcp-icons), the same
layout `architecture-suite install-gcp-icons` writes. Review assets/licenses/GCP-USAGE.md
by hand when the terms or sources change.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "skills/architecture-suite-runtime/scripts"
sys.path.insert(0, str(RUNTIME))
from architecture_suite.aws import gcp_icon_root, gcp_key, validate_svg  # noqa: E402

ASSETS = RUNTIME / "architecture_suite/assets"

# Modern file stems -> display names (folder names are not usable as keys).
MODERN = {
    "Agents": "Agents",
    "AIMachineLearning": "AI & Machine Learning",
    "BusinessIntelligence": "Business Intelligence",
    "Collaboration": "Collaboration",
    "Compute": "Compute",
    "Containers": "Containers",
    "DataAnalytics": "Data Analytics",
    "Databases": "Databases",
    "Developer_Tools": "Developer Tools",
    "DevOps": "DevOps",
    "HybridMulticloud": "Hybrid & Multicloud",
    "IntegrationServices": "Integration Services",
    "ManagementTools": "Management Tools",
    "MapsGeospatial": "Maps & Geospatial",
    "Marketplace": "Marketplace",
    "MediaServices": "Media Services",
    "Migration": "Migration",
    "MixedReality": "Mixed Reality",
    "Networking": "Networking",
    "Observability": "Observability",
    "Operations": "Operations",
    "SecurityIdentity": "Security & Identity",
    "ServerlessComputing": "Serverless Computing",
    "Storage": "Storage",
    "WebMobile": "Web & Mobile",
    "Web3": "Web3",
    "AIHypercomputer": "AI Hypercomputer",
    "AlloyDB": "AlloyDB",
    "Anthos": "Anthos",
    "Apigee": "Apigee",
    "BigQuery": "BigQuery",
    "CloudRun": "Cloud Run",
    "CloudSpanner": "Cloud Spanner",
    "CloudSQL": "Cloud SQL",
    "Cloud_Storage": "Cloud Storage",
    "ComputeEngine": "Compute Engine",
    "DistributedCloud": "Distributed Cloud",
    "GKE": "Google Kubernetes Engine",
    "Hyperdisk": "Hyperdisk",
    "Looker": "Looker",
    "Mandiant": "Mandiant",
    "SecurityCommandCenter": "Security Command Center",
    "SecOps": "Security Operations",
    "ThreatIntelligence": "Threat Intelligence",
    "VertexAI": "Vertex AI",
}
CATEGORY_STEMS = set(list(MODERN)[:26])


def stem_of(path: Path) -> str:
    return re.sub(r"-512-color(?:-rgb)?$", "", path.stem)


def put(directory: Path, name: str, data: bytes) -> str:
    validate_svg(data)
    (directory / name).write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--modern", required=True)
    parser.add_argument("--legacy-zip", required=True)
    parser.add_argument("--icons-out", type=Path, default=None)
    args = parser.parse_args()
    icons = args.icons_out or gcp_icon_root()
    catalog, hashes = {}, {}
    modern_dir, legacy_dir = icons / "modern", icons / "legacy"
    for directory in (modern_dir, legacy_dir):
        directory.mkdir(parents=True, exist_ok=True)
        for stale in directory.glob("*.svg"):
            stale.unlink()
    modern_root = Path(args.modern)
    modern_hash = hashlib.sha256()
    for source in sorted(modern_root.rglob("*.svg")):
        stem = stem_of(source)
        display = MODERN[stem]
        category = stem in CATEGORY_STEMS
        key = "GCP-" + ("Category-" if category else "") + re.sub(
            r"[^A-Za-z0-9]+", "-", display
        ).strip("-")
        data = source.read_bytes()
        modern_hash.update(data)
        hashes[f"modern/{key}.svg"] = put(modern_dir, f"{key}.svg", data)
        catalog[key] = {
            "file": f"modern/{key}.svg",
            "style": "modern",
            "label": display,
            "kind": "category" if category else "product",
            "service_id": gcp_key(("category " if category else "") + display),
            "source": source.relative_to(modern_root).as_posix(),
        }
    with open(args.legacy_zip, "rb") as handle:
        archive = handle.read()
    with zipfile.ZipFile(args.legacy_zip) as bundle:
        for name in sorted(bundle.namelist()):
            parts = Path(name).parts
            if (
                not name.endswith(".svg")
                or parts[0] == "__MACOSX"
                or Path(name).name.startswith("._")
                or len(parts) != 2
            ):
                continue
            stem = Path(name).stem
            key = "GCP-Legacy-" + stem
            hashes[f"legacy/{key}.svg"] = put(legacy_dir, f"{key}.svg", bundle.read(name))
            catalog[key] = {
                "file": f"legacy/{key}.svg",
                "style": "legacy",
                "label": stem.replace("_", " ").replace("-", " ").title(),
                "kind": "product",
                "service_id": gcp_key(stem),
                "source": name,
            }
    (ASSETS / "gcp-catalog.json").write_bytes(
        json.dumps(catalog, indent=2, sort_keys=True).encode()
    )
    (ASSETS / "manifest-gcp.json").write_bytes(
        (json.dumps(hashes, indent=2, sort_keys=True) + "\n").encode()
    )
    provenance_path = ASSETS / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["gcp"] = {
        "source": "https://cloud.google.com/icons",
        "retrieved": provenance.get("gcp", {}).get("retrieved", "unknown"),
        "redistributed": False,
        "modern_sha256": modern_hash.hexdigest(),
        "legacy_archive_sha256": hashlib.sha256(archive).hexdigest(),
        "modern_icons": sum(e["style"] == "modern" for e in catalog.values()),
        "legacy_icons": sum(e["style"] == "legacy" for e in catalog.values()),
    }
    provenance_path.write_bytes(json.dumps(provenance, indent=2).encode())
    files = {
        p.relative_to(ASSETS).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(ASSETS.rglob("*"))
        if p.is_file() and p.name != "manifest.json"
    }
    (ASSETS / "manifest.json").write_bytes(json.dumps(files, indent=2).encode())
    print(json.dumps(provenance["gcp"], indent=2))


if __name__ == "__main__":
    main()
