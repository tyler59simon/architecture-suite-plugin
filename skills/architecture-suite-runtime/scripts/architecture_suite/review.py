"""Plan readiness review: which C4 levels can render, and what would make the plan sounder.

Read-only and deterministic. It reuses lint, compile and model validation and never edits
or completes a plan; each finding carries a question for the person who knows the system.
"""

from __future__ import annotations
import re
from .model import CLAIM_STATUSES, project_model, slugify, validate_model
from .plan import ADVISORY, _entries, compile_plan, errors, lint_plan

LEVELS = ("system", "container", "component", "code")
PROFILES = dict(zip(LEVELS, ("context", "container", "component", "code")))
VIEW_LEVELS = {profile: level for level, profile in PROFILES.items()}
ELEMENT_LEVELS = {
    "system": "system",
    "person": "system",
    "software_system": "system",
    "container": "container",
    "component": "component",
    "code": "code",
}
CROWDED_VIEW = 35  # boxes; matches the layout readability advisory
# Values left over from assets/architecture-plan-template.md or common stand-ins.
PLACEHOLDER = re.compile(r"(replace with\b|unspecified$|tbd$|todo$|\?+$)", re.IGNORECASE)


def _percent(part: int, whole: int) -> int | None:
    return round(100 * part / whole) if whole else None


def _finding(code, message, where="", level="plan", question="", severity=ADVISORY):
    return {
        "code": code,
        "message": message,
        "where": where,
        "severity": severity,
        "level": level,
        "question": question,
    }


def _lint_question(code: str, where: str, flows: list) -> str:
    if code == "unevidenced-element":
        return f"What document, file or decision shows {where!r}, or is it only proposed?"
    if code == "unevidenced-flow" and where.isdigit() and int(where) < len(flows):
        flow = flows[int(where)]
        if isinstance(flow, dict):
            return (
                f"What shows that {flow.get('from')!r} -> {flow.get('to')!r} happens, "
                "or is it proposed?"
            )
    return ""


