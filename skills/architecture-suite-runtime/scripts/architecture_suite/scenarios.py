"""Structured scenarios independent of canonical C4 views."""

from .scene import Scene, Box, Edge
from .style import Label, TextLine, wrap_to_width

GROUPS = {"alt", "opt", "loop", "par"}


def validate_scenario(scenario, model):
    if (
        not isinstance(scenario, dict)
        or scenario.get("schema_version") != "architecture-scenario/v1"
        or not isinstance(scenario.get("name"), str)
        or not isinstance(scenario.get("participants"), list)
        or not scenario["participants"]
        or len(set(scenario["participants"])) != len(scenario["participants"])
    ):
        raise ValueError("Expected scenario/v1 name and unique participants")
    ids = {e["id"] for e in model["elements"]}
    if not set(scenario["participants"]) <= ids:
        raise ValueError("Unknown scenario participant")

    def walk(steps, depth):
        if depth > 12 or not isinstance(steps, list) or not steps:
            raise ValueError("Scenario steps must be nonempty; nesting limit 12")
        for step in steps:
            if not isinstance(step, dict):
                raise ValueError("Step must be a mapping")
            if step.get("type", "message") in {"message", "response"}:
                if (
                    set(step) - {"type", "from", "to", "description"}
                    or step.get("from") not in scenario["participants"]
                    or step.get("to") not in scenario["participants"]
                    or not isinstance(step.get("description"), str)
                    or not step["description"].strip()
                ):
                    raise ValueError("Invalid message")
            elif step.get("type") in GROUPS:
                if (
                    set(step) - {"type", "condition", "steps", "branches"}
                    or not isinstance(step.get("condition"), str)
                    or not step["condition"].strip()
                ):
                    raise ValueError("Group requires a condition")
                walk(step.get("steps"), depth + 1)
                branches = step.get("branches", [])
                if (
                    not isinstance(branches, list)
                    or branches
                    and step["type"] not in {"alt", "par"}
                ):
                    raise ValueError("Branches require alt or par")
                for branch in branches:
                    if (
                        not isinstance(branch, dict)
                        or set(branch) - {"condition", "steps"}
                        or not isinstance(branch.get("condition"), str)
                        or not branch["condition"].strip()
                    ):
                        raise ValueError("Invalid branch")
                    walk(branch.get("steps"), depth + 1)
            else:
                raise ValueError("Unknown scenario step")

    walk(scenario.get("steps"), 0)
    return scenario


def scenario_mermaid(scenario, model):
    validate_scenario(scenario, model)
    from .renderers import _quoted

    names = {e["id"]: e["name"] for e in model["elements"]}
    aliases = {p: f"p{i}" for i, p in enumerate(scenario["participants"])}

    def clean(text):
        return _quoted(text)[1:-1].replace(";", ";")

    lines = ["sequenceDiagram"] + [
        f"  participant {aliases[p]} as {clean(names[p])}" for p in aliases
    ]

    def walk(steps, indent):
        for step in steps:
            kind = step.get("type", "message")
            if kind in GROUPS:
                lines.append(indent + kind + " " + clean(step["condition"]))
                walk(step["steps"], indent + "  ")
                for branch in step.get("branches", []):
                    lines.append(
                        indent
                        + ("else" if kind == "alt" else "and")
                        + " "
                        + clean(branch["condition"])
                    )
                    walk(branch["steps"], indent + "  ")
                lines.append(indent + "end")
            else:
                lines.append(
                    indent
                    + aliases[step["from"]]
                    + ("-->>" if kind == "response" else "->>")
                    + aliases[step["to"]]
                    + ": "
                    + clean(step["description"])
                )

    walk(scenario["steps"], "  ")
    return "\n".join(lines) + "\n"


def scenario_scene(scenario, model):
    validate_scenario(scenario, model)
    names = {e["id"]: e["name"] for e in model["elements"]}
    width = max(660, 320 * len(scenario["participants"]) + 96)
    scene = Scene(
        scenario["name"],
        width,
        400,
        title_lines=wrap_to_width(scenario["name"], width - 96, 22),
        content_top=120,
    )
    positions = {p: 208 + i * 320 for i, p in enumerate(scenario["participants"])}
    for p, x in positions.items():
        lab = Label([TextLine(t) for t in wrap_to_width(names[p], 230)])
        scene.boxes.append(
            Box(p, "card", x - 130, 120, 260, max(80, lab.height + 32), lab)
        )
    y = max(b.y + b.height for b in scene.boxes) + 60

    def walk(steps, parent=None):
        nonlocal y
        for step in steps:
            kind = step.get("type", "message")
            if kind in GROUPS:
                ident = "group-" + str(len(scene.boxes))
                top = y
                y += 70
                box = Box(
                    ident,
                    "frame",
                    55,
                    top,
                    width - 110,
                    100,
                    Label(
                        [
                            TextLine(kind + ": " + t)
                            for t in wrap_to_width(step["condition"], width - 180)
                        ]
                    ),
                    parent,
                )
                scene.boxes.append(box)
                walk(step["steps"], ident)
                for branch in step.get("branches", []):
                    scene.boxes.append(
                        Box(
                            "branch-" + str(len(scene.boxes)),
                            "panel-title",
                            75,
                            y,
                            width - 150,
                            60,
                            Label(
                                [
                                    TextLine(t)
                                    for t in wrap_to_width(
                                        ("else: " if kind == "alt" else "and: ")
                                        + branch["condition"],
                                        width - 180,
                                    )
                                ]
                            ),
                            ident,
                        )
                    )
                    y += 80
                    walk(branch["steps"], ident)
                y += 30
                box.height = y - top
            else:
                x1, x2 = positions[step["from"]], positions[step["to"]]
                lab = Label(
                    [
                        TextLine(t, 11)
                        for t in wrap_to_width(step["description"], 240, 11)
                    ]
                )
                if x1 == x2:
                    points = [(x1, y), (x1 + 110, y), (x1 + 110, y + 60), (x1, y + 60)]
                else:
                    points = [(x1, y), (x2, y)]
                box = Box(
                    "message-label-" + str(len(scene.edges)),
                    "edge-label",
                    (x1 + x2) / 2 - 130,
                    y - lab.height - 20,
                    260,
                    lab.height + 10,
                    lab,
                )
                scene.edges.append(
                    Edge(
                        "message-" + str(len(scene.edges)),
                        step["from"],
                        step["to"],
                        points,
                        box,
                        kind=kind,
                    )
                )
                y += lab.height + 110

    walk(scenario["steps"])
    # Lifelines are separate visual strokes and never dependencies in the model.
    for p, x in positions.items():
        scene.edges.insert(
            0, Edge("lifeline-" + p, p, p, [(x, 200), (x, y)], kind="lifeline")
        )
    scene.height = y + 180
    scene.key_y = y + 50
    return scene
