"""Generate distributed machine-readable contracts; field semantics are checked by model.py."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/architecture-suite-runtime/scripts/architecture_suite/assets"
STRING = {"type": "string"}
STRINGS = {"type": "array", "items": STRING}


def obj(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required)}


def array(item):
    return {"type": "array", "items": item}


def main():
    evidence = obj(
        {
            "id": STRING,
            "reference": STRING,
            "excerpt": STRING,
            "line": {"type": "integer", "minimum": 1},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        ("id",),
    )
    element = obj(
        {
            "id": STRING,
            "name": STRING,
            "type": STRING,
            "description": STRING,
            "technology": STRING,
            "parent_id": STRING,
            "members": STRINGS,
            "evidence_ids": STRINGS,
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "cloud": obj(
                {"provider": STRING, "service": STRING}, ("provider", "service")
            ),
        },
        ("id", "name", "description", "type"),
    )
    relation = obj(
        {
            "id": STRING,
            "source_id": STRING,
            "destination_id": STRING,
            "description": STRING,
            "technology": STRING,
            "evidence_ids": STRINGS,
            "flow_ids": STRINGS,
        },
        ("id", "source_id", "destination_id", "description"),
    )
    view = obj(
        {
            "id": STRING,
            "type": STRING,
            "title": STRING,
            "boundary_id": STRING,
            "element_ids": STRINGS,
            "relationship_ids": STRINGS,
            "direction": STRING,
        },
        ("id", "type", "title", "element_ids", "relationship_ids"),
    )
    node = obj(
        {"id": STRING, "type": STRING, "name": STRING, "parent_id": STRING},
        ("id", "type", "name"),
    )
    deployment = obj(
        {
            "provider": {"enum": ["aws", "gcp"]},
            "nodes": array(node),
            "placements": array(
                obj(
                    {"element_id": STRING, "node_id": STRING}, ("element_id", "node_id")
                )
            ),
        },
        ("nodes", "placements"),
    )
    model = obj(
        {
            "schema_version": {"const": "2.0"},
            "system": obj(
                {k: STRING for k in ("name", "description", "classification", "scope")},
                ("name", "description", "classification", "scope"),
            ),
            "elements": array(element),
            "relationships": array(relation),
            "views": array(view),
            "evidence": array(evidence),
            "assumptions": STRINGS,
            "gaps": STRINGS,
            "deployment": deployment,
        },
        ("schema_version", "system", "elements", "relationships", "views", "evidence"),
    )
    model["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    (ASSETS / "architecture-model.schema.json").write_text(
        json.dumps(model, indent=2), encoding="utf-8"
    )
    refs = {"oneOf": [STRING, STRINGS]}
    base = {
        "name": STRING,
        "description": STRING,
        "technology": STRING,
        "group": STRING,
        "evidence": refs,
    }
    code = obj(
        {
            **base,
            "kind": {"enum": ["class", "interface", "module", "function"]},
            "members": STRINGS,
        },
        ("name", "members"),
    )
    component = obj(
        {**base, "aws_service": STRING, "gcp_service": STRING, "code": array(code)}, ("name", "description")
    )
    container = obj(
        {**base, "aws_service": STRING, "gcp_service": STRING, "components": array(component)},
        ("name", "description"),
    )
    for item in (code, component, container):
        item["additionalProperties"] = False
    plan = obj(
        {
            "schema_version": {"const": "architecture-plan/v1"},
            "title": STRING,
            "gcp_icon_style": {"enum": ["auto", "modern", "legacy"]},
            "system": model["properties"]["system"],
            "people": array(obj(base, ("name", "description"))),
            "external_systems": array(obj(base, ("name", "description"))),
            "containers": array(container),
            "flows": array(
                obj(
                    {
                        "from": STRING,
                        "to": STRING,
                        "description": STRING,
                        "technology": STRING,
                        "order": {"type": "integer", "minimum": 1},
                        "evidence": refs,
                    },
                    ("from", "to", "description"),
                )
            ),
            "layout": obj(
                {
                    "direction": {"enum": ["auto", "down", "right"]},
                    "views": {
                        "type": "object",
                        "additionalProperties": {"enum": ["auto", "down", "right"]},
                    },
                }
            ),
            "deployment": {"type": "object"},
            "evidence": {"type": "array"},
            "assumptions": STRINGS,
            "gaps": STRINGS,
        },
        ("system", "containers", "flows"),
    )
    plan.update(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "additionalProperties": False,
        }
    )
    (ASSETS / "architecture-plan.schema.json").write_text(
        json.dumps(plan, indent=2), encoding="utf-8"
    )
    manifest = json.loads((ASSETS / "manifest.json").read_text())
    import hashlib

    for path in ASSETS.glob("*.schema.json"):
        manifest[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (ASSETS / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
