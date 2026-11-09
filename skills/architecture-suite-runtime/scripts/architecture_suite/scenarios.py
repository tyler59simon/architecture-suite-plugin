"""Structured scenarios independent of canonical C4 views."""

from .scene import Scene, Box, Edge
from .style import Label, TextLine, wrap_to_width

GROUPS = {"alt", "opt", "loop", "par"}
# Sequence spacing: between messages, around frames, inside frames, and per nesting level.
STEP_GAP, FRAME_GAP, FRAME_PAD, FRAME_INSET = 90, 40, 20, 12


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
        # ";" ends a sequence statement; encode it between quoted parts so the entity
        # codes _quoted emits keep their own semicolons.
        return "#59;".join(_quoted(part)[1:-1] for part in str(text).split(";"))

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
    # y is the bottom of the content placed so far; every step starts below it with
    # a gap, so frames, branch dividers and message labels never share a line.
    y = max(b.y + b.height for b in scene.boxes)

    def walk(steps, depth=0, parent=None):
        nonlocal y
        previous = None
        for step in steps:
            kind = step.get("type", "message")
            if previous is None:
                y += FRAME_PAD if parent else FRAME_GAP
            elif kind in GROUPS or previous in GROUPS:
                y += FRAME_GAP
            else:
                y += STEP_GAP
            previous = kind
            if kind in GROUPS:
                ident = "group-" + str(len(scene.boxes))
                # Nested frames are inset per depth so every level stays visible.
                left = 55 + depth * FRAME_INSET
                inner = width - 2 * left
                top = y
                title = Label(
                    [
                        TextLine(kind + ": " + t)
                        for t in wrap_to_width(step["condition"], inner - 70)
                    ]
                )
                box = Box(ident, "frame", left, top, inner, 0, title, parent)
                scene.boxes.append(box)
                y = top + 10 + title.height
                walk(step["steps"], depth + 1, ident)
                for branch in step.get("branches", []):
                    y += FRAME_PAD
                    scene.edges.append(
                        Edge(
                            "divider-" + str(len(scene.edges)),
                            ident,
                            ident,
                            [(left, y), (left + inner, y)],
                            kind="lifeline",
                        )
                    )
                    lab = Label(
                        [
                            TextLine(t)
                            for t in wrap_to_width(
                                ("else: " if kind == "alt" else "and: ")
                                + branch["condition"],
                                inner - 70,
                            )
                        ]
                    )
                    scene.boxes.append(
                        Box(
                            "branch-" + str(len(scene.boxes)),
                            "panel-title",
                            left + 20,
                            y + 4,
                            inner - 40,
                            lab.height + 24,
                            lab,
                            ident,
                        )
                    )
                    y += lab.height + 28
                    walk(branch["steps"], depth + 1, ident)
                y += FRAME_PAD
                box.height = y - top
            else:
                x1, x2 = positions[step["from"]], positions[step["to"]]
                lab = Label(
                    [
                        TextLine(t, 11)
                        for t in wrap_to_width(step["description"], 240, 11)
                    ]
                )
                box = Box(
                    "message-label-" + str(len(scene.edges)),
                    "edge-label",
                    (x1 + x2) / 2 - 130,
                    y,
                    260,
                    lab.height + 10,
                    lab,
                )
                y += lab.height + 20
                if x1 == x2:
                    points = [(x1, y), (x1 + 110, y), (x1 + 110, y + 60), (x1, y + 60)]
                else:
                    points = [(x1, y), (x2, y)]
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
                y = points[-1][1]

    walk(scenario["steps"])
    y += STEP_GAP
    # Lifelines are separate visual strokes and never dependencies in the model.
    for p, x in positions.items():
        scene.edges.insert(
            0, Edge("lifeline-" + p, p, p, [(x, 200), (x, y)], kind="lifeline")
        )
    scene.height = y + 180
    scene.key_y = y + 50
    return scene
