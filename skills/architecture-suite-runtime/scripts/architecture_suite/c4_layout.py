"""Scope-specific C4 scene requests."""

from .scene import build_scene, scene_collisions
from .readability import readability_findings, score_scene


def build_view_scene_elk(model: dict, view: dict):
    by_id = {e["id"]: e for e in model["elements"]}
    boundary = view.get("boundary_id")
    elements = [by_id[i] for i in view["element_ids"] if i != boundary]
    relationships = [
        r for r in model["relationships"] if r["id"] in view["relationship_ids"]
    ]
    parents, frames = {}, {}
    if boundary:
        frames[boundary] = by_id[boundary]
        parents.update(
            {e["id"]: boundary for e in elements if e.get("parent_id") == boundary}
        )
    groups = {}
    for e in elements:
        if e.get("group"):
            groups.setdefault((parents.get(e["id"]), e["group"]), []).append(e["id"])
    for (parent, name), ids in groups.items():
        if len(ids) > 1:
            ident = f"group-{len(frames)}"
            frames[ident] = {"id": ident, "name": name, "type": "group"}
            if parent:
                parents[ident] = parent
            parents.update({i: ident for i in ids})
    return choose_scene(
        view["title"],
        elements,
        relationships,
        parents,
        frames,
        view.get("direction", "auto"),
    )


def choose_scene(title, elements, relationships, parents, frames, direction="auto"):
    candidates = [
        build_scene(
            title, elements, relationships, parents=parents, frames=frames, direction=d
        )
        for d in (("right", "down") if direction == "auto" else (direction,))
    ]
    return min(
        candidates,
        key=lambda s: (
            len(scene_collisions(s)) + len(readability_findings(s)),
            score_scene(s)["score"],
        ),
    )
