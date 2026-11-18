"""Five overview styles derived from the canonical C4 model, never a fifth C4 level."""

from copy import deepcopy
import math
import re
from .model import ELEMENT_TYPE_DEPTH, merge_flows
from .scene import Box, Scene, build_view_scene_elk, choose_scene

# Below the 6000 px PNG cap, leaving room for the page margin.
SMALL_MULTIPLES_MAX_WIDTH = 5600

PANEL_PREFIX = re.compile(r"panel-(\d+)-")

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
    # Model order, not set order: frame order feeds ELK and must not depend on hash seeds.
    framed = set(parents.values())
    frames.update((e["id"], e) for e in elements if e["id"] in framed)
    # One representative per original flow, at the finest scope whose endpoints remain visible.
    selected = {}
    for r in model["relationships"]:
        if {r["source_id"], r["destination_id"]} <= visible:
            rank = sum(
                ELEMENT_TYPE_DEPTH[by_id[x]["type"]]
                for x in (r["source_id"], r["destination_id"])
            )
            for flow in r.get("flow_ids") or [r["id"]]:  # [] means none recorded
                if flow not in selected or rank > selected[flow][0]:
                    selected[flow] = (rank, r)
    # A merged arrow keeps only the flows assigned to it; the rest are drawn finer.
    assigned: dict[str, list] = {}
    for flow, (_, r) in selected.items():
        assigned.setdefault(r["id"], []).append(flow)
    relationships = []
    for r in {r["id"]: r for _, r in selected.values()}.values():
        details = {f["id"]: f for f in r.get("flows") or []}
        keep = [details[f] for f in r.get("flow_ids") or [] if f in details and f in assigned[r["id"]]]
        if keep and len(keep) < len(r["flow_ids"]):
            r = merge_flows(r["id"], r["source_id"], r["destination_id"], keep)
        relationships.append(r)
    if style == "hierarchy":
        relationships = []
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
    # Every expanded scope gets a panel; retain all repeated L3/L4 scopes. Panels fill
    # rows in reading order at their own widths up to a landscape target, so one wide
    # view does not widen every panel (which overflowed PNG limits on moderate models).
    gap = 24
    area = sum(s.width * s.height for s in scenes)
    target = max(
        max((s.width for s in scenes), default=660),
        min(SMALL_MULTIPLES_MAX_WIDTH, math.ceil(math.sqrt(area * 1.5))),
    )
    rows: list[list[int]] = []
    for index, scene in enumerate(scenes):
        if rows and sum(scenes[i].width + gap for i in rows[-1]) + scene.width <= target:
            rows[-1].append(index)
        else:
            rows.append([index])
    width = max(
        (sum(scenes[i].width for i in row) + gap * (len(row) - 1) for row in rows),
        default=660,
    )
    heights = [max(scenes[i].height for i in row) for row in rows]
    result = Scene(title, width, sum(heights) + 260, title_lines=[title], content_top=100)
    y = 100
    offsets = {}
    for row in rows:
        x = 0
        for i in row:
            offsets[i] = x
            x += scenes[i].width + gap
    row_end = {row[-1]: heights[n] for n, row in enumerate(rows)}
    for index, scene in enumerate(scenes):
        prefix = f"panel-{index}-"
        x_offset = offsets[index]
        column_width = scene.width
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
        # Their ID never reuses a box ID (an element may be called `title`).
        from .style import Label, TextLine, wrap_to_width

        title_id, suffix = prefix + "title", 2
        taken = {box.id for box in scene.boxes}
        while title_id in taken:
            title_id, suffix = f"{prefix}title-{suffix}", suffix + 1
        result.boxes.append(
            Box(
                title_id,
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
        if index in row_end:
            y += row_end[index]
    result.key_y = y + 30
    return result


def panel_groups(scene: Scene) -> list[tuple[Box, list[Box]]]:
    """Small-multiples panels in order: each title box with the panel's top-level boxes.

    Every box of a small-multiples scene has a `panel-<n>-` ID prefix; other scenes
    have no panel-title boxes and return an empty list.
    """
    groups: dict[str, tuple[Box, list[Box]]] = {
        PANEL_PREFIX.match(b.id).group(1): (b, [])
        for b in scene.boxes
        if b.role == "panel-title"
    }
    for b in scene.boxes if groups else ():
        if b.role != "panel-title" and b.parent_id is None:
            groups[PANEL_PREFIX.match(b.id).group(1)][1].append(b)
    return list(groups.values())


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
