"""Evidence and uncertainty accompany the diagram package."""

import json
from .safety import safe_text


def render_architecture_report(model: dict, *, verification: dict | None = None) -> str:
    lines = [
        "# " + safe_text(model["system"]["name"]),
        "",
        safe_text(model["system"]["classification"]),
        "",
        safe_text(model["system"]["scope"]),
        "",
        "## Evidence",
        "",
    ]
    for e in model["evidence"]:
        lines.append(
            f"- {safe_text(e['id'])}: {safe_text(e.get('reference', ''))}:{e.get('line', '')} — {safe_text(e.get('excerpt', ''))}"
        )
    for heading, key in (("Assumptions", "assumptions"), ("Gaps", "gaps")):
        lines.extend(["", "## " + heading, ""])
        lines.extend("- " + safe_text(v) for v in model.get(key, []))
    elements, relationships = model["elements"], model.get("relationships", [])
    if any("status" in item for item in elements + relationships):
        lines.extend(["", "## Claim status", ""])
        for status in ("observed", "inferred", "proposed", "unknown", None):
            counts = [
                sum(item.get("status") == status for item in items)
                for items in (elements, relationships)
            ]
            if any(counts):
                lines.append(
                    f"- {status or 'not stated'}: {counts[0]} elements, "
                    f"{counts[1]} relationships"
                )
    if verification is not None:
        lines.extend(
            [
                "",
                "## Layout verification",
                "",
                "```json",
                json.dumps(verification, indent=2),
                "```",
            ]
        )
    return "\n".join(lines) + "\n"
