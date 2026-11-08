"""Offline import of exported infrastructure. Unresolved values remain findings."""

from pathlib import Path
import json
import re
from .plan import parse_yaml
from .safety import canonical_existing_file, redact
from .model import slugify


def evidence_reference(path) -> str:
    """Path as recorded in evidence: relative to the working directory when inside it, so
    shared artifacts do not expose home-directory layouts; absolute otherwise."""
    path = Path(path)
    try:
        return path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path)

SENSITIVE, UNKNOWN = "[SENSITIVE]", "[UNKNOWN AFTER APPLY]"


def _apply_mask(value, mask, marker, path, hits):
    """Replace what a Terraform sensitivity/unknown mask marks true; record attribute paths.

    Unknown masks also name attributes absent from planned values, so those are added.
    """
    if mask is True:
        hits.append(path or "(resource)")
        return marker
    if isinstance(mask, dict) and isinstance(value, dict):
        result = dict(value)
        for key, sub in mask.items():
            where = f"{path}.{key}" if path else str(key)
            if key in value:
                result[key] = _apply_mask(value[key], sub, marker, where, hits)
            elif marker == UNKNOWN and sub is True:
                result[key] = _apply_mask(None, sub, marker, where, hits)
        return result
    if isinstance(mask, list) and isinstance(value, list):
        return [
            _apply_mask(item, mask[i], marker, f"{path}[{i}]", hits) if i < len(mask) else item
            for i, item in enumerate(value)
        ]
    return value


def _strings(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, str):
        yield value


