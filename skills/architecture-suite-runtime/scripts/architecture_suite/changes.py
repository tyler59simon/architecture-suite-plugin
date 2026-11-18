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


def _identities(before, after, identities):
    aliases = {} if identities is None else identities
    if not isinstance(aliases, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in aliases.items()
    ):
        raise ValueError("Identity mappings must map string IDs to string IDs")
    if len(set(aliases.values())) != len(aliases):
        raise ValueError("Identity mappings must be one-to-one")

    def ids(model):
        sections = _sections(model)
        return {item.get("id") for item in sections["elements"] + sections["nodes"]}

    # A mapping that names nothing would be silently ignored; reject it instead.
    unknown = sorted(set(aliases) - ids(before))
    if unknown:
        raise ValueError("Identity mappings name unknown before IDs: " + ", ".join(unknown))
    unknown = sorted(set(aliases.values()) - ids(after))
    if unknown:
        raise ValueError("Identity mappings name unknown after IDs: " + ", ".join(unknown))
    return aliases


def diff_models(before, after, identities=None):
    aliases = _identities(before, after, identities)
    before = deepcopy(before)
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
                    f"{value.get('source_id')}->{value.get('destination_id')}"
                    if section == "relationships"
                    else f"{value.get('element_id')}->{value.get('node_id')}"
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
                    key = str(key) + " " + json.dumps(clean, sort_keys=True)
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


def _baseline_fingerprints(baseline):
    if baseline is None:
        return set()
    if (
        not isinstance(baseline, dict)
        or baseline.get("schema_version", "architecture-baseline/v1")
        != "architecture-baseline/v1"
        or not isinstance(baseline.get("fingerprints"), list)
        or not all(isinstance(f, str) for f in baseline["fingerprints"])
    ):
        raise ValueError("Expected architecture-baseline/v1 with a fingerprints string array")
    return set(baseline["fingerprints"])


def check_rules(model, config, baseline=None):
    if (
        not isinstance(config, dict)
        or set(config) - {"schema_version", "rules"}
        or config.get("schema_version", "architecture-rules/v1")
        != "architecture-rules/v1"
        or not isinstance(config.get("rules"), list)
    ):
        raise ValueError("Expected architecture-rules/v1 with a rules array")
    accepted = _baseline_fingerprints(baseline)
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
    # A flow is projected into every view (container, component, code). Visit the most
    # specific views first and report each flow once per rule, at its finest level.
    depth = {"code": 0, "component": 1, "container": 2, "context": 3}
    level = {
        rid: depth.get(view.get("type"), 4)
        for view in model.get("views", [])
        for rid in view.get("relationship_ids", [])
    }
    relationships = sorted(model["relationships"], key=lambda r: level.get(r.get("id"), 4))
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
        reported = set()
        for rel in relationships:
            source, dest = elements[rel["source_id"]], elements[rel["destination_id"]]
            if matches(source, rule.get("source", {})):
                allowed = matches(dest, rule.get("destination", {}))
                if (rule["effect"] == "deny" and allowed) or (
                    rule["effect"] == "allow" and not allowed
                ):
                    identity = (rule["id"], source["id"], dest["id"])
                    flows = set(rel.get("flow_ids") or [])
                    if identity in seen or (flows and flows <= reported):
                        continue
                    seen.add(identity)
                    reported |= flows
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
                            "existing": fingerprint in accepted,
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


def _text(value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return " ".join(text.split())


def _table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(_text(v).replace("|", "\\|") for v in row) + " |" for row in rows]
    return "\n".join(lines)


def _count(n, noun):
    return f"{n} {noun}" + ("" if n == 1 else "s")


def markdown_report(report):
    """A readable summary of a diff or check report; the JSON file holds every field."""
    if report["schema_version"] == "architecture-diff/v1":
        changes = report["changes"]
        if not changes:
            return "# Architecture diff\n\nNo architecture changes.\n"
        counts = {k: sum(c["kind"] == k for c in changes) for k in ("added", "changed", "removed")}
        rows = []
        for c in changes:
            before, after = c["before"] or {}, c["after"] or {}
            fields = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
            details = (
                "; ".join(f"{k}: {_text(before.get(k))} -> {_text(after.get(k))}" for k in fields)
                if c["kind"] == "changed"
                else ""
            )
            rows.append((c["section"], c["id"], c["kind"], details))
        return (
            "# Architecture diff\n\n"
            + f"{_count(len(changes), 'change')}: {counts['added']} added, {counts['changed']} changed, "
            + f"{counts['removed']} removed.\n\n"
            + _table(("Section", "ID", "Change", "Details"), rows)
            + "\n"
        )
    findings = report["findings"]
    if not findings:
        return "# Architecture check\n\nNo rule findings.\n"
    rows = [
        (f["rule"], f["source"], f["destination"], f["severity"],
         "accepted" if f["existing"] else "new")
        for f in findings
    ]
    return (
        "# Architecture check\n\n"
        + f"{_count(len(findings), 'finding')}, {_count(report['new_errors'], 'new error')}.\n\n"
        + _table(("Rule", "Source", "Destination", "Severity", "Status"), rows)
        + "\n"
    )
