"""Static official AWS and Google Cloud catalogue access; no cloud client or network usage.

AWS and Google Cloud icons are bundled and verified against SHA-256 manifests.
ARCHITECTURE_SUITE_GCP_ICONS may point at another folder with the same layout (tests use it);
a GCP icon missing from that folder renders without an icon.
"""

from __future__ import annotations
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from .safety import SafetyError, contained_path

ASSETS = Path(__file__).parent / "assets"
GCP_ICON_ENV = "ARCHITECTURE_SUITE_GCP_ICONS"


def verify_assets() -> dict[str, str]:
    manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest.items():
        path = contained_path(ASSETS, name)
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != digest
        ):
            raise SafetyError(f"Asset missing or checksum mismatch: {name}")
    return manifest


PROVIDERS = ("aws", "gcp")
GCP_ICON_STYLES = ("auto", "modern", "legacy")


def normalize_cloud_profile(value: str | None) -> str | None:
    if value in (None, "none", ""):
        return None
    if value.lower() not in PROVIDERS:
        raise ValueError("cloud profile must be none, aws or gcp")
    return value.lower()


def normalize_gcp_icon_style(value: str | None) -> str:
    if value in (None, ""):
        return "auto"
    if value.lower() not in GCP_ICON_STYLES:
        raise ValueError("gcp icon style must be auto, modern or legacy")
    return value.lower()


GCP_ALIASES = {
    "gke": "kubernetesengine",
    "gce": "computeengine",
    "gcs": "cloudstorage",
    "bq": "bigquery",
    "spanner": "cloudspanner",
    "cloudbigtable": "bigtable",
    "cloudpubsub": "pubsub",
    "cloudmemorystore": "memorystore",
    "vpc": "virtualprivatecloud",
    "cloudvpc": "virtualprivatecloud",
    "iam": "identityandaccessmanagement",
    "kms": "keymanagementservice",
    "cloudkms": "keymanagementservice",
    "cloudloadbalancer": "cloudloadbalancing",
    "secops": "securityoperations",
    "vertex": "vertexai",
    "cloudfirestore": "firestore",
    "apigee": "apigeeapiplatform",
}


def gcp_key(value: str) -> str:
    """Canonical service id: lowercase alphanumerics, no 'google' prefix, aliases applied."""
    text = re.sub(r"[^a-z0-9]", "", value.lower()).removeprefix("google")
    return GCP_ALIASES.get(text, text)


def catalog(provider: str = "aws") -> dict:
    if provider not in PROVIDERS:
        raise ValueError("provider must be aws or gcp")
    return _read_json(ASSETS / f"{provider}-catalog.json")


@lru_cache(maxsize=8)
def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def gcp_icon_root() -> Path:
    """Bundled Google Cloud icons, unless ARCHITECTURE_SUITE_GCP_ICONS names another folder."""
    override = os.environ.get(GCP_ICON_ENV)
    return Path(override) if override else ASSETS / "gcp"


def gcp_manifest() -> dict[str, str]:
    """Expected SHA-256 per GCP icon, relative to the icon root (e.g. modern/GCP-Cloud-Run.svg)."""
    return _read_json(ASSETS / "manifest-gcp.json")


def icon_available(service: str | None) -> bool:
    """AWS icons are always bundled; a GCP icon needs its optional file installed."""
    if not service:
        return False
    if not service.startswith("GCP-"):
        return True
    entry = catalog("gcp").get(service)
    return bool(entry) and (gcp_icon_root() / entry["file"]).is_file()


def gcp_icon_status() -> str:
    """'ok (n of m icons)', or 'missing' when the icon folder is empty; raises on a tampered icon."""
    expected = gcp_manifest()
    root = gcp_icon_root()
    present = [rel for rel in expected if (root / rel).is_file()]
    if not present:
        return f"missing: no icons in {root}"
    for rel in present:
        data = contained_path(root, rel).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected[rel]:
            raise SafetyError(f"GCP icon checksum mismatch: {rel}")
    return f"ok ({len(present)} of {len(expected)} icons)"


def resolve_gcp_service(value: str, style: str = "auto") -> str | None:
    """Return the catalogue key for a GCP service in the requested icon style."""
    style = normalize_gcp_icon_style(style)
    entries = catalog("gcp")
    lowered = {k.lower(): k for k in entries}
    if value.lower() in lowered:
        key = lowered[value.lower()]
        return key if style in ("auto", entries[key]["style"]) else None
    wanted = gcp_key(value)
    for wanted_style in ("modern", "legacy") if style == "auto" else (style,):
        for key in sorted(entries):
            entry = entries[key]
            if entry["style"] == wanted_style and entry["service_id"] == wanted:
                return key
    return None


def resolve_service(
    value: str, provider: str = "aws", style: str = "auto"
) -> str | None:
    if provider == "gcp":
        return resolve_gcp_service(value, style)
    def key(s):
        return re.sub(r"[^a-z0-9]", "", s.lower()).removeprefix("amazon").removeprefix("aws")

    aliases = {
        "ecs": "elasticcontainerservice",
        "eks": "elastickubernetesservice",
        "s3": "simplestorageservice",
        "sqs": "simplequeueservice",
        "sns": "simplenotificationservice",
        "ec2": "elasticcomputecloud",
        "rds": "relationaldatabaseservice",
    }
    wanted = key(value)
    wanted = aliases.get(wanted, wanted)
    for name in sorted(catalog()):
        normalized = key(re.sub(r"_\d+$", "", name))
        if normalized == wanted or aliases.get(normalized) == wanted:
            return name
    return None


def validate_svg(svg: bytes) -> None:
    text = svg.decode("utf-8")
    if len(svg) > 1_000_000 or re.search(
        r"<!DOCTYPE|<!ENTITY|<script|<foreignObject|\bon\w+\s*=|(?:href\s*=\s*['\"](?!#)|url\(\s*(?!#))",
        text,
        re.I,
    ):
        raise SafetyError("Unsafe SVG asset")
    if ET.fromstring(svg).tag.split("}")[-1] != "svg":
        raise SafetyError("Expected SVG asset")


def icon_bytes(service: str, provider: str | None = None) -> bytes:
    provider = provider or ("gcp" if service.startswith("GCP-") else "aws")
    items = catalog(provider)
    if service not in items:
        raise SafetyError(f"Unknown {provider.upper()} icon: {service}")
    relative = items[service]["file"]
    if provider == "gcp":
        path = contained_path(gcp_icon_root(), relative)
        if not path.is_file():
            raise SafetyError(f"GCP icon not installed: {service}")
        expected = gcp_manifest()[relative]
    else:
        path = contained_path(ASSETS / provider, relative)
        expected = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))[
            f"{provider}/{relative}"
        ]
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise SafetyError(f"{provider.upper()} icon checksum mismatch")
    validate_svg(data)
    return data