def import_infrastructure(paths, bindings=None):
    resources, edges, findings = [], [], []
    bindings = bindings or {}

    def add(ident, kind, properties, source, parent=None):
        if any(r["id"] == ident for r in resources):
            raise ValueError("Duplicate infrastructure resource: " + ident)
        resources.append(
            {
                "id": ident,
                "type": kind,
                "properties": properties,
                "evidence": source,
                "parent_id": parent,
            }
        )

    for file_index, path in enumerate(paths):
        path = canonical_existing_file(Path(path))
        text = path.read_text(encoding="utf-8")
        prefix = f"input-{file_index}-"
        # CloudFormation short tags are converted to data, never evaluated.
        text = re.sub(
            r"!(Ref|Sub|GetAtt|Join|If|FindInMap|ImportValue|Select|Split)\s+([^\n]+)",
            lambda m: json.dumps({"intrinsic": m[1], "expression": m[2]}),
            text,
        )

        def scrub(value):
            if isinstance(value, dict):
                return {
                    k: "[REDACTED]"
                    if re.search(r"password|secret|token|api.?key", str(k), re.I)
                    else scrub(v)
                    for k, v in value.items()
                }
            if isinstance(value, list):
                return [scrub(v) for v in value]
            return redact(value) if isinstance(value, str) else value

        try:
            docs = [
                scrub(parse_yaml(part))
                for part in re.split(r"(?m)^---\s*$", text)
                if part.strip()
            ]
        except ValueError as exc:
            raise ValueError("Malformed infrastructure document") from exc
        for doc_index, doc in enumerate(docs):
            if not isinstance(doc, dict):
                raise ValueError("Infrastructure document must be a mapping")
            source = {"reference": evidence_reference(path), "document": doc_index + 1}
            entries, depends = [], {}
            if "planned_values" in doc:
                changes = {
                    c.get("address"): c.get("change") or {}
                    for c in doc.get("resource_changes") or []
                    if isinstance(c, dict)
                }

                def walk(module):
                    for resource in module.get("resources", []):
                        address = resource["address"]
                        change = changes.get(address, {})
                        values, hidden, unknown = resource.get("values", {}), [], []
                        for mask in (resource.get("sensitive_values"), change.get("after_sensitive")):
                            values = _apply_mask(values, mask, SENSITIVE, "", hidden)
                        values = _apply_mask(
                            values, change.get("after_unknown"), UNKNOWN, "", unknown
                        )
                        ident = prefix + slugify(address)
                        if hidden:
                            findings.append(
                                {
                                    "resource": ident,
                                    "message": "Sensitive values masked: "
                                    + ", ".join(sorted(set(hidden))),
                                }
                            )
                        if unknown:
                            findings.append(
                                {
                                    "resource": ident,
                                    "message": "Values unknown until apply: "
                                    + ", ".join(sorted(set(unknown))),
                                }
                            )
                        entries.append((address, resource["type"], values, None))
                    for child in module.get("child_modules", []):
                        walk(child)

                walk(doc["planned_values"].get("root_module", {}))
                if doc.get("resource_changes"):
                    findings.append(
                        {
                            "source": source,
                            "message": "Terraform unknown/sensitive values are not evaluated; review change metadata",
                        }
                    )
            elif "Resources" in doc:
                for name, value in doc["Resources"].items():
                    # Resource-level DependsOn sits beside Properties: deployment ordering.
                    order = value.get("DependsOn", [])
                    depends[name] = [order] if isinstance(order, str) else order
                    entries.append(
                        (
                            name,
                            value.get("Type", "unknown"),
                            value.get("Properties", {}),
                            None,
                        )
                    )
            elif "apiVersion" in doc and "kind" in doc:
                items = doc.get("items", []) if doc["kind"] == "List" else [doc]
                for item in items:
                    meta = item.get("metadata", {})
                    namespace = meta.get("namespace", "default")
                    entries.append(
                        (
                            namespace
                            + "/"
                            + item["kind"]
                            + "/"
                            + meta.get("name", "unnamed"),
                            "kubernetes/" + item["kind"],
                            item.get("spec", {}),
                            namespace,
                        )
                    )
            elif "services" in doc:
                for section in ("networks", "volumes"):
                    for name, value in (doc.get(section) or {}).items():
                        entries.append(
                            (
                                section + "/" + name,
                                "compose/" + section.rstrip("s"),
                                value or {},
                                "compose",
                            )
                        )
                for name, value in doc["services"].items():
                    entries.append((name, "compose/service", value or {}, "compose"))
            else:
                raise ValueError(
                    "Expected Terraform plan, CloudFormation/CDK template, Kubernetes/rendered Helm or Compose"
                )
            names = {name: prefix + slugify(name) for name, _, _, _ in entries}
            for name, kind, props, parent in entries:
                ident = names[name]
                add(ident, kind, props, source, parent)
                serialized = json.dumps(props)
                if (
                    "${" in serialized
                    or '"Ref"' in serialized
                    or '"Fn::' in serialized
                    or '"intrinsic"' in serialized
                ):
                    findings.append(
                        {
                            "resource": ident,
                            "message": "Contains unresolved expression; no values or placement guessed",
                        }
                    )

                def refs(value):
                    if isinstance(value, dict):
                        for k, v in value.items():
                            if k in {
                                "Ref",
                                "DependsOn",
                                "depends_on",
                                "depends_on_resource",
                            }:
                                for item in v if isinstance(v, list) else [v]:
                                    if isinstance(item, str) and item in names:
                                        yield names[item]
                            yield from refs(v)
                    elif isinstance(value, list):
                        for item in value:
                            yield from refs(item)

                for target in set(refs(props)):
                    edges.append(
                        {
                            "source_id": ident,
                            "destination_id": target,
                            "kind": "explicit-reference",
                            "evidence": source,
                        }
                    )
                for dep in depends.get(name, []):
                    if isinstance(dep, str) and dep in names:
                        edges.append(
                            {
                                "source_id": ident,
                                "destination_id": names[dep],
                                "kind": "depends-on",
                                "evidence": source,
                            }
                        )
                if kind == "compose/service":
                    dependencies = props.get("depends_on", [])
                    for dep in dependencies:
                        if dep in names:
                            edges.append(
                                {
                                    "source_id": ident,
                                    "destination_id": names[dep],
                                    "kind": "depends-on",
                                    "evidence": source,
                                }
                            )
                    for network in props.get("networks", []):
                        if "networks/" + network in names:
                            edges.append(
                                {
                                    "source_id": ident,
                                    "destination_id": names["networks/" + network],
                                    "kind": "network-membership",
                                    "evidence": source,
                                }
                            )
                if kind == "kubernetes/Service":
                    findings.append(
                        {
                            "resource": ident,
                            "message": "Service selector requires workload label resolution; review before binding",
                        }
                    )
    resource_ids = {r["id"] for r in resources}
    for resource in resources:
        props = resource["properties"]
        # Exact values only: "vpc-1" must not match "vpc-123" or free text containing it.
        scalars = set(_strings(props))
        for target in resources:
            if resource["id"] == target["id"]:
                continue
            if resource["type"].startswith(("aws_", "google_")):
                # Terraform resolved IDs are matched only against declared resource IDs.
                value = target["properties"].get("id")
                if isinstance(value, str) and value and value in scalars:
                    edges.append(
                        {
                            "source_id": resource["id"],
                            "destination_id": target["id"],
                            "kind": "resolved-resource-id",
                            "evidence": resource["evidence"],
                        }
                    )
            if (
                resource["type"] == "kubernetes/Service"
                and target["parent_id"] == resource["parent_id"]
            ):
                selector = props.get("selector", {})
                labels = (
                    target["properties"]
                    .get("template", {})
                    .get("metadata", {})
                    .get("labels", {})
                )
                if selector and selector.items() <= labels.items():
                    edges.append(
                        {
                            "source_id": resource["id"],
                            "destination_id": target["id"],
                            "kind": "selector",
                            "evidence": resource["evidence"],
                        }
                    )
    if set(bindings) - resource_ids:
        raise ValueError("Binding refers to unknown resource")
    by_id = {r["id"]: r for r in resources}
    for edge in edges:
        child, parent = by_id[edge["source_id"]], by_id[edge["destination_id"]]
        if child["type"] in {
            "aws_subnet",
            "AWS::EC2::Subnet",
            "google_compute_subnetwork",
        } and parent["type"] in {
            "aws_vpc",
            "AWS::EC2::VPC",
            "google_compute_network",
        }:
            child["parent_id"] = parent["id"]
    return {
        "schema_version": "architecture-topology/v1",
        "resources": resources,
        "relationships": edges,
        "bindings": bindings,
        "findings": findings,
    }


def topology_plan(topology):
    return {
        "schema_version": "architecture-plan/v1",
        "system": {
            "name": "Imported Infrastructure",
            "description": "Reviewable infrastructure candidates",
            "classification": "Internal",
            "scope": "Imported declarations; ownership requires review",
        },
        "containers": [
            {
                "name": r["id"],
                "description": r["type"],
                "technology": r["type"],
                "evidence": r["evidence"]["reference"],
                "status": "inferred",
            }
            for r in topology["resources"]
        ],
        "flows": [
            {
                "from": e["source_id"],
                "to": e["destination_id"],
                "description": e["kind"],
                "evidence": e["evidence"]["reference"],
                "status": "inferred",
            }
            for e in topology["relationships"]
        ],
        "assumptions": [],
        "gaps": [f.get("message", "") for f in topology["findings"]],
    }
