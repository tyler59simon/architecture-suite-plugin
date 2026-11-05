"""Shared absolute geometry for SVG, PNG, Draw.io, and verification."""

from __future__ import annotations
from dataclasses import asdict, dataclass, field
from .style import Label, TextLine, element_label, wrap_to_width
from .layout_host import layout_graph

PAGE_MARGIN = 48
FRAME_TITLE_TOP = 8
LABEL_MAX_WIDTH = 300


@dataclass
class Box:
    id: str
    role: str
    x: float
    y: float
    width: float
    height: float
    label: Label
    parent_id: str | None = None
    element: dict | None = None


@dataclass
class Edge:
    id: str
    source_id: str
    destination_id: str
    points: list[tuple[float, float]]
    label: Box | None = None
    kind: str = "dependency"


@dataclass
class Scene:
    title: str
    width: float
    height: float
    boxes: list[Box] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    title_lines: list[str] = field(default_factory=list)
    content_top: float = 100
    key_y: float = 0

    def as_dict(self) -> dict:
        return asdict(self)


def build_scene(
    title: str,
    elements: list[dict],
    relationships: list[dict],
    *,
    parents: dict[str, str] | None = None,
    frames: dict[str, dict] | None = None,
    direction: str = "auto",
) -> Scene:
    parents, frames = parents or {}, frames or {}
    elements_by_id = {e["id"]: e for e in elements}
    labels = {e["id"]: element_label(e) for e in elements}
    labels.update(
        {
            ident: Label(
                [TextLine(t, 15) for t in wrap_to_width(value["name"], 260, 15)]
            )
            for ident, value in frames.items()
        }
    )
    nodes = {}
    for ident, label in labels.items():
        if ident in frames:
            nodes[ident] = {
                "id": ident,
                "width": max(320, label.width + 56),
                "height": label.height + 80,
                "children": [],
                "layoutOptions": {
                    "elk.nodeSize.constraints": "MINIMUM_SIZE",
                    "elk.nodeSize.minimum": f"({max(320, label.width + 56)},{label.height + 80})",
                    "elk.padding": f"[top={label.height + 30},left=28,bottom=28,right=28]",
                },
            }
        else:
            nodes[ident] = {
                "id": ident,
                "width": max(160, label.width + 32),
                "height": label.height + 32,
            }
    root = {
        "id": "__architecture_suite_root__",
        "children": [],
        "edges": [],
        "layoutOptions": {
            "elk.algorithm": "layered",
            "elk.direction": "DOWN" if direction == "down" else "RIGHT",
            "elk.hierarchyHandling": "INCLUDE_CHILDREN",
            "elk.edgeRouting": "ORTHOGONAL",
            "elk.spacing.nodeNode": "60",
            "elk.layered.spacing.nodeNodeBetweenLayers": "100",
            "elk.spacing.edgeNode": "25",
            "elk.spacing.edgeEdge": "20",
            "elk.layered.spacing.edgeEdgeBetweenLayers": "25",
            "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
            "elk.randomSeed": "1",
            "elk.padding": "[top=24,left=24,bottom=24,right=24]",
        },
    }
    for ident, node in nodes.items():
        parent = parents.get(ident)
        (nodes[parent] if parent in frames else root)["children"].append(node)
    edge_labels = {}
    for r in relationships:
        if r["source_id"] not in nodes or r["destination_id"] not in nodes:
            continue
        text = r["description"] + (
            f" [{r['technology']}]" if r.get("technology") else ""
        )
        label = Label(
            [TextLine(t, 11) for t in wrap_to_width(text, LABEL_MAX_WIDTH, 11)]
        )
        edge_labels[r["id"]] = label
        root["edges"].append(
            {
                "id": r["id"],
                "sources": [r["source_id"]],
                "targets": [r["destination_id"]],
                "labels": [
                    {
                        "text": text,
                        "width": label.width + 16,
                        "height": label.height + 10,
                        "layoutOptions": {"elk.edgeLabels.placement": "CENTER"},
                    }
                ],
            }
        )
    graph = layout_graph(root)
    title_lines = wrap_to_width(title, max(400, graph["width"]), 22)
    top = PAGE_MARGIN + len(title_lines) * 33 + 25
    scene = Scene(
        title,
        max(660, graph["width"] + 2 * PAGE_MARGIN),
        graph["height"] + top + 170,
        title_lines=title_lines,
        content_top=top,
        key_y=graph["height"] + top + 40,
    )

    def visit(parent, ox, oy):
        for node in parent.get("children", []):
            ident = node["id"]
            x, y = ox + node["x"], oy + node["y"]
            scene.boxes.append(
                Box(
                    ident,
                    "frame" if ident in frames else "card",
                    x,
                    y,
                    node["width"],
                    node["height"],
                    labels[ident],
                    parents.get(ident),
                    elements_by_id.get(ident, frames.get(ident)),
                )
            )
            visit(node, x, y)
        for edge in parent.get("edges", []):
            container = next(
                (b for b in scene.boxes if b.id == edge.get("container")), None
            )
            ex, ey = (container.x, container.y) if container else (ox, oy)
            points = []
            for section in edge.get("sections", []):
                points.extend(
                    (ex + p["x"], ey + p["y"])
                    for p in [
                        section["startPoint"],
                        *section.get("bendPoints", []),
                        section["endPoint"],
                    ]
                )
            label_box = None
            if edge.get("labels"):
                lab = edge["labels"][0]
                label_box = Box(
                    edge["id"] + "-label",
                    "edge-label",
                    ex + lab["x"],
                    ey + lab["y"],
                    lab["width"],
                    lab["height"],
                    edge_labels[edge["id"]],
                )
            scene.edges.append(
                Edge(
                    edge["id"],
                    edge["sources"][0],
                    edge["targets"][0],
                    points,
                    label_box,
                )
            )

    visit(graph, PAGE_MARGIN, top)
    return scene


