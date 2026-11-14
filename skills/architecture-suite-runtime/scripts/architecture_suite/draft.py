"""Editable plan serialization, not diagram generation."""

import yaml


def render_plan(plan: dict) -> str:
    return (
        "# Architecture plan\n\nDrafted by bounded static analysis. Review candidate boundaries and gaps before publishing.\n\n```yaml\n"
        + yaml.safe_dump(plan, allow_unicode=True, sort_keys=False)
        + "```\n"
    )
