"""Five overview styles derived from the canonical C4 model, never a fifth C4 level."""

from copy import deepcopy
from .model import ELEMENT_TYPE_DEPTH
from .c4_layout import build_view_scene_elk, choose_scene
from .scene import Scene

OVERVIEW_STYLES = (
    "executive",
    "progressive",
    "hierarchy",
    "small-multiples",
    "complete",
)


def normalize_overview_styles(styles=None) -> tuple[str, ...]:
    if styles is None:
        return ("progressive",)
    if isinstance(styles, str):
        styles = [styles]
    requested = [s.strip() for v in styles for s in v.split(",") if s.strip()]
    if not requested or set(requested) - set(OVERVIEW_STYLES) - {"all"}:
        raise ValueError("Unknown or empty overview style")
    return tuple(s for s in OVERVIEW_STYLES if "all" in requested or s in requested)


def overview_data(model: dict, style: str):
    normalize_overview_styles(style)
    by_id = {e["id"]: e for e in model["elements"]}
    depth = 2 if style == "executive" else 3 if style == "progressive" else 4
    elements = [
        deepcopy(e) for e in model["elements"] if ELEMENT_TYPE_DEPTH[e["type"]] <= depth
    ]
    parents, frames = {}, {}
    visible = {e["id"] for e in elements}
    for e in elements:
        descendants = []
        for child in model["elements"]:
            current = child.get("parent_id")
            while current in by_id:
                if current == e["id"]:
                    descendants.append(child)
                    break
                current = by_id[current].get("parent_id")
        if style in {"executive", "progressive"} and descendants:
            counts = ", ".join(
                f"{sum(d['type'] == t for d in descendants)} {t}"
                for t in ("component", "code")
                if any(d["type"] == t for d in descendants)
            )
            e["description"] += ("\nDrill-down: " + counts) if counts else ""
        if e.get("parent_id") in visible:
            parents[e["id"]] = e["parent_id"]
    for parent in set(parents.values()):
        frames[parent] = next(e for e in elements if e["id"] == parent)
    # One representative per original flow, at the finest scope whose endpoints remain visible.
    selected = {}
    for r in model["relationships"]:
        if {r["source_id"], r["destination_id"]} <= visible:
            rank = sum(
                ELEMENT_TYPE_DEPTH[by_id[x]["type"]]
                for x in (r["source_id"], r["destination_id"])
            )
            for flow in r.get("flow_ids", [r["id"]]):
                if flow not in selected or rank > selected[flow][0]:
                    selected[flow] = (rank, r)
    relationships = (
        list({r["id"]: r for _, r in selected.values()}.values())
        if style != "hierarchy"
        else []
    )
    return (
        [e for e in elements if e["id"] not in frames],
        relationships,
        parents,
        frames,
    )


def build_overview_scene(model: dict, style: str = "progressive") -> Scene:
    title = (
        model["system"]["name"] + " — " + style.replace("-", " ").title() + " overview"
    )
    if style != "small-multiples":
        elements, relationships, parents, frames = overview_data(model, style)
        return choose_scene(title, elements, relationships, parents, frames)
    scenes = [build_view_scene_elk(model, v) for v in model["views"]]
    # Every expanded scope gets a panel; retain all repeated L3/L4 scopes.
    column_width = max((s.width for s in scenes), default=660)
    width = column_width * 2 + 24
    rows = [max(s.height for s in scenes[i : i + 2]) for i in range(0, len(scenes), 2)]
    result = Scene(title, width, sum(rows) + 260, title_lines=[title], content_top=100)
    y = 100
    for index, scene in enumerate(scenes):
        prefix = f"panel-{index}-"
        x_offset = index % 2 * (column_width + 24)
        for box in scene.boxes:
            box.id = prefix + box.id
            box.parent_id = prefix + box.parent_id if box.parent_id else None
            box.y += y
            box.x += x_offset
        for edge in scene.edges:
            edge.id = prefix + edge.id
            edge.source_id = prefix + edge.source_id
            edge.destination_id = prefix + edge.destination_id
            edge.points = [(x + x_offset, py + y) for x, py in edge.points]
            if edge.label:
                edge.label.id = prefix + edge.label.id
                edge.label.y += y
                edge.label.x += x_offset
        # Panel titles are measured labels and live in the panel's reserved title area.
        from .scene import Box
        from .style import Label, TextLine, wrap_to_width

        result.boxes.append(
            Box(
                prefix + "title",
                "panel-title",
                48 + x_offset,
                y + 12,
                column_width - 96,
                80,
                Label(
                    [
                        TextLine(t, 18)
                        for t in wrap_to_width(scene.title, column_width - 110, 18)
                    ]
                ),
            )
        )
        result.boxes.extend(scene.boxes)
        result.edges.extend(scene.edges)
        if index % 2 or index == len(scenes) - 1:
            y += rows[index // 2]
    result.key_y = y + 30
    return result


DEPLOYMENT_TITLES = {"aws": "AWS deployment", "gcp": "Google Cloud deployment"}


def build_cloud_scene(model: dict) -> Scene:
    deployment = model["deployment"]
    by_id = {e["id"]: e for e in model["elements"]}
    frames = {n["id"]: n for n in deployment["nodes"]}
    parents = {
        n["id"]: n["parent_id"] for n in deployment["nodes"] if n.get("parent_id")
    }
    parents.update({p["element_id"]: p["node_id"] for p in deployment["placements"]})
    elements = [by_id[p["element_id"]] for p in deployment["placements"]]
    visible = {e["id"] for e in elements}
    relationships = [
        r
        for r in model["relationships"]
        if r["source_id"] in visible
        and r["destination_id"] in visible
        and r["id"]
        in next(v for v in model["views"] if v["type"] == "container")[
            "relationship_ids"
        ]
    ]
    return choose_scene(
        model["system"]["name"]
        + " — "
        + DEPLOYMENT_TITLES[deployment.get("provider", "aws")],
        elements,
        relationships,
        parents,
        frames,
    )


build_aws_scene = build_gcp_scene = build_cloud_scene
