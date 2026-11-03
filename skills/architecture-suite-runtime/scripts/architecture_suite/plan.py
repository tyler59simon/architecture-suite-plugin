"""Human-authored Markdown/YAML plan parser, lint, and fidelity compiler."""

from __future__ import annotations
from dataclasses import asdict, dataclass, field
import json
import re
from typing import Any
import yaml
from .aws import PROVIDERS, normalize_gcp_icon_style, resolve_service
from .model import derive_views, slugify, validate_model
from .safety import SECRET, safe_text

PLAN_SCHEMA_VERSION = "architecture-plan/v1"
SECTION_KEYS = (
    "system",
    "people",
    "external_systems",
    "containers",
    "flows",
    "deployment",
    "layout",
    "evidence",
    "assumptions",
    "gaps",
)
ERROR, ADVISORY = "error", "advisory"
META_KEYS = {"schema_version", "title", "gcp_icon_style"}
CLOUD_ROOTS = {"aws": ("aws-cloud", "AWS Cloud"), "gcp": ("gcp-cloud", "Google Cloud")}


class PlanError(ValueError):
    """A plan cannot compile without silently losing or inventing facts."""


class _Loader(yaml.SafeLoader):
    pass


def _mapping(loader, node):
    result = {}
    for k, v in node.value:
        key = loader.construct_object(k)
        if not isinstance(key, str) or key in result:
            raise PlanError("Mapping keys must be unique strings")
        result[key] = loader.construct_object(v)
    return result


_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def parse_yaml(source: str) -> Any:
    if len(source) > 2_000_000:
        raise PlanError("Plan exceeds 2 MB")
    try:
        for token in yaml.scan(source):
            if isinstance(
                token,
                (yaml.tokens.AliasToken, yaml.tokens.AnchorToken, yaml.tokens.TagToken),
            ):
                raise PlanError("YAML anchors, aliases, and tags are unsupported")
        return yaml.load(source, Loader=_Loader)
    except (yaml.YAMLError, RecursionError) as exc:
        raise PlanError(f"Malformed YAML: {str(exc)[:200]}") from exc


def parse_plan_document(source: str) -> dict:
    if len(source) > 2_000_000:
        raise PlanError("Plan exceeds 2 MB")
    blocks = []
    current = None
    for line in source.splitlines():
        if re.fullmatch(r"\s*```ya?ml\s*", line):
            if current is not None:
                raise PlanError("Unclosed YAML fence")
            current = []
        elif current is not None and line.strip() == "```":
            blocks.append("\n".join(current))
            current = None
        elif current is not None:
            current.append(line)
    if current is not None or not blocks:
        raise PlanError("Expected closed fenced YAML blocks")
    result = {}
    for block in blocks:
        value = parse_yaml(block)
        if value in (None, {}, []):
            continue
        if not isinstance(value, dict):
            raise PlanError("A plan block must be a mapping")
        for key, item in value.items():
            if key not in result or result[key] in (None, [], {}):
                result[key] = item
            elif isinstance(result[key], list) and isinstance(item, list):
                result[key].extend(item)
            else:
                raise PlanError(f"Section {key!r} is already set by an earlier block")
    return result


@dataclass
class Finding:
    code: str
    message: str
    where: str = ""
    severity: str = ERROR

    @property
    def blocking(self) -> bool:
        return self.severity == ERROR

    def render(self) -> str:
        return f"{self.severity}: {self.code}: {self.message}" + (
            f" [{self.where}]" if self.where else ""
        )


def errors(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.blocking]


def advisories(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if not f.blocking]


def _entries(plan):
    yield plan.get("system"), "system", None

    def walk(items, typ, parent):
        if isinstance(items, list):
            for item in items:
                yield item, typ, parent
                if isinstance(item, dict):
                    if typ == "container":
                        yield from walk(
                            item.get("components"), "component", item.get("name")
                        )
                    if typ == "component":
                        yield from walk(item.get("code"), "code", item.get("name"))

    for section, typ in (
        ("people", "person"),
        ("external_systems", "software_system"),
        ("containers", "container"),
    ):
        yield from walk(
            plan.get(section),
            typ,
            plan.get("system", {}).get("name")
            if typ == "container" and isinstance(plan.get("system"), dict)
            else None,
        )


def plan_provider(plan: dict) -> str:
    """Explicit deployment.provider wins; otherwise infer from *_service fields."""
    deployment = plan.get("deployment")
    explicit = deployment.get("provider") if isinstance(deployment, dict) else None
    if explicit in PROVIDERS:
        return explicit
    entries = [item for item, _, _ in _entries(plan) if isinstance(item, dict)]
    has_gcp = any(item.get("gcp_service") for item in entries)
    has_aws = any(item.get("aws_service") for item in entries)
    return "gcp" if has_gcp and not has_aws else "aws"


