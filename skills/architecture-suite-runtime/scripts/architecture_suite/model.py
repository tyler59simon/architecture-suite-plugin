"""Schema 2.0 validation and scope projection."""

from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any
from .safety import SECRET

SCHEMA_VERSION = "2.0"
VIEW_LEVELS = (
    ("system-context", "context", "01-system-context"),
    ("containers", "container", "02-containers"),
    ("components", "component", "03-components"),
    ("code", "code", "04-code"),
)
VIEW_FOLDERS = {t: f for _, t, f in VIEW_LEVELS}
OVERVIEW_ID, OVERVIEW_FOLDER = "overview", "05-overview"
VALIDATION_PROFILES = ("context", "container", "component", "code")
ELEMENT_TYPE_DEPTH = {
    "person": 1,
    "software_system": 1,
    "container": 2,
    "component": 3,
    "code": 4,
}
VIEW_TYPE_DEPTH = dict(zip(VALIDATION_PROFILES, range(1, 5)))
VIEW_BOUNDARY_TYPES = {
    "container": "software_system",
    "component": "container",
    "code": "component",
}
ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
# Optional per-claim status, weakest first. Absent means "not stated" and renders as today.
CLAIM_STATUSES = ("unknown", "proposed", "inferred", "observed")


def slugify(value: str, fallback: str = "item") -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or fallback


def view_id_for(view_type: str, boundary_id: str) -> str:
    return f"{view_type}-{boundary_id}"


