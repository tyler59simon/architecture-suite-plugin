"""Scene exporters. Geometry and pre-wrapped label positions are shared."""

from __future__ import annotations
import base64
import html
import io
import math
from urllib.parse import quote
import xml.etree.ElementTree as ET
import zipfile
from .aws import ASSETS, icon_bytes
from .scene import Scene
from .style import CYLINDER_CAP, INK, box_style, claim_cue

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


# Visio (.vsdx): an OPC package of Visio 2013+ XML parts. Scene pixels are 1/96 inch.
VISIO_NS = "http://schemas.microsoft.com/office/visio/2012/main"
OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
VISIO_REL = "http://schemas.microsoft.com/visio/2010/relationships"
PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
EDGE_COLOR = "#526580"
VISIO_FONT = "Roboto"
LINE = 1.5 / 96
SOLID, DASHED, DOTTED, NO_LINE = 1, 2, 3, 0
FILLED_ARROW = 13


def _n(value: float) -> str:
    return f"{round(value, 6) + 0.0:.10g}"


def _xml(root: ET.Element) -> bytes:
    return b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + ET.tostring(
        root, encoding="utf-8", xml_declaration=False
    )


def _rels(*items: tuple[str, str, str]) -> bytes:
    root = ET.Element("Relationships", xmlns=PACKAGE_REL)
    for ident, kind, target in items:
        ET.SubElement(root, "Relationship", Id=ident, Type=kind, Target=target)
    return _xml(root)


def _cell(parent, name: str, value, unit: str | None = None) -> None:
    attrs = {"N": name, "V": value if isinstance(value, str) else _n(value)}
    if unit:
        attrs["U"] = unit
    ET.SubElement(parent, "Cell", attrs)


def _row(section, kind: str, index: int, **cells) -> None:
    row = ET.SubElement(section, "Row", T=kind, IX=str(index))
    for name, value in cells.items():
        _cell(row, name, value)


def _rectangle(geometry) -> None:
    for index, (x, y) in enumerate(((0, 0), (1, 0), (1, 1), (0, 1), (0, 0))):
        _row(geometry, "RelMoveTo" if index == 0 else "RelLineTo", index + 1, X=x, Y=y)


def _cells(parent, values) -> None:
    for name, value in values:
        _cell(parent, name, value)


def _text(shape, lines, width: float, height: float, *, top: float, align: int = 1) -> None:
    """One editable text block; each pre-wrapped (text, font, height) line is a paragraph."""
    if not lines:
        return
    # Lines are already wrapped to the scene's font metrics. A wider text block keeps a
    # substituted font (Roboto not installed) from wrapping them again.
    w, h = width / 96, height / 96
    block = w * 1.25 + 0.5
    _cells(
        shape,
        (
            ("TxtPinX", w / 2),
            ("TxtPinY", h / 2),
            ("TxtWidth", block),
            ("TxtHeight", h),
            ("TxtLocPinX", w / 2 if align == 0 else block / 2),
            ("TxtLocPinY", h / 2),
            ("TxtAngle", 0),
            ("TopMargin", top / 96),
            ("BottomMargin", 0),
            ("LeftMargin", 0),
            ("RightMargin", 0),
            ("VerticalAlign", 0),
        ),
    )
    # One character and one paragraph row per line, in text order, as Visio writes them.
    character = ET.SubElement(shape, "Section", N="Character")
    paragraph = ET.SubElement(shape, "Section", N="Paragraph")
    for index, (_, font, height) in enumerate(lines):
        row = ET.SubElement(character, "Row", IX=str(index))
        _cells(row, (("Font", VISIO_FONT), ("Color", INK)))
        _cell(row, "Size", font / 96, "PT")
        row = ET.SubElement(paragraph, "Row", IX=str(index))
        _cells(row, (("HorzAlign", align), ("SpBefore", 0), ("SpAfter", 0)))
        _cell(row, "SpLine", height / 96, "PT")
    text = ET.SubElement(shape, "Text")
    for index, (value, _, _) in enumerate(lines):
        ET.SubElement(text, "cp", IX=str(index))
        ET.SubElement(text, "pp", IX=str(index)).tail = value + (
            "\n" if index < len(lines) - 1 else ""
        )