def review_plan(plan: dict, gcp_icon_style: str | None = None) -> dict:
    """Return readiness per level, coverage, claim mix and review findings for a plan."""
    lint = lint_plan(plan, gcp_icon_style)
    items = (
        [(i, t) for i, t, _ in _entries(plan) if isinstance(i, dict)]
        if isinstance(plan, dict)
        else []
    )
    level_of = {i.get("name"): ELEMENT_LEVELS[t] for i, t in items}
    flows = plan.get("flows") if isinstance(plan, dict) else None
    flows = flows if isinstance(flows, list) else []
    findings = [
        _finding(
            f.code,
            f.message,
            f.where,
            level_of.get(f.where, "plan"),
            _lint_question(f.code, f.where, flows),
            f.severity,
        )
        for f in lint
    ]
    review = {
        "operation": "plan-review",
        "ok": not errors(lint),
        "levels": {},
        "ready_levels": [],
        "max_level": None,
        "coverage": {},
        "claim_status": {},
        "findings": findings,
        "gaps": [],
        "assumptions": [],
    }
    if errors(lint):
        reason = f"{len(errors(lint))} plan-lint error(s); fix them first"
        review["levels"] = {lvl: {"status": "blocked", "reasons": [reason]} for lvl in LEVELS}
        review["finding_count"] = len(findings)
        return review
    model, fidelity = compile_plan(plan, gcp_icon_style)  # lint is clean, so this compiles

    # Readiness: the same projection and validation `plan-render --level <level>` applies.
    for lvl in LEVELS:
        problems = validate_model(project_model(model, PROFILES[lvl]), PROFILES[lvl])
        review["levels"][lvl] = {
            "status": "blocked" if problems else "ready",
            "reasons": [p["message"] for p in problems[:5]],
        }
    if "deployment" in model:
        placed = model["deployment"].get("placements", [])
        reasons = [] if placed else ["deployment has no placements"]
        if review["levels"]["container"]["status"] != "ready":
            reasons.append("the container level must be ready first")
        review["levels"]["deployment"] = {
            "status": "blocked" if reasons else "ready",
            "reasons": reasons,
        }
    review["ready_levels"] = [k for k, v in review["levels"].items() if v["status"] == "ready"]
    for lvl in LEVELS:
        if review["levels"][lvl]["status"] != "ready":
            break
        review["max_level"] = lvl

    elements = [e for e in model["elements"] if e["type"] != "software_system" or e.get("external")]
    owned = [e for e in elements if e["type"] in {"container", "component"}]
    review["coverage"] = {
        "elements": len(elements),
        "elements_with_evidence_percent": _percent(
            sum(bool(e["evidence_ids"]) for e in elements), len(elements)
        ),
        "flows": len(flows),
        "flows_with_evidence_percent": _percent(
            sum(bool(f.get("evidence")) for f in flows), len(flows)
        ),
        "containers_and_components_with_technology_percent": _percent(
            sum(bool(e.get("technology")) for e in owned), len(owned)
        ),
    }
    claims = list(elements) + [{"status": f["status"]} if "status" in f else {} for f in flows]
    review["claim_status"] = {
        status: sum(c.get("status") == status for c in claims) for status in CLAIM_STATUSES
    } | {"unstated": sum("status" not in c for c in claims)}
    review["gaps"] = list(plan.get("gaps") or [])
    review["assumptions"] = list(plan.get("assumptions") or [])

    add = findings.append
    if not plan.get("people"):
        add(
            _finding(
                "no-people",
                "No people: the system context shows no users or operators",
                "people",
                "system",
                "Who uses, operates or administers this system?",
            )
        )
    if not plan.get("external_systems"):
        add(
            _finding(
                "no-external-systems",
                "No external systems: confirm the system depends on nothing outside your ownership",
                "external_systems",
                "system",
                "Which systems outside your ownership does it call, or receive data from?",
            )
        )
    parents = {e["id"]: e.get("parent_id") for e in model["elements"]}
    touched = set()
    for flow in flows:
        for end in (flow["from"], flow["to"]):
            node = slugify(end)
            while node and node not in touched:  # a flow on a part touches its parents
                touched.add(node)
                node = parents.get(node)
    for e in elements:
        if e["type"] != "code" and e["id"] not in touched:
            add(
                _finding(
                    "isolated-element",
                    "No flow reaches this element or its parts, so it floats unconnected",
                    e["name"],
                    ELEMENT_LEVELS[e["type"]],
                    f"Who or what does {e['name']!r} talk to, and why?",
                )
            )
    for e in owned:
        if not e.get("technology"):
            add(
                _finding(
                    "missing-technology",
                    "No technology label",
                    e["name"],
                    ELEMENT_LEVELS[e["type"]],
                    f"What is {e['name']!r} built with or run on (language, framework, product)?",
                )
            )
    for e in elements:
        if e.get("status") == "observed" and not e["evidence_ids"]:
            add(
                _finding(
                    "observed-without-evidence",
                    "Marked observed but cites no evidence; the claim is stronger than its support",
                    e["name"],
                    ELEMENT_LEVELS[e["type"]],
                    f"Where can {e['name']!r} be seen, or should it be inferred or proposed?",
                )
            )
    for i, flow in enumerate(flows):
        if flow.get("status") == "observed" and not flow.get("evidence"):
            add(
                _finding(
                    "observed-without-evidence",
                    "Flow marked observed but cites no evidence",
                    str(i),
                    "plan",
                    f"What shows that {flow['from']!r} -> {flow['to']!r} happens?",
                )
            )
    for item, typ in items:
        description = item.get("description")
        if typ in {"system", "code"} or not isinstance(description, str):
            continue
        if len(description.split()) < 3 or description.strip().lower() == item["name"].lower():
            add(
                _finding(
                    "thin-description",
                    "Description is too short to say what the element is responsible for",
                    item["name"],
                    ELEMENT_LEVELS[typ],
                    f"In one sentence, what does {item['name']!r} do?",
                )
            )
    for item, typ in items:
        for key in ("description", "technology", "scope", "evidence"):
            values = item.get(key)
            for value in [values] if isinstance(values, str) else values or []:
                if isinstance(value, str) and PLACEHOLDER.match(value.strip()):
                    add(
                        _finding(
                            "placeholder",
                            f"{key} still holds template placeholder text",
                            item["name"],
                            ELEMENT_LEVELS[typ],
                            f"What is the real {key} of {item['name']!r}?",
                        )
                    )
    if "deployment" in model:
        placed = {p["element_id"] for p in model["deployment"].get("placements", [])}
        for e in model["elements"]:
            if (
                e["type"] == "container"
                and e["id"] not in placed
                and not any(parents.get(p) == e["id"] for p in placed)
            ):
                add(
                    _finding(
                        "unplaced-container",
                        "Container has no deployment placement",
                        e["name"],
                        "deployment",
                        f"Where does {e['name']!r} run (account or project, region, network)?",
                    )
                )
    for view in model["views"]:
        if len(view["element_ids"]) > CROWDED_VIEW:
            add(
                _finding(
                    "crowded-view",
                    f"{len(view['element_ids'])} boxes in one view; split it or use groups",
                    view["id"],
                    VIEW_LEVELS.get(view["type"], "plan"),
                )
            )
    for dropped in fidelity.dropped:
        add(_finding("dropped-flow", dropped, dropped.split(":")[0]))
    review["finding_count"] = len(findings)
    return review


def review_exit_code(review: dict, strict: bool = False) -> int:
    """1 when the plan has lint errors, or under --strict when anything was found."""
    return 1 if not review["ok"] or (strict and review["findings"]) else 0


def render_review_markdown(review: dict) -> str:
    lines = ["# Plan review", "", "| Level | Status | Why |", "| --- | --- | --- |"]
    for level, state in review["levels"].items():
        why = "; ".join(state["reasons"]) or "-"
        lines.append(f"| {level} | {state['status']} | {why} |")
    lines += ["", f"Deepest ready C4 level: {review['max_level'] or 'none'}", ""]
    if review["coverage"]:
        lines += ["## Coverage", ""]
        lines += [
            f"- {k.replace('_', ' ')}: {v if v is not None else '-'}"
            for k, v in review["coverage"].items()
        ]
        lines += ["", "## Claim status", ""]
        lines += [f"- {k}: {v}" for k, v in review["claim_status"].items()]
        lines.append("")
    lines += ["## Findings", ""]
    if not review["findings"]:
        lines += ["None.", ""]
    for level in (*LEVELS, "deployment", "plan"):
        group = [f for f in review["findings"] if f["level"] == level]
        if group:
            lines += [f"### {level}", ""]
            for f in group:
                where = f" ({f['where']})" if f["where"] else ""
                lines.append(f"- **{f['severity']}: {f['code']}**{where}: {f['message']}")
                if f["question"]:
                    lines.append(f"  - Ask: {f['question']}")
            lines.append("")
    for title, key in (("Open gaps", "gaps"), ("Assumptions", "assumptions")):
        if review[key]:
            lines += [f"## {title}", ""] + [f"- {x}" for x in review[key]] + [""]
    return "\n".join(lines)