def _overlap(a: Box, b: Box, tolerance: float = 0.5) -> bool:
    return (
        min(a.x + a.width, b.x + b.width) - max(a.x, b.x) > tolerance
        and min(a.y + a.height, b.y + b.height) - max(a.y, b.y) > tolerance
    )


def scene_collisions(scene: Scene) -> list[dict]:
    findings = []
    by_id = {b.id: b for b in scene.boxes}

    def ancestors(box):
        result = set()
        parent = box.parent_id
        while parent in by_id and parent not in result:
            result.add(parent)
            parent = by_id[parent].parent_id
        return result

    def add(code, ids):
        findings.append({"code": code, "elements": ids})

    for i, box in enumerate(scene.boxes):
        if (
            box.x < 0
            or box.y < scene.content_top
            or box.x + box.width > scene.width + 0.5
            or box.y + box.height > scene.key_y
        ):
            add("page-bounds", [box.id])
        if box.role != "frame" and (
            box.label.width + 20 > box.width or box.label.height + 20 > box.height
        ):
            add("label-bounds", [box.id])
        if box.parent_id in by_id:
            parent = by_id[box.parent_id]
            if not (
                box.x > parent.x
                and box.y >= parent.y + parent.label.height + 16
                and box.x + box.width < parent.x + parent.width
                and box.y + box.height < parent.y + parent.height
            ):
                add("containment", [box.id, parent.id])
        for other in scene.boxes[i + 1 :]:
            if (
                other.id not in ancestors(box)
                and box.id not in ancestors(other)
                and _overlap(box, other)
            ):
                add("box-overlap", [box.id, other.id])
    labels = [e.label for e in scene.edges if e.label]
    for i, label in enumerate(labels):
        if label.label.width > label.width or label.label.height > label.height:
            add("edge-label-bounds", [label.id])
        if (
            label.x < 0
            or label.y < scene.content_top
            or label.x + label.width > scene.width
            or label.y + label.height > scene.key_y
        ):
            add("edge-label-page", [label.id])
        for box in scene.boxes:
            if box.role != "frame" and _overlap(label, box):
                add("edge-label-overlap", [label.id, box.id])
        for other in labels[i + 1 :]:
            if _overlap(label, other):
                add("edge-label-overlap", [label.id, other.id])
    for edge in scene.edges:
        for a, b in zip(edge.points, edge.points[1:]):
            segment = Box(
                "segment",
                "",
                min(a[0], b[0]) - 0.5,
                min(a[1], b[1]) - 0.5,
                abs(a[0] - b[0]) + 1,
                abs(a[1] - b[1]) + 1,
                Label(),
            )
            for box in scene.boxes:
                if (
                    box.role == "card"
                    and box.id not in {edge.source_id, edge.destination_id}
                    and _overlap(segment, box, 0)
                ):
                    add("edge-through-card", [edge.id, box.id])
            for label in labels:
                if edge.label is not label and _overlap(segment, label, 0):
                    add("edge-through-label", [edge.id, label.id])
    segments = [
        (e.id, a, b) for e in scene.edges for a, b in zip(e.points, e.points[1:])
    ]
    for i, (ident, a, b) in enumerate(segments):
        for other, c, d in segments[i + 1 :]:
            if ident == other:
                continue
            if a[0] == b[0] == c[0] == d[0]:
                overlap = min(max(a[1], b[1]), max(c[1], d[1])) - max(
                    min(a[1], b[1]), min(c[1], d[1])
                )
            elif a[1] == b[1] == c[1] == d[1]:
                overlap = min(max(a[0], b[0]), max(c[0], d[0])) - max(
                    min(a[0], b[0]), min(c[0], d[0])
                )
            else:
                continue
            if overlap > 8:
                add("edge-shared-track", [ident, other])
    return findings
