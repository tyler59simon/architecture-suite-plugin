"""Ship versioned extension document schemas alongside the legacy contracts."""

import hashlib
import json
from pathlib import Path

root = (
    Path(__file__).resolve().parents[1]
    / "skills/architecture-suite-runtime/scripts/architecture_suite/assets"
)
contracts = {
    "inventory": {
        "declarations": "array",
        "references": "array",
        "routes": "array",
        "connections": "array",
        "findings": "array",
    },
    "topology": {
        "resources": "array",
        "relationships": "array",
        "bindings": "object",
        "findings": "array",
    },
    "scenario": {"name": "string", "participants": "array", "steps": "array"},
    "diff": {"changes": "array", "changed": "boolean"},
    "rules": {"rules": "array"},
    "check": {"findings": "array", "fingerprints": "array", "new_errors": "integer"},
    "baseline": {"fingerprints": "array"},
}
manifest = json.loads((root / "manifest.json").read_text())
for kind, fields in contracts.items():
    version = f"architecture-{kind}/v1"
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "schema_version": {"const": version},
            **{key: {"type": value} for key, value in fields.items()},
        },
        "required": ["schema_version", *fields],
    }
    file = root / f"architecture-{kind}.schema.json"
    file.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    manifest[file.name] = hashlib.sha256(file.read_bytes()).hexdigest()
(root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
