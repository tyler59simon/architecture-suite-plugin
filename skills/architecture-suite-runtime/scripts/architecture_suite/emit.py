"""Scene exporters. Geometry and pre-wrapped label positions are shared."""

from __future__ import annotations
import base64
import html
from urllib.parse import quote
import xml.etree.ElementTree as ET
from .aws import ASSETS, icon_bytes
from .scene import Scene
from .style import CYLINDER_CAP, box_style, claim_cue

KEY = (
    "Notation key",
    "Name · «type» · technology · responsibility",
    "Enclosing frame = named scope or deployment boundary",
    "Arrow = directed dependency; label states its purpose",
)
CLAIM_KEY = "Dotted outline or arrow, «inferred»/«proposed»/«unknown» = claim not observed"


def _claimed(item) -> bool:
    """A box or edge whose stated status is inferred, proposed or unknown."""
    element = getattr(item, "element", None)
    status = element.get("status") if isinstance(element, dict) else getattr(item, "status", None)
    return bool(claim_cue(status))


def _key(scene) -> tuple:
    claims = any(_claimed(b) for b in scene.boxes) or any(_claimed(e) for e in scene.edges)
    return KEY + ((CLAIM_KEY,) if claims else ())


def _placements(box):
    y = box.y + (10 if box.role == "frame" else 16) + box.label.top_pad
    if box.label.icon:
        y += box.label.icon_size + 8
    for line in box.label.lines:
        y += line.height
        yield box.x + box.width / 2, y - 4, line


def _cylinder(box, stroke, fill, dash="") -> str:
    x, y, w, h, ry = box.x, box.y, box.width, box.height, CYLINDER_CAP
    rx = w / 2
    body = (
        f"M {x},{y + ry} L {x},{y + h - ry} A {rx},{ry} 0 0 0 {x + w},{y + h - ry} "
        f"L {x + w},{y + ry} Z"
    )
    return (
        f'<path d="{body}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"{dash}/>'
        f'<ellipse cx="{x + rx}" cy="{y + ry}" rx="{rx}" ry="{ry}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"{dash}/>'
    )