def load_model(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Architecture model root must be a JSON object")
    return value


def model_as_json(model: dict) -> str:
    return (
        json.dumps(
            normalized_model(model), indent=2, sort_keys=True, ensure_ascii=False
        )
        + "\n"
    )


def error_findings(findings: list[dict]) -> list[dict]:
    return [f for f in findings if f.get("severity", "error") == "error"]


def normalize_validation_profile(profile: str = "full") -> str:
    profile = "code" if profile == "full" else profile
    if profile not in VALIDATION_PROFILES:
        raise ValueError(
            "validation profile must be full, context, container, component, or code"
        )
    return profile


def normalized_model(model: dict) -> dict:
    value = deepcopy(model)
    value.setdefault("schema_version", SCHEMA_VERSION)
    for key in ("elements", "relationships", "evidence"):
        value.setdefault(key, []).sort(key=lambda item: str(item.get("id", "")))
    value.setdefault("views", []).sort(
        key=lambda v: (
            VIEW_TYPE_DEPTH.get(v.get("type"), 9),
            v.get("boundary_id", ""),
            v.get("id", ""),
        )
    )
    for key in ("assumptions", "gaps"):
        value.setdefault(key, []).sort()
    if isinstance(value.get("deployment"), dict):
        value["deployment"].setdefault("nodes", []).sort(key=lambda n: n["id"])
        value["deployment"].setdefault("placements", []).sort(
            key=lambda p: (p["element_id"], p["node_id"])
        )
    return value


def project_model(model: dict, profile: str) -> dict:
    depth = VIEW_TYPE_DEPTH[normalize_validation_profile(profile)]
    result = deepcopy(model)
    result["elements"] = [
        e
        for e in result.get("elements", [])
        if ELEMENT_TYPE_DEPTH.get(e.get("type"), 99) <= depth
    ]
    visible = {e["id"] for e in result["elements"]}
    result["views"] = [
        v
        for v in result.get("views", [])
        if VIEW_TYPE_DEPTH.get(v.get("type"), 99) <= depth
    ]
    used = {r for v in result["views"] for r in v.get("relationship_ids", [])}
    result["relationships"] = [
        r
        for r in result.get("relationships", [])
        if r["id"] in used and {r["source_id"], r["destination_id"]} <= visible
    ]
    if "deployment" in result:
        if depth == 1:
            result.pop("deployment")
        else:
            result["deployment"]["placements"] = [
                p
                for p in result["deployment"].get("placements", [])
                if p.get("element_id") in visible
            ]
    result["gaps"] = [
        g
        for g in result.get("gaps", [])
        if not (depth < 4 and ("L4" in g or "code structure" in g))
        and not (depth < 3 and "L3" in g)
    ]
    return normalized_model(result)


def derive_views(
    elements: list[dict], flows: list[dict], layout: dict | None = None
) -> tuple[list[dict], list[dict], list[str]]:
    """Project each declared flow to the nearest visible ancestor in every scope."""
    by_id = {e["id"]: e for e in elements}
    systems = [
        e for e in elements if e["type"] == "software_system" and not e.get("external")
    ]
    system_id = systems[0]["id"]
    views = [
        {
            "id": "system-context",
            "type": "context",
            "element_ids": [
                e["id"] for e in elements if ELEMENT_TYPE_DEPTH[e["type"]] == 1
            ],
        }
    ]
    views.append(
        {
            "id": "containers",
            "type": "container",
            "boundary_id": system_id,
            "element_ids": [
                e["id"]
                for e in elements
                if e["id"] != system_id and ELEMENT_TYPE_DEPTH[e["type"]] <= 2
            ],
        }
    )
    for typ, parent_type in (("component", "container"), ("code", "component")):
        for parent in elements:
            children = [e["id"] for e in elements if e.get("parent_id") == parent["id"]]
            if parent["type"] == parent_type and children:
                views.append(
                    {
                        "id": view_id_for(typ, parent["id"]),
                        "type": typ,
                        "boundary_id": parent["id"],
                        "element_ids": children,
                    }
                )
    relationships, merges = [], []
    for view in views:
        visible = set(view["element_ids"])
        boundary = view.get("boundary_id")
        # Coarser dependencies remain outside the scope; sibling internals collapse to their container.
        if view["type"] in {"component", "code"}:
            visible.update(
                e["id"]
                for e in elements
                if e["type"] in {"person", "software_system", "container"}
                and e["id"] not in {boundary, system_id}
            )
            if view["type"] == "code":
                visible.update(
                    e["id"]
                    for e in elements
                    if e["type"] == "component" and e["id"] != boundary
                )
                visible.discard(by_id[boundary].get("parent_id"))

        def ancestor(ident):
            seen = set()
            while ident not in visible and ident in by_id and ident not in seen:
                seen.add(ident)
                ident = by_id[ident].get("parent_id")
            return ident if ident in visible else None

        pairs: dict[tuple, list] = {}
        for flow in flows:
            src, dst = ancestor(flow["source_id"]), ancestor(flow["destination_id"])
            if not src or not dst or src == dst:
                continue
            if view["type"] in {"component", "code"} and not any(
                by_id[x].get("parent_id") == boundary for x in (src, dst)
            ):
                continue
            pairs.setdefault((src, dst), []).append(flow)
        used = set(view["element_ids"])
        view["relationship_ids"] = []
        for (src, dst), entries in pairs.items():
            ident = f"{view['id']}-r{len(view['relationship_ids']) + 1}"
            relationship = {
                "id": ident,
                "source_id": src,
                "destination_id": dst,
                "description": "; ".join(
                    dict.fromkeys(e["description"] for e in entries)
                ),
                "evidence_ids": sorted(
                    {r for e in entries for r in e.get("evidence_ids", [])}
                ),
                "flow_ids": [e["id"] for e in entries],
            }
            technology = "; ".join(
                dict.fromkeys(e["technology"] for e in entries if e.get("technology"))
            )
            if technology:
                relationship["technology"] = technology
            # A merged arrow is only as certain as its weakest stated flow.
            declared = [e["status"] for e in entries if e.get("status") in CLAIM_STATUSES]
            if declared:
                relationship["status"] = min(declared, key=CLAIM_STATUSES.index)
            relationships.append(relationship)
            view["relationship_ids"].append(ident)
            used.update((src, dst))
            if len(entries) > 1:
                merges.append(f"{ident}: " + ", ".join(e["id"] for e in entries))
        view["element_ids"] = [e["id"] for e in elements if e["id"] in used]
        if boundary and boundary not in view["element_ids"]:
            view["element_ids"].insert(0, boundary)
        scope = by_id.get(boundary, systems[0])["name"]
        view["title"] = f"{scope} — {view['type'].title()}"
        view["direction"] = (
            (layout or {})
            .get("views", {})
            .get(view["id"], (layout or {}).get("direction", "auto"))
        )
    return views, relationships, merges


def validate_model(model: dict, profile: str = "full") -> list[dict[str, str]]:
    """Validate model shape, C4 prefix, containment, endpoints, and placements."""
    findings = []

    def add(code, message, path=""):
        findings.append({"code": code, "message": message, "path": path})

    depth = VIEW_TYPE_DEPTH[normalize_validation_profile(profile)]
    if not isinstance(model, dict):
        return [
            {"code": "model-object", "message": "Model must be an object", "path": ""}
        ]
    from jsonschema import Draft202012Validator
    from .aws import ASSETS

    schema = json.loads(
        (ASSETS / "architecture-model.schema.json").read_text(encoding="utf-8")
    )
    shape_errors = sorted(
        Draft202012Validator(schema).iter_errors(model), key=lambda e: str(list(e.path))
    )
    if shape_errors:
        return [
            {
                "code": "model-schema",
                "message": e.message,
                "path": ".".join(map(str, e.path)),
            }
            for e in shape_errors
        ]
    if model.get("schema_version") != SCHEMA_VERSION:
        add("schema-version", "schema_version must be '2.0'", "schema_version")
    system = model.get("system")
    if not isinstance(system, dict):
        add("system-required", "system must be an object", "system")
    else:
        for key in ("name", "description", "classification", "scope"):
            if not isinstance(system.get(key), str) or not system[key].strip():
                add("system-field", f"system.{key} must be non-empty", f"system.{key}")
    arrays = {}
    for key in ("elements", "relationships", "views", "evidence"):
        items = model.get(key)
        if not isinstance(items, list):
            add(f"{key}-array", f"{key} must be an array", key)
            items = []
        lookup = {}
        for i, item in enumerate(items):
            path = f"{key}[{i}]"
            if not isinstance(item, dict):
                add("entry-object", "Entry must be an object", path)
                continue
            ident = item.get("id")
            if not isinstance(ident, str) or not ID_PATTERN.fullmatch(ident):
                add("invalid-id", "IDs must be kebab-case", path)
                continue
            if ident in lookup:
                add("duplicate-id", f"Duplicate id {ident}", path)
            lookup[ident] = item
        arrays[key] = lookup
    elements, relationships, views, evidence = (
        arrays[k] for k in ("elements", "relationships", "views", "evidence")
    )
    owned_systems = [
        e
        for e in elements.values()
        if e.get("type") == "software_system" and not e.get("external")
    ]
    if len(owned_systems) != 1:
        add("system-boundary", "Exactly one owned software system is required")
    for ident, e in elements.items():
        typ = e.get("type")
        if typ not in ELEMENT_TYPE_DEPTH or ELEMENT_TYPE_DEPTH.get(typ, 99) > depth:
            add("element-depth", "Unsupported element type or selected depth", ident)
        for key in ("name", "description"):
            if not isinstance(e.get(key), str) or not e[key].strip():
                add("element-field", f"Element {key} required", ident)
        if (
            typ in VIEW_BOUNDARY_TYPES
            and elements.get(e.get("parent_id"), {}).get("type")
            != VIEW_BOUNDARY_TYPES[typ]
        ):
            add("element-hierarchy", "Missing or wrong parent type", ident)
        if typ in {"person", "software_system"} and e.get("parent_id"):
            add("element-hierarchy", "Context elements cannot have a parent", ident)
        if typ == "code" and (
            not isinstance(e.get("members"), list)
            or not e["members"]
            or not all(isinstance(x, str) and x.strip() for x in e["members"])
        ):
            add("code-members", "Code requires UML members", ident)
        if "confidence" in e and (
            not isinstance(e["confidence"], (int, float))
            or not 0 <= e["confidence"] <= 1
        ):
            add("confidence", "Confidence must be between 0 and 1", ident)
        if e.get("cloud"):
            from .aws import catalog

            provider = (
                e["cloud"].get("provider") if isinstance(e["cloud"], dict) else None
            )
            if provider not in ("aws", "gcp") or e["cloud"].get(
                "service"
            ) not in catalog(provider):
                add(
                    "gcp-service" if provider == "gcp" else "aws-service",
                    f"Invalid {(provider or 'AWS').upper()} service metadata",
                    ident,
                )
        for ref in e.get("evidence_ids", []):
            if ref not in evidence:
                add("evidence-reference", "Unknown evidence id", ident)
    for ident, r in relationships.items():
        if (
            r.get("source_id") not in elements
            or r.get("destination_id") not in elements
        ):
            add("relationship-endpoint", "Unknown relationship endpoint", ident)
        if r.get("source_id") == r.get("destination_id"):
            add("relationship-self", "Relationship endpoints must differ", ident)
        if not isinstance(r.get("description"), str) or not r["description"].strip():
            add("relationship-description", "Relationship description required", ident)
        if any(ref not in evidence for ref in r.get("evidence_ids", [])):
            add("evidence-reference", "Unknown relationship evidence", ident)
    for typ in VALIDATION_PROFILES[:depth]:
        count = sum(v.get("type") == typ for v in views.values())
        if typ in {"context", "container"} and count != 1:
            add("view-count", f"Exactly one {typ} view required")
        if typ in {"component", "code"} and count == 0:
            add(
                "view-prefix",
                f"Selected {typ} depth requires an evidenced {typ} view; choose a shallower --level",
            )
        parent_type = VIEW_BOUNDARY_TYPES.get(typ)
        if typ in {"component", "code"}:
            expected = {
                e["id"]
                for e in elements.values()
                if e.get("type") == parent_type
                and any(x.get("parent_id") == e["id"] for x in elements.values())
            }
            actual = [
                v.get("boundary_id") for v in views.values() if v.get("type") == typ
            ]
            if set(actual) != expected or len(actual) != len(set(actual)):
                add(
                    "view-scopes",
                    f"{typ} scopes must expand every eligible parent exactly once",
                )
    for ident, v in views.items():
        typ = v.get("type")
        if typ not in VIEW_TYPE_DEPTH or VIEW_TYPE_DEPTH.get(typ, 99) > depth:
            add("view-type", "Unsupported view or selected depth", ident)
        if (
            typ in VIEW_BOUNDARY_TYPES
            and elements.get(v.get("boundary_id"), {}).get("type")
            != VIEW_BOUNDARY_TYPES[typ]
        ):
            add("view-boundary", "Wrong view boundary type", ident)
        expected_id = {"context": "system-context", "container": "containers"}.get(typ)
        if expected_id is None and typ in {"component", "code"}:
            expected_id = view_id_for(typ, str(v.get("boundary_id")))
        if expected_id and ident != expected_id:
            add("view-id", "View id must match its canonical scope", ident)
        ids, rids = v.get("element_ids"), v.get("relationship_ids")
        if (
            not isinstance(ids, list)
            or len(ids) != len(set(map(str, ids)))
            or any(x not in elements for x in ids if isinstance(x, str))
        ):
            add("view-elements", "Invalid view element references", ident)
            ids = []
        if not isinstance(rids, list) or any(
            x not in relationships for x in rids if isinstance(x, str)
        ):
            add("view-relationships", "Invalid view relationship references", ident)
            rids = []
        for rid in rids:
            r = relationships.get(rid, {})
            if r.get("source_id") not in ids or r.get("destination_id") not in ids:
                add(
                    "view-endpoint",
                    "View must contain both relationship endpoints",
                    ident,
                )
        for eid in ids:
            element = elements.get(eid, {})
            etype = element.get("type")
            if typ == "context" and etype not in {"person", "software_system"}:
                add(
                    "view-scope", "Context cannot contain implementation details", ident
                )
            if typ == "container" and (
                etype in {"component", "code"}
                or etype == "container"
                and element.get("parent_id") != v.get("boundary_id")
            ):
                add("view-scope", "Container view must stay within its system", ident)
            if typ == "component" and (
                etype == "code"
                or etype == "component"
                and element.get("parent_id") != v.get("boundary_id")
            ):
                add(
                    "view-scope",
                    "Component view cannot expand sibling container internals",
                    ident,
                )
            if (
                typ == "code"
                and etype == "code"
                and element.get("parent_id") != v.get("boundary_id")
            ):
                add(
                    "view-scope",
                    "Code view cannot expand sibling component internals",
                    ident,
                )
        if v.get("direction", "auto") not in {"auto", "down", "right"}:
            add("view-direction", "Direction must be auto, down or right", ident)
    deployment = model.get("deployment")
    if deployment is not None:
        if (
            not isinstance(deployment, dict)
            or not isinstance(deployment.get("nodes"), list)
            or not isinstance(deployment.get("placements"), list)
        ):
            add("deployment-shape", "Deployment requires nodes and placements arrays")
        else:
            nodes = {
                n.get("id"): n
                for n in deployment["nodes"]
                if isinstance(n, dict) and isinstance(n.get("id"), str)
            }
            if len(nodes) != len(deployment["nodes"]):
                add("deployment-id", "Invalid or duplicate deployment id")
            for nid, node in nodes.items():
                if not ID_PATTERN.fullmatch(nid) or node.get("type") not in {
                    "cloud",
                    "organization",
                    "folder",
                    "project",
                    "zone",
                    "account",
                    "region",
                    "vpc",
                    "availability-zone",
                    "subnet",
                    "cluster",
                    "device",
                    "off-cloud",
                    "execution-environment",
                    "deployment-group",
                }:
                    add("deployment-node", "Unsupported deployment node", nid)
                parent_types = {
                    "account": {"cloud"},
                    "region": {"account"},
                    "vpc": {"region"},
                    "availability-zone": {"vpc"},
                    "subnet": {"availability-zone", "vpc"},
                    "cluster": {"subnet", "availability-zone", "vpc", "region"},
                    "execution-environment": {"device", "execution-environment"},
                }
                if deployment.get("provider") == "gcp":
                    parent_types = {
                        "organization": {"cloud"},
                        "folder": {"organization", "folder"},
                        "project": {"cloud", "organization", "folder"},
                        "region": {"project"},
                        "vpc": {"project", "region"},
                        "zone": {"region", "vpc"},
                        "subnet": {"region", "zone", "vpc"},
                        "cluster": {"subnet", "zone", "vpc", "region", "project"},
                        "execution-environment": {"device", "execution-environment"},
                    }
                if (
                    node.get("type") in parent_types
                    and nodes.get(node.get("parent_id"), {}).get("type")
                    not in parent_types[node["type"]]
                ):
                    add("deployment-hierarchy", "Invalid deployment boundary parent type", nid)
                seen, parent = {nid}, node.get("parent_id")
                while parent:
                    if parent in seen or parent not in nodes:
                        add(
                            "deployment-parent",
                            "Missing or cyclic deployment parent",
                            nid,
                        )
                        break
                    seen.add(parent)
                    parent = nodes[parent].get("parent_id")
            placements = set()
            for p in deployment["placements"]:
                if (
                    not isinstance(p, dict)
                    or elements.get(p.get("element_id"), {}).get("type") != "container"
                    or p.get("node_id") not in nodes
                ):
                    add(
                        "deployment-placement",
                        "Placements require a container and existing node",
                    )
                    continue
                pair = p["element_id"]
                if pair in placements:
                    add("deployment-placement", "Duplicate placement")
                placements.add(pair)
    if SECRET.search(json.dumps(model, ensure_ascii=False)):
        add("credential", "Credential-like value must be redacted")
    return findings