def _deployment(deployment: dict, names: dict, provider: str = "aws") -> dict:
    nodes = []
    entries = deployment.get("nodes", [])
    cloud = None
    if not any(n.get("type") == "cloud" for n in entries):
        cloud, cloud_name = CLOUD_ROOTS[provider]
        nodes.append({"id": cloud, "name": cloud_name, "type": "cloud"})

    def walk(items, parent):
        for item in items:
            ident = item.get("id") or slugify(item["name"])
            node = {k: v for k, v in item.items() if k not in {"children", "nodes"}}
            node["id"] = ident
            if parent:
                node["parent_id"] = parent
            nodes.append(node)
            walk(item.get("children", item.get("nodes", [])), ident)

    walk(entries, cloud)
    node_names = {n["name"]: n["id"] for n in nodes}
    placements = []
    for p in deployment.get("placements", []):
        element = p.get("element", p.get("element_id", p.get("container")))
        node = p.get("node", p.get("node_id"))
        placements.append(
            {
                "element_id": names.get(element, element),
                "node_id": node_names.get(node, node),
            }
        )
    return {"provider": provider, "nodes": nodes, "placements": placements}


def lint_plan(plan: dict, gcp_icon_style: str | None = None) -> list[Finding]:
    findings = []

    def add(code, message, where="", severity=ERROR):
        findings.append(Finding(code, message, where, severity))

    if not isinstance(plan, dict):
        return [Finding("plan-object", "Plan must be a mapping")]
    if set(plan) - set(SECTION_KEYS) - META_KEYS:
        add("unknown-section", "Unknown plan section")
    try:
        style = normalize_gcp_icon_style(gcp_icon_style or plan.get("gcp_icon_style"))
    except (ValueError, AttributeError):
        add("gcp-icon-style", "gcp_icon_style must be auto, modern or legacy")
        style = "auto"
    if plan.get("schema_version", PLAN_SCHEMA_VERSION) != PLAN_SCHEMA_VERSION:
        add("schema-version", "Unsupported plan schema")
    system = plan.get("system")
    if not isinstance(system, dict):
        return findings + [Finding("system-required", "System must be a mapping")]
    for key in ("name", "description", "classification", "scope"):
        if not isinstance(system.get(key), str) or not system[key].strip():
            add("system-field", f"System {key} is required", "system")
    for section in (
        "people",
        "external_systems",
        "containers",
        "flows",
        "assumptions",
        "gaps",
    ):
        if section in plan and not isinstance(plan[section], list):
            add("section-list", f"{section} must be a list", section)
    for section in ("containers", "flows"):
        if section not in plan:
            add("section-required", f"{section} is required", section)
    names, ids, groups = {}, set(), {}
    entries = list(_entries(plan))
    for item, typ, parent in entries:
        if not isinstance(item, dict):
            add("element-object", "Element must be a mapping", typ)
            continue
        allowed = {"name", "description", "technology", "group", "evidence"}
        allowed |= {"classification", "scope"} if typ == "system" else set()
        allowed |= {"components", "aws_service", "gcp_service"} if typ == "container" else set()
        allowed |= {"code", "aws_service", "gcp_service"} if typ == "component" else set()
        allowed |= {"kind", "members"} if typ == "code" else set()
        if set(item) - allowed:
            add(
                "unknown-field",
                "Unknown element field: " + ", ".join(sorted(set(item) - allowed)),
                str(item.get("name", typ)),
            )
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            add("element-name", "Element name is required", typ)
            continue
        ident = slugify(name)
        if ident in ids:
            add("duplicate-name", "Names must slugify to unique IDs", name)
        ids.add(ident)
        names[name] = ident
        if typ != "code" and (
            not isinstance(item.get("description"), str)
            or not item["description"].strip()
        ):
            add("element-description", "Description required", name)
        if typ != "system" and not item.get("evidence"):
            add(
                "unevidenced-element",
                "Cite evidence or record an assumption",
                name,
                ADVISORY,
            )
        if "evidence" in item and not isinstance(item["evidence"], (str, list)):
            add("evidence-type", "Evidence must be a reference or list", name)
        if isinstance(item.get("evidence"), list) and not all(
            isinstance(ref, str) and ref.strip() for ref in item["evidence"]
        ):
            add("evidence-type", "Evidence references must be non-empty strings", name)
        for text_key in ("technology", "group"):
            if text_key in item and not isinstance(item[text_key], str):
                add("element-field", f"{text_key} must be a string", name)
        if item.get("aws_service") and (
            not isinstance(item["aws_service"], str)
            or not resolve_service(item["aws_service"])
        ):
            add("unknown-aws-service", "No matching official AWS service", name)
        if item.get("gcp_service"):
            if not isinstance(item["gcp_service"], str) or not resolve_service(
                item["gcp_service"], "gcp"
            ):
                add("unknown-gcp-service", "No matching official GCP service", name)
            elif not resolve_service(item["gcp_service"], "gcp", style):
                add(
                    "gcp-icon-unavailable",
                    f"No {style} icon for this service; it renders without an icon",
                    name,
                    ADVISORY,
                )
        for nested in ("components", "code"):
            if nested in item and not isinstance(item[nested], list):
                add("nested-list", f"{nested} must be a list", name)
        if typ == "code":
            if item.get("kind", "class") not in {
                "class",
                "interface",
                "module",
                "function",
            }:
                add("code-kind", "Unsupported code kind", name)
            if (
                not isinstance(item.get("members"), list)
                or not item["members"]
                or not all(isinstance(m, str) and m.strip() for m in item["members"])
            ):
                add("code-members", "At least one UML member required", name)
        if item.get("group"):
            groups.setdefault((parent, str(item["group"])), []).append(name)
    for group, members in groups.items():
        if len(members) == 1:
            add(
                "single-member-group",
                "A single-member group has no frame",
                str(group[1]),
                ADVISORY,
            )
    flows = plan.get("flows", [])
    for i, flow in enumerate(flows if isinstance(flows, list) else []):
        if not isinstance(flow, dict):
            add("flow-object", "Flow must be a mapping", str(i))
            continue
        if set(flow) - {"from", "to", "description", "technology", "order", "evidence"}:
            add("unknown-field", "Unknown flow field", str(i))
        for key in ("from", "to"):
            if not isinstance(flow.get(key), str) or flow[key] not in names:
                add("unknown-endpoint", f"Unknown flow {key}", str(i))
        if flow.get("from") == flow.get("to"):
            add("self-flow", "Flow endpoints must differ", str(i))
        if (
            not isinstance(flow.get("description"), str)
            or not flow["description"].strip()
        ):
            add("flow-description", "Flow description required", str(i))
        if "order" in flow and (
            not isinstance(flow["order"], int) or flow["order"] < 1
        ):
            add("flow-order", "Order must be a positive integer", str(i))
        if not flow.get("evidence"):
            add("unevidenced-flow", "Flow has no evidence", str(i), ADVISORY)
        if "technology" in flow and not isinstance(flow["technology"], str):
            add("flow-technology", "Technology must be a string", str(i))
        if "evidence" in flow and not (
            isinstance(flow["evidence"], str)
            or isinstance(flow["evidence"], list)
            and all(isinstance(ref, str) and ref.strip() for ref in flow["evidence"])
        ):
            add("evidence-type", "Flow evidence must contain string references", str(i))
    for section in ("assumptions", "gaps"):
        if isinstance(plan.get(section), list) and not all(
            isinstance(x, str) for x in plan[section]
        ):
            add("text-list", f"{section} must contain strings", section)
    layout = plan.get("layout", {})
    valid_views = (
        {"system-context", "containers"}
        | {
            f"component-{slugify(e['name'])}"
            for e, t, _ in entries
            if isinstance(e, dict)
            and t == "container"
            and e.get("components")
            and isinstance(e.get("name"), str)
        }
        | {
            f"code-{slugify(e['name'])}"
            for e, t, _ in entries
            if isinstance(e, dict)
            and t == "component"
            and e.get("code")
            and isinstance(e.get("name"), str)
        }
    )
    if (
        not isinstance(layout, dict)
        or set(layout) - {"direction", "views"}
        or layout.get("direction", "auto") not in {"auto", "down", "right"}
        or not isinstance(layout.get("views", {}), dict)
    ):
        add("layout", "Invalid layout mapping")
    else:
        for v, direction in layout.get("views", {}).items():
            if v not in valid_views:
                add("unknown-view", "Layout names an absent view", v)
            if direction not in {"auto", "down", "right"}:
                add("layout-direction", "Unknown layout direction", v)
    if "deployment" in plan:
        try:
            deployment = _deployment(plan["deployment"], names, plan_provider(plan))
            dummy = {
                "schema_version": "2.0",
                "system": system,
                "elements": [
                    {
                        "id": names[e["name"]],
                        "type": "container" if t == "container" else "person",
                        "name": e["name"],
                        "description": "lint",
                    }
                    for e, t, _ in entries
                    if isinstance(e, dict) and e.get("name") in names
                ],
                "relationships": [],
                "views": [],
                "evidence": [],
                "deployment": deployment,
            }
            for finding in validate_model(dummy):
                if finding["code"].startswith("deployment"):
                    add(finding["code"], finding["message"], finding["path"])
        except (KeyError, TypeError, AttributeError, RecursionError):
            add("deployment-shape", "Invalid deployment mapping")
    if SECRET.search(json.dumps(plan, default=str)):
        add("credential", "Remove credential-like values")
    return findings