def render_scene_svg(scene: Scene) -> str:
    font = base64.b64encode((ASSETS / "font.ttf").read_bytes()).decode()
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{scene.width}" height="{scene.height}" viewBox="0 0 {scene.width} {scene.height}" role="img">',
        f"<title>{html.escape(scene.title)}</title>",
        f'<defs><style>@font-face{{font-family:Suite;src:url(data:font/ttf;base64,{font})}}text{{font-family:Suite,Arial,sans-serif;fill:#172b4d}}</style><marker id="__suite_arrow__" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#526580"/></marker></defs>',
        f'<rect width="{scene.width}" height="{scene.height}" fill="white"/>',
    ]
    for i, line in enumerate(scene.title_lines):
        parts.append(
            f'<text x="48" y="{65 + i * 33}" font-size="22">{html.escape(line)}</text>'
        )
    titles = []
    # Parent frames precede children in the scene's preorder.
    for box in scene.boxes:
        shape, stroke, fill = box_style(box)
        if box.role != "panel-title":
            dash = (
                ' stroke-dasharray="6 4"'
                if box.role == "frame"
                else ' stroke-dasharray="2 3"'
                if _claimed(box)
                else ""
            )
            if shape == "cylinder":
                # Invisible bounding rect keeps a stable id and exact geometry hook.
                parts.append(
                    f'<rect id="box-{box.id}" x="{box.x}" y="{box.y}" width="{box.width}" height="{box.height}" fill="none" stroke="none"/>'
                )
                parts.append(_cylinder(box, stroke, fill, dash))
            else:
                radius = 28 if shape == "pill" else 6
                parts.append(
                    f'<rect id="box-{box.id}" x="{box.x}" y="{box.y}" width="{box.width}" height="{box.height}" rx="{radius}" stroke="{stroke}" fill="{fill}" stroke-width="1.5"{dash}/>'
                )
        if box.label.icon:
            uri = base64.b64encode(icon_bytes(box.label.icon)).decode()
            parts.append(
                f'<image x="{box.x + (box.width - box.label.icon_size) / 2}" y="{box.y + 14 + box.label.top_pad}" width="{box.label.icon_size}" height="{box.label.icon_size}" preserveAspectRatio="xMidYMid meet" href="data:image/svg+xml;base64,{uri}"/>'
            )
        for x, y, line in _placements(box):
            text = f'<text x="{x}" y="{y}" text-anchor="middle" font-size="{line.font}">{html.escape(line.text)}</text>'
            if box.role == "frame":
                # Edges enter frames across their titles: draw titles last, with a halo.
                titles.append(
                    text.replace(
                        "<text ",
                        '<text stroke="white" stroke-width="4" stroke-linejoin="round" '
                        'paint-order="stroke" ',
                        1,
                    )
                )
            else:
                parts.append(text)
    for edge in scene.edges:
        points = " ".join(f"{x},{y}" for x, y in edge.points)
        marker = (
            ' marker-end="url(#__suite_arrow__)"' if edge.kind != "lifeline" else ""
        )
        dashed = (
            ' stroke-dasharray="5 4"'
            if edge.kind in {"lifeline", "response"}
            else ' stroke-dasharray="2 3"'
            if _claimed(edge)
            else ""
        )
        parts.append(
            f'<polyline id="edge-{edge.id}" points="{points}" fill="none" stroke="#526580" stroke-width="1.5"{marker}{dashed}/>'
        )
        if edge.label:
            b = edge.label
            parts.append(
                f'<rect x="{b.x}" y="{b.y}" width="{b.width}" height="{b.height}" fill="white" rx="3"/>'
            )
            # Edge labels use the same top inset as the dimensions ELK reserved.
            y = b.y + 5
            for line in b.label.lines:
                y += line.height
                parts.append(
                    f'<text x="{b.x + b.width / 2}" y="{y - 4}" font-size="{line.font}" text-anchor="middle">{html.escape(line.text)}</text>'
                )
    parts.extend(titles)
    for i, line in enumerate(_key(scene)):
        parts.append(
            f'<text x="48" y="{scene.key_y + i * 22}" font-size="12">{html.escape(line)}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def render_scene_drawio(scene: Scene) -> str:
    mxfile = ET.Element("mxfile", host="Architecture Suite", version="2.0")
    diagram = ET.SubElement(mxfile, "diagram", id="architecture", name=scene.title)
    graph = ET.SubElement(
        diagram,
        "mxGraphModel",
        page="1",
        pageWidth=str(scene.width),
        pageHeight=str(scene.height),
    )
    root = ET.SubElement(graph, "root")
    ET.SubElement(root, "mxCell", id="0")
    ET.SubElement(root, "mxCell", id="1", parent="0")
    by_id = {b.id: b for b in scene.boxes}
    cell_ids = {b.id: f"n{i}" for i, b in enumerate(scene.boxes)}

    def vertex(ident, value, x, y, w, h, style, parent="1"):
        cell = ET.SubElement(
            root,
            "mxCell",
            id=ident,
            value=value,
            style=style,
            vertex="1",
            parent=parent,
        )
        ET.SubElement(
            cell,
            "mxGeometry",
            x=str(x),
            y=str(y),
            width=str(w),
            height=str(h),
            attrib={"as": "geometry"},
        )

    vertex(
        "title",
        html.escape(scene.title),
        48,
        35,
        scene.width - 96,
        55,
        "text;html=1;fontSize=22;align=left;fontFamily=Roboto;",
    )
    for box in scene.boxes:
        parent = by_id.get(box.parent_id)
        x, y = box.x - (parent.x if parent else 0), box.y - (parent.y if parent else 0)
        shape, stroke, fill = box_style(box)
        geometry_style = {
            "cylinder": f"shape=cylinder3;boundedLbl=1;backgroundOutline=1;size={CYLINDER_CAP};",
            "pill": "rounded=1;arcSize=25;",
        }.get(shape, "rounded=1;")
        vertex(
            cell_ids[box.id],
            "",
            x,
            y,
            box.width,
            box.height,
            f"{geometry_style}fillColor={fill};strokeColor={stroke};"
            + (
                "dashed=1;dashPattern=2 3;"
                if box.role != "frame" and _claimed(box)
                else f"dashed={int(box.role == 'frame')};"
            ),
            cell_ids.get(box.parent_id, "1"),
        )
        for index, (tx, ty, line) in enumerate(_placements(box)):
            vertex(
                cell_ids[box.id] + f"-text-{index}",
                html.escape(line.text),
                tx - box.x - box.width / 2,
                ty - box.y - line.font,
                box.width,
                line.height,
                f"text;html=1;align=center;fontSize={line.font};fontFamily=Roboto;spacing=0;",
                cell_ids[box.id],
            )
        if box.label.icon:
            uri = "data:image/svg+xml," + quote(
                icon_bytes(box.label.icon).decode(), safe=""
            )
            vertex(
                cell_ids[box.id] + "-icon",
                "",
                (box.width - box.label.icon_size) / 2,
                14 + box.label.top_pad,
                box.label.icon_size,
                box.label.icon_size,
                f"shape=image;imageAspect=1;image={uri};",
                cell_ids[box.id],
            )
    for edge_index, edge in enumerate(scene.edges):
        source = by_id.get(edge.source_id)
        destination = by_id.get(edge.destination_id)
        connection_style = ""
        if edge.points and source and destination:
            sx, sy = edge.points[0]
            dx, dy = edge.points[-1]
            connection_style = (
                f"exitX={(sx - source.x) / source.width};exitY={(sy - source.y) / source.height};exitPerimeter=0;"
                f"entryX={(dx - destination.x) / destination.width};entryY={(dy - destination.y) / destination.height};entryPerimeter=0;noEdgeStyle=1;"
            )
        cell = ET.SubElement(
            root,
            "mxCell",
            id=f"e{edge_index}",
            edge="1",
            parent="1",
            source=cell_ids[edge.source_id],
            target=cell_ids[edge.destination_id],
            style=f"endArrow={'none' if edge.kind == 'lifeline' else 'block'};"
            + (
                "dashed=1;dashPattern=2 3;"
                if _claimed(edge) and edge.kind not in {"lifeline", "response"}
                else f"dashed={int(edge.kind in {'lifeline', 'response'})};"
            )
            + "rounded=0;strokeColor=#526580;"
            + connection_style,
        )
        geometry = ET.SubElement(
            cell, "mxGeometry", relative="1", attrib={"as": "geometry"}
        )
        if edge.points:
            for (x, y), name in (
                (edge.points[0], "sourcePoint"),
                (edge.points[-1], "targetPoint"),
            ):
                ET.SubElement(
                    geometry, "mxPoint", x=str(x), y=str(y), attrib={"as": name}
                )
            array = ET.SubElement(geometry, "Array", attrib={"as": "points"})
            for x, y in edge.points[1:-1]:
                ET.SubElement(array, "mxPoint", x=str(x), y=str(y))
        if edge.label:
            b = edge.label
            vertex(
                f"e{edge_index}-label",
                "<br>".join(html.escape(ln.text) for ln in b.label.lines),
                b.x,
                b.y,
                b.width,
                b.height,
                "text;html=1;fillColor=#ffffff;fontSize=11;fontFamily=Roboto;spacing=0;",
            )
    vertex(
        "key",
        "<br>".join(html.escape(ln) for ln in _key(scene)),
        48,
        scene.key_y - 15,
        560,
        100,
        "text;html=1;align=left;fontSize=12;fontFamily=Roboto;",
    )
    return ET.tostring(mxfile, encoding="unicode")