def _vsdx_document() -> ET.Element:
    document = ET.Element("VisioDocument", {"xmlns": VISIO_NS, "xmlns:r": OFFICE_REL})
    faces = ET.SubElement(document, "FaceNames")
    ET.SubElement(faces, "FaceName", NameU=VISIO_FONT, Name=VISIO_FONT)
    sheets = ET.SubElement(document, "StyleSheets")
    style = ET.SubElement(sheets, "StyleSheet", ID="0", NameU="No Style", Name="No Style")
    _cells(
        style,
        (
            ("EnableLineProps", 1),
            ("EnableFillProps", 1),
            ("EnableTextProps", 1),
            ("HideForApply", 0),
            ("LineWeight", LINE),
            ("LineColor", INK),
            ("LinePattern", SOLID),
            ("Rounding", 0),
            ("BeginArrow", 0),
            ("EndArrow", 0),
            ("BeginArrowSize", 1),
            ("EndArrowSize", 1),
            ("LineCap", 0),
            ("FillForegnd", "#ffffff"),
            ("FillBkgnd", "#ffffff"),
            ("FillPattern", 1),
            ("ShdwPattern", 0),
            ("LeftMargin", 0),
            ("RightMargin", 0),
            ("TopMargin", 0),
            ("BottomMargin", 0),
            ("VerticalAlign", 1),
            ("TextBkgnd", 0),
        ),
    )
    return document


def _vsdx_package(scene: Scene, page_xml: ET.Element, media: dict, icons: dict) -> bytes:
    pages = ET.Element("Pages", {"xmlns": VISIO_NS, "xmlns:r": OFFICE_REL})
    page = ET.SubElement(pages, "Page", ID="0", NameU="Page-1", Name=scene.title[:31] or "Page-1")
    sheet = ET.SubElement(page, "PageSheet")
    _cell(sheet, "PageWidth", scene.width / 96, "IN")
    _cell(sheet, "PageHeight", scene.height / 96, "IN")
    _cell(sheet, "PageScale", 1, "IN")
    _cell(sheet, "DrawingScale", 1, "IN")
    _cells(sheet, (("DrawingSizeType", 3), ("DrawingScaleType", 0)))
    ET.SubElement(page, "Rel", {"r:id": "rId1"})

    core = ET.Element(
        "cp:coreProperties",
        {
            "xmlns:cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
            "xmlns:dc": "http://purl.org/dc/elements/1.1/",
        },
    )
    ET.SubElement(core, "dc:title").text = scene.title
    ET.SubElement(core, "dc:creator").text = "Architecture Suite"
    app = ET.Element(
        "Properties",
        xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties",
    )
    ET.SubElement(app, "Application").text = "Architecture Suite"

    types = ET.Element(
        "Types", xmlns="http://schemas.openxmlformats.org/package/2006/content-types"
    )
    for extension, kind in (
        ("rels", "application/vnd.openxmlformats-package.relationships+xml"),
        ("xml", "application/xml"),
        ("png", "image/png"),
    ):
        ET.SubElement(types, "Default", Extension=extension, ContentType=kind)
    for part, kind in (
        ("/visio/document.xml", "application/vnd.ms-visio.drawing.main+xml"),
        ("/visio/pages/pages.xml", "application/vnd.ms-visio.pages+xml"),
        ("/visio/pages/page1.xml", "application/vnd.ms-visio.page+xml"),
        ("/docProps/core.xml", "application/vnd.openxmlformats-package.core-properties+xml"),
        (
            "/docProps/app.xml",
            "application/vnd.openxmlformats-officedocument.extended-properties+xml",
        ),
    ):
        ET.SubElement(types, "Override", PartName=part, ContentType=kind)

    parts = [
        ("[Content_Types].xml", _xml(types)),
        (
            "_rels/.rels",
            _rels(
                ("rId1", f"{VISIO_REL}/document", "visio/document.xml"),
                ("rId2", f"{PACKAGE_REL}/metadata/core-properties", "docProps/core.xml"),
                ("rId3", f"{OFFICE_REL}/extended-properties", "docProps/app.xml"),
            ),
        ),
        ("docProps/app.xml", _xml(app)),
        ("docProps/core.xml", _xml(core)),
        ("visio/document.xml", _xml(_vsdx_document())),
        (
            "visio/_rels/document.xml.rels",
            _rels(("rId1", f"{VISIO_REL}/pages", "pages/pages.xml")),
        ),
        ("visio/pages/pages.xml", _xml(pages)),
        ("visio/pages/_rels/pages.xml.rels", _rels(("rId1", f"{VISIO_REL}/page", "page1.xml"))),
        ("visio/pages/page1.xml", _xml(page_xml)),
    ]
    if media:
        parts.append(
            (
                "visio/pages/_rels/page1.xml.rels",
                _rels(
                    *((rid, f"{OFFICE_REL}/image", f"../media/{rid}.png") for rid in media.values())
                ),
            )
        )
        parts.extend((f"visio/media/{rid}.png", icons[name]) for name, rid in media.items())
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        for name, data in parts:
            # Fixed metadata keeps packages byte-identical across runs and hosts.
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 0
            package.writestr(info, data)
    return buffer.getvalue()