@dataclass
class Fidelity:
    declared: dict = field(default_factory=dict)
    compiled: dict = field(default_factory=dict)
    merged: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    views: list[str] = field(default_factory=list)

    @property
    def lossless(self) -> bool:
        return not self.dropped

    def as_dict(self) -> dict:
        return {**asdict(self), "lossless": self.lossless}

    @property
    def is_lossless(self) -> bool:
        return self.lossless

    def payload(self) -> dict:
        return self.as_dict()

    def render(self) -> list[str]:
        return [
            "Plan fidelity",
            json.dumps(self.as_dict(), indent=2, ensure_ascii=False),
        ]


def compile_plan(
    plan: dict, gcp_icon_style: str | None = None
) -> tuple[dict, Fidelity]:
    blocking = errors(lint_plan(plan, gcp_icon_style))
    style = normalize_gcp_icon_style(gcp_icon_style or plan.get("gcp_icon_style"))
    if blocking:
        raise PlanError("\n".join(f.render() for f in blocking[:10]))
    elements, evidence, flows = [], [], []
    refs = {}

    def evidence_ids(value):
        ids = []
        for reference in [value] if isinstance(value, str) else value or []:
            reference = safe_text(reference)
            if reference not in refs:
                ident = f"evidence-{len(refs) + 1}"
                refs[reference] = ident
                evidence.append({"id": ident, "reference": reference, "kind": "plan"})
            ids.append(refs[reference])
        return ids

    for item, typ, parent in _entries(plan):
        element = {
            k: safe_text(item[k])
            for k in ("name", "description", "technology", "group", "kind")
            if k in item
        }
        element.update(
            id=slugify(item["name"]), type="software_system" if typ == "system" else typ
        )
        if typ == "code" and not element.get("description"):
            element["description"] = f"{item.get('kind', 'class')} {item['name']}"
        if parent:
            element["parent_id"] = slugify(parent)
        if typ == "software_system":
            element["external"] = True
        if typ == "code":
            element["kind"] = item.get("kind", "class")
            element["members"] = [safe_text(m) for m in item["members"]]
        if item.get("aws_service"):
            element["cloud"] = {
                "provider": "aws",
                "service": resolve_service(item["aws_service"]),
            }
        elif item.get("gcp_service") and resolve_service(
            item["gcp_service"], "gcp", style
        ):
            element["cloud"] = {
                "provider": "gcp",
                "service": resolve_service(item["gcp_service"], "gcp", style),
            }
        element["evidence_ids"] = evidence_ids(item.get("evidence"))
        elements.append(element)
    for i, flow in enumerate(plan["flows"]):
        flows.append(
            {
                "id": f"flow-{i + 1}",
                "source_id": slugify(flow["from"]),
                "destination_id": slugify(flow["to"]),
                "description": safe_text(flow["description"]),
                "technology": safe_text(flow.get("technology", "")),
                "evidence_ids": evidence_ids(flow.get("evidence")),
            }
        )
    for reference in plan.get("evidence", []) or []:
        evidence_ids(
            reference.get("reference", str(reference))
            if isinstance(reference, dict)
            else reference
        )
    views, relationships, merges = derive_views(elements, flows, plan.get("layout"))
    model = {
        "schema_version": "2.0",
        "system": {
            k: safe_text(plan["system"][k])
            for k in ("name", "description", "classification", "scope")
        },
        "elements": elements,
        "relationships": relationships,
        "views": views,
        "evidence": evidence,
        "assumptions": list(plan.get("assumptions", [])),
        "gaps": list(plan.get("gaps", [])),
    }
    if plan.get("deployment"):
        model["deployment"] = _deployment(
            plan["deployment"],
            {e["name"]: e["id"] for e in elements},
            plan_provider(plan),
        )
    fidelity = Fidelity(
        declared={"elements": len(elements), "flows": len(flows), "views": len(views)},
        compiled={
            "elements": len(elements),
            "flows": len(relationships),
            "views": len(views),
        },
        merged=merges,
        views=[v["id"] for v in views],
    )
    used_flows = {f for r in relationships for f in r["flow_ids"]}
    fidelity.dropped = [
        f"{f['id']}: collapses within every view"
        for f in flows
        if f["id"] not in used_flows
    ]
    return model, fidelity


def slug(value: str) -> str:
    return slugify(value)
