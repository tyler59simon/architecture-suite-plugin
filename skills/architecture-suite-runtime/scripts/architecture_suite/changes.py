"""Deterministic architecture differences and declarative dependency rules."""

from copy import deepcopy
import json
import hashlib


def _sections(model):
    return {
        "elements": model.get("elements", []),
        "relationships": model.get("relationships", []),
        "nodes": model.get("deployment", {}).get("nodes", []),
        "placements": model.get("deployment", {}).get("placements", []),
    }


def diff_models(before, after, identities=None):
    before = deepcopy(before)
    aliases = identities or {}
    if len(set(aliases.values())) != len(aliases):
        raise ValueError("Identity mappings must be one-to-one")
    for values in _sections(before).values():
        for item in values:
            for key in (
                "id",
                "parent_id",
                "source_id",
                "destination_id",
                "element_id",
                "node_id",
            ):
                if key in item:
                    item[key] = aliases.get(item[key], item[key])
    changes = []
    ignored = {"evidence_ids", "confidence", "flow_ids"}
    for section, old_items in _sections(before).items():

        def index(items):
            result = {}
            for value in items:
                # Arrow identity follows endpoints, not generated ordinal IDs.
                key = (
                    (value.get("source_id"), value.get("destination_id"))
                    if section == "relationships"
                    else (value.get("element_id"), value.get("node_id"))
                    if section == "placements"
                    else value["id"]
                )
                clean = {
                    k: v
                    for k, v in value.items()
                    if k not in ignored
                    and not (section == "relationships" and k == "id")
                }
                if key in result and result[key] != clean:
                    key = str(key) + json.dumps(clean, sort_keys=True)
                result[key] = clean
            return result

        old, new = index(old_items), index(_sections(after)[section])
        for key in sorted(set(old) | set(new), key=str):
            if old.get(key) != new.get(key):
                changes.append(
                    {
                        "section": section,
                        "id": str(key),
                        "kind": "added"
                        if key not in old
                        else "removed"
                        if key not in new
                        else "changed",
                        "before": old.get(key),
                        "after": new.get(key),
                    }
                )
    return {
        "schema_version": "architecture-diff/v1",
        "changes": changes,
        "changed": bool(changes),
    }


def check_rules(model, config, baseline=None):
    if (
        not isinstance(config, dict)
        or set(config) - {"schema_version", "rules"}
        or config.get("schema_version", "architecture-rules/v1")
        != "architecture-rules/v1"
        or not isinstance(config.get("rules"), list)
    ):
        raise ValueError("Expected architecture-rules/v1 with a rules array")
    elements = {e["id"]: e for e in model["elements"]}

    def matches(element, selector):
        if not isinstance(selector, dict) or set(selector) - {"ids", "types", "tags"}:
            raise ValueError("Selectors accept ids, types and tags only")
        if any(
            not isinstance(v, list) or not all(isinstance(x, str) for x in v)
            for v in selector.values()
        ):
            raise ValueError("Selector values must be string arrays")
        return all(
            element.get("id") in v
            if k == "ids"
            else element.get("type") in v
            if k == "types"
            else set(v) <= set(element.get("tags", []))
            for k, v in selector.items()
        )

    findings, seen = [], set()
    ids = set()
    for rule in config["rules"]:
        if (
            not isinstance(rule, dict)
            or set(rule) - {"id", "effect", "source", "destination", "severity"}
            or not isinstance(rule.get("id"), str)
            or rule["id"] in ids
            or rule.get("effect") not in {"allow", "deny"}
            or rule.get("severity", "error") not in {"error", "warning"}
        ):
            raise ValueError("Invalid or duplicate dependency rule")
        ids.add(rule["id"])
        matches({}, rule.get("source", {}))
        matches({}, rule.get("destination", {}))
        for rel in model["relationships"]:
            source, dest = elements[rel["source_id"]], elements[rel["destination_id"]]
            if matches(source, rule.get("source", {})):
                allowed = matches(dest, rule.get("destination", {}))
                if (rule["effect"] == "deny" and allowed) or (
                    rule["effect"] == "allow" and not allowed
                ):
                    identity = (rule["id"], source["id"], dest["id"])
                    if identity in seen:
                        continue
                    seen.add(identity)
                    fingerprint = hashlib.sha256(
                        json.dumps(identity).encode()
                    ).hexdigest()
                    findings.append(
                        {
                            "rule": rule["id"],
                            "source": source["id"],
                            "destination": dest["id"],
                            "severity": rule.get("severity", "error"),
                            "fingerprint": fingerprint,
                            "existing": fingerprint
                            in set((baseline or {}).get("fingerprints", [])),
                        }
                    )
    return {
        "schema_version": "architecture-check/v1",
        "findings": findings,
        "fingerprints": sorted(f["fingerprint"] for f in findings),
        "new_errors": sum(
            f["severity"] == "error" and not f["existing"] for f in findings
        ),
    }


def markdown_report(report):
    return (
        "# Architecture report\n\n```json\n"
        + json.dumps(report, indent=2, ensure_ascii=False)
        + "\n```\n"
    )