def render_scene_vsdx(scene: Scene, icons: dict[str, bytes] | None = None) -> bytes:
    """Editable Visio drawing: shapes, glued connectors, text and PNG icons (name -> PNG)."""
    icons = icons or {}
    page_height = scene.height
    page_xml = ET.Element("PageContents", {"xmlns": VISIO_NS, "xmlns:r": OFFICE_REL})
    shapes = ET.SubElement(page_xml, "Shapes")
    connects = []
    used = sorted({b.label.icon for b in scene.boxes if b.label.icon in icons})
    media = {name: f"rId{i + 1}" for i, name in enumerate(used)}
    ids = iter(range(1, 10**9))

    def new_shape(kind="Shape", name=None):
        ident = next(ids)
        attrs = {"ID": str(ident), "Type": kind}
        attrs.update(LineStyle="0", FillStyle="0", TextStyle="0")
        if name:
            attrs.update(NameU=name, Name=name)
        return ident, ET.SubElement(shapes, "Shape", attrs)

    def shape2d(x, y, w, h, *, kind="Shape", name=None):
        ident, shape = new_shape(kind, name)
        _cells(
            shape,
            (
                ("PinX", (x + w / 2) / 96),
                ("PinY", (page_height - y - h / 2) / 96),
                ("Width", w / 96),
                ("Height", h / 96),
                ("LocPinX", w / 192),
                ("LocPinY", h / 192),
                ("Angle", 0),
            ),
        )
        return ident, shape

    def stroke(shape, color, pattern, fill=None):
        _cell(shape, "LineWeight", LINE, "PT")
        _cells(
            shape,
            (
                ("LineColor", color),
                ("LinePattern", pattern),
                ("FillForegnd", fill or "#ffffff"),
                ("FillPattern", 1 if fill else 0),
            ),
        )

    def text_only(shape):
        _cells(shape, (("LinePattern", NO_LINE), ("FillPattern", 0)))

    title_lines = scene.title_lines or [scene.title]
    title_size = (scene.width - 96, 33 * len(title_lines))
    _, title = shape2d(48, 39, *title_size, name="Title")
    text_only(title)
    _text(title, [(ln, 22, 33) for ln in title_lines], *title_size, top=0, align=0)

    box_ids = {}
    # Scene preorder puts frames before their children, so they stay underneath.
    for box in scene.boxes:
        shape_kind, line_color, fill = box_style(box)
        ident, shape = shape2d(box.x, box.y, box.width, box.height, name=f"box-{box.id}")
        box_ids[box.id] = ident
        if box.role == "panel-title":
            text_only(shape)
        else:
            pattern = DASHED if box.role == "frame" else DOTTED if _claimed(box) else SOLID
            stroke(shape, line_color, pattern, fill)
            _cell(shape, "ObjType", 1)
            geometry = ET.SubElement(shape, "Section", N="Geometry", IX="0")
            _cells(geometry, (("NoFill", 0), ("NoLine", 0)))
            if shape_kind == "cylinder":
                w, h, cap = box.width / 96, box.height / 96, CYLINDER_CAP / 96
                _row(geometry, "MoveTo", 1, X=0, Y=h - cap)
                _row(geometry, "LineTo", 2, X=0, Y=cap)
                _row(geometry, "EllipticalArcTo", 3, X=w, Y=cap, A=w / 2, B=0, C=0, D=w / 2 / cap)
                _row(geometry, "LineTo", 4, X=w, Y=h - cap)
                _row(geometry, "LineTo", 5, X=0, Y=h - cap)
                rim = ET.SubElement(shape, "Section", N="Geometry", IX="1")
                _cells(rim, (("NoFill", 0), ("NoLine", 0)))
                _row(rim, "Ellipse", 1, X=w / 2, Y=h - cap, A=w, B=h - cap, C=w / 2, D=h)
            else:
                _cell(shape, "Rounding", (28 if shape_kind == "pill" else 6) / 96)
                _rectangle(geometry)
        # Same top inset as _placements(), so text lands where the SVG puts it.
        top = (10 if box.role == "frame" else 16) + box.label.top_pad
        if box.label.icon:
            top += box.label.icon_size + 8
        _text(
            shape,
            [(ln.text, ln.font, ln.height) for ln in box.label.lines],
            box.width,
            box.height,
            top=top,
        )
        if box.label.icon in media:
            size = box.label.icon_size
            x = box.x + (box.width - size) / 2
            _, image = shape2d(x, box.y + 14 + box.label.top_pad, size, size, kind="Foreign")
            _cells(
                image,
                (
                    ("ImgOffsetX", 0),
                    ("ImgOffsetY", 0),
                    ("ImgWidth", size / 96),
                    ("ImgHeight", size / 96),
                ),
            )
            text_only(image)
            foreign = ET.SubElement(
                image, "ForeignData", ForeignType="Bitmap", CompressionType="PNG"
            )
            ET.SubElement(foreign, "Rel", {"r:id": media[box.label.icon]})

    for edge in scene.edges:
        if not edge.points:
            continue
        points = [(x / 96, (page_height - y) / 96) for x, y in edge.points]
        (bx, by), (ex, ey) = points[0], points[-1]
        # A 1-D shape's local x axis runs from its begin point to its end point.
        length = math.hypot(ex - bx, ey - by)
        angle = math.atan2(ey - by, ex - bx) if length else 0.0
        cos, sin = math.cos(angle), math.sin(angle)
        ident, shape = new_shape(name=f"edge-{edge.id}")
        _cells(
            shape,
            (
                ("PinX", (bx + ex) / 2),
                ("PinY", (by + ey) / 2),
                ("Width", length),
                ("Height", 0),
                ("LocPinX", length / 2),
                ("LocPinY", 0),
                ("Angle", angle),
                ("BeginX", bx),
                ("BeginY", by),
                ("EndX", ex),
                ("EndY", ey),
                ("ObjType", 2),
                ("ConFixedCode", 1),
            ),
        )
        dashed = edge.kind in {"lifeline", "response"}
        stroke(shape, EDGE_COLOR, DASHED if dashed else DOTTED if _claimed(edge) else SOLID)
        _cells(
            shape,
            (
                ("BeginArrow", 0),
                ("EndArrow", 0 if edge.kind == "lifeline" else FILLED_ARROW),
                ("EndArrowSize", 1),
            ),
        )
        geometry = ET.SubElement(shape, "Section", N="Geometry", IX="0")
        _cells(geometry, (("NoFill", 1), ("NoLine", 0)))
        for index, (px, py) in enumerate(points):
            dx, dy = px - bx, py - by
            kind = "MoveTo" if index == 0 else "LineTo"
            _row(geometry, kind, index + 1, X=dx * cos + dy * sin, Y=dy * cos - dx * sin)
        for cell_name, part, target in (
            ("BeginX", "9", edge.source_id),
            ("EndX", "12", edge.destination_id),
        ):
            if target in box_ids:
                connects.append(
                    {
                        "FromSheet": str(ident),
                        "FromCell": cell_name,
                        "FromPart": part,
                        "ToSheet": str(box_ids[target]),
                        "ToCell": "PinX",
                        "ToPart": "3",
                    }
                )
        if edge.label:
            b = edge.label
            _, label = shape2d(b.x, b.y, b.width, b.height)
            stroke(label, "#ffffff", NO_LINE, "#ffffff")
            _cell(label, "Rounding", 3 / 96)
            backing = ET.SubElement(label, "Section", N="Geometry", IX="0")
            _cells(backing, (("NoFill", 0), ("NoLine", 1)))
            _rectangle(backing)
            # Edge labels use the same top inset as the SVG exporter.
            _text(
                label,
                [(ln.text, ln.font, ln.height) for ln in b.label.lines],
                b.width,
                b.height,
                top=5,
            )

    key_lines = _key(scene)
    _, key = shape2d(48, scene.key_y - 16, 560, 22 * len(key_lines) + 8, name="Notation key")
    text_only(key)
    _text(key, [(ln, 12, 22) for ln in key_lines], 560, 22 * len(key_lines) + 8, top=0, align=0)
    if connects:
        section = ET.SubElement(page_xml, "Connects")
        for attrs in connects:
            ET.SubElement(section, "Connect", attrs)
    return _vsdx_package(scene, page_xml, media, icons)
