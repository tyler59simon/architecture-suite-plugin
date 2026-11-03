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
