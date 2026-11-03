from copy import deepcopy
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import pytest
from PIL import Image
from architecture_suite import renderers
from architecture_suite.c4_layout import build_view_scene_elk
from architecture_suite.emit import render_scene_drawio, render_scene_svg
from architecture_suite.layout_host import layout_graph
from architecture_suite.overview_layout import (
    build_aws_scene,
    build_overview_scene,
    normalize_overview_styles,
)
from architecture_suite.readability import readability_findings, score_scene
from architecture_suite.safety import SafetyError
from architecture_suite.scene import Box, Edge, Scene, build_scene, scene_collisions
from architecture_suite.style import (
    Label,
    TextLine,
    element_label,
    line_height,
    text_width,
    wrap_to_width,
)

ROOT = Path(__file__).resolve().parents[1]


def test_measured_labels_and_unicode():
    text = (
        "Long \u0627\u0644\u0639\u0631\u0628\u064a\u0629 Unicode caf\u00e9 \u6771\u4eac label with many words and "
        + "verylongidentifier" * 10
    )
    lines = wrap_to_width(text, 180)
    assert len(lines) > 3
    assert all(text_width(line) <= 180 for line in lines)
    assert "".join(lines).replace(" ", "") == text.replace(" ", "")
    assert line_height(12) >= 12
    label = Label([TextLine("text", 12)], icon="AWS-Lambda")
    assert label.height > label.lines[0].height and label.width == label.lines[0].width
    assert label.plain() == "text"
    with pytest.raises(ValueError):
        wrap_to_width("tiny", 1)
    code = element_label(
        {
            "id": "x",
            "name": "Type",
            "description": "A class",
            "type": "code",
            "members": ["+run(): Result"],
            "cloud": {"service": "AWS-Lambda"},
        }
    )
    assert code.icon is None and any("run()" in ln.text for ln in code.lines)
    assert not any(
        "run()" in ln.text
        for ln in element_label(
            {"name": "Type", "type": "code", "members": ["+run()"]}, compact=True
        ).lines
    )


def test_all_views_geometry_and_determinism(model):
    assert normalize_overview_styles("all") == normalize_overview_styles(
        ["complete,executive", "progressive,hierarchy,small-multiples"]
    )
    with pytest.raises(ValueError):
        normalize_overview_styles([])
    with pytest.raises(ValueError):
        normalize_overview_styles("made-up")
    report = renderers.layout_report(model, ["all"])
    assert report["ok"], report
    dimensions = renderers.layout_measurements(model, ["all"])
    assert len(dimensions) == 13
    assert all(v["width"] > 400 and v["height"] > 200 for v in dimensions.values())
    for view in model["views"]:
        first = build_view_scene_elk(model, view)
        assert first.as_dict() == build_view_scene_elk(model, view).as_dict()
    hierarchy = build_overview_scene(model, "hierarchy")
    assert not hierarchy.edges
    complete = build_overview_scene(model, "complete")
    assert all(e["name"] in render_scene_svg(complete) for e in model["elements"])
    executive = build_overview_scene(model, "executive")
    assert "RequestHandler" not in render_scene_svg(executive)
    assert "Drill-down" in render_scene_svg(executive)
    aws = build_aws_scene(model)
    assert any(b.element.get("type") == "subnet" for b in aws.boxes if b.element)


def test_empty_cycles_disconnected_long_labels_and_groups(model):
    elements = [
        {
            "id": f"n{i}",
            "name": f"Module {i}",
            "type": "code",
            "description": "Shared module",
            "members": ["+run(): Result"],
        }
        for i in range(5)
    ]
    elements[0]["name"] = "Unicode cafÃ©: " + "a long name " * 20
    relationships = [
        {
            "id": f"r{i}",
            "source_id": f"n{i}",
            "destination_id": f"n{(i + 1) % 4}",
            "description": "Calls " + "with a measured long purpose " * 3,
        }
        for i in range(4)
    ]
    scene = build_scene(
        "Cycles and disconnected modules", elements, relationships, direction="right"
    )
    assert not scene_collisions(scene)
    assert len(scene.boxes) == 5 and len(scene.edges) == 4
    empty = build_scene("Empty evidence", [], [])
    assert not scene_collisions(empty)
    assert "Empty evidence" in render_scene_svg(empty)
    for e in model["elements"]:
        if e["id"] in {"order-queue", "order-store"}:
            e["group"] = "Data"
    view = next(v for v in model["views"] if v["type"] == "container")
    scene = build_view_scene_elk(model, view)
    assert any(b.element.get("type") == "group" for b in scene.boxes if b.element)
    assert not scene_collisions(scene)


def test_collision_detection_identifies_actual_failures():
    lab = Label([TextLine("some content")])
    parent = Box("p", "frame", 40, 100, 300, 240, lab)
    a = Box("a", "card", 60, 150, 140, 80, lab, "p")
    b = Box("b", "card", 130, 170, 140, 80, lab, "p")
    outside = Box("o", "card", 690, 40, 60, 10, lab, "p")
    label = Box("l", "edge-label", 130, 170, 40, 10, lab)
    edges = [
        Edge("e", "a", "o", [(50, 200), (400, 200)], label),
        Edge("f", "o", "a", [(150, 120), (150, 300)], deepcopy(label)),
    ]
    scene = Scene("Bad", 700, 500, [parent, a, b, outside], edges, ["Bad"], 100, 450)
    codes = {f["code"] for f in scene_collisions(scene)}
    assert {
        "page-bounds",
        "label-bounds",
        "containment",
        "box-overlap",
        "edge-label-bounds",
        "edge-label-overlap",
        "edge-through-card",
    } <= codes
    assert score_scene(scene)["crossings"] == 1
    scene.boxes *= 10
    scene.width = 5000
    assert len(score_scene(scene)["advisories"]) == 2


def test_shared_tracks_and_readability_gates():
    label = Label([TextLine("edge")])
    a = Box("a", "card", 0, 100, 100, 100, label)
    b = Box("b", "card", 300, 100, 100, 100, label)
    middle = Box("label", "edge-label", 150, 120, 50, 20, label)
    edges = [
        Edge("first", "a", "b", [(100, 130), (300, 130)], middle),
        Edge("second", "a", "b", [(100, 130), (300, 130)]),
    ]
    scene = Scene("tracks", 500, 400, [a, b], edges, ["tracks"], 100, 350)
    codes = {f["code"] for f in scene_collisions(scene)}
    assert {"edge-shared-track", "edge-through-label"} <= codes
    assert not readability_findings(scene)
    # A deliberately wandering route with seven bends and little direct progress.
    points = [
        (100, 130),
        (2000, 130),
        (2000, 600),
        (0, 600),
        (0, 700),
        (2000, 700),
        (2000, 140),
        (200, 140),
        (200, 130),
    ]
    scene.edges = [Edge("wander", "a", "b", points)]
    scene.height = 10000
    codes = {f["code"] for f in readability_findings(scene)}
    assert {"readability-bends", "readability-aspect", "readability-detour"} <= codes
    scene.width = scene.height = 1000
    scene.edges = [
        Edge(f"v{i}", "a", "b", [(i * 10, 0), (i * 10, 500)]) for i in range(5)
    ] + [
        Edge(f"h{i}", "a", "b", [(-5, i * 10 + 5), (100, i * 10 + 5)]) for i in range(5)
    ]
    assert any(
        f["code"] == "readability-crossings" for f in readability_findings(scene)
    )


def test_dense_relationships_remain_in_scene():
    elements = [
        {
            "id": f"n{i}",
            "name": f"Node {i}",
            "type": "container",
            "description": "Dense fixture",
        }
        for i in range(8)
    ]
    relationships = [
        {
            "id": f"r{i}-{j}",
            "source_id": f"n{i}",
            "destination_id": f"n{j}",
            "description": f"Depends {i} to {j}",
        }
        for i in range(8)
        for j in range(i + 1, 8)
    ]
    scene = build_scene("Dense", elements, relationships)
    assert len(scene.boxes) == 8 and len(scene.edges) == 28
    assert all(edge.label and len(edge.points) >= 2 for edge in scene.edges)
    assert (
        len(ET.fromstring(render_scene_drawio(scene)).findall(".//mxCell[@edge='1']"))
        == 28
    )


def test_all_generated_formats_are_valid():
    samples = ROOT / "examples/starter-systems"
    assert len(list(samples.rglob("*.png"))) == 39
    for path in samples.rglob("*"):
        if path.suffix in {".svg", ".drawio"}:
            root = ET.fromstring(path.read_text(encoding="utf-8"))
            assert root.tag.endswith("svg") or root.tag == "mxfile"
            for element in root.iter():
                for key, value in element.attrib.items():
                    if key.endswith("href"):
                        assert value.startswith(("data:", "#"))
        if path.suffix == ".png":
            assert renderers.validate_png(path)


def test_export_xml_and_shared_geometry(model):
    view = model["views"][1]
    scene = build_view_scene_elk(model, view)
    svg = renderers.render_svg(model, view)
    svg_root = ET.fromstring(svg)
    drawio = renderers.render_drawio(model, view)
    drawio_root = ET.fromstring(drawio)
    assert svg == render_scene_svg(scene)
    assert drawio == render_scene_drawio(scene)
    cell_ids = {box.id: f"n{i}" for i, box in enumerate(scene.boxes)}
    for box in scene.boxes:
        xml = next(e for e in svg_root.iter() if e.get("id") == "box-" + box.id)
        assert float(xml.get("x")) == box.x and float(xml.get("height")) == box.height
        cell = drawio_root.find(f".//mxCell[@id='{cell_ids[box.id]}']/mxGeometry")
        parent = next((b for b in scene.boxes if b.id == box.parent_id), None)
        assert float(cell.get("x")) == box.x - (parent.x if parent else 0)
    # Every referenced SVG resource is internal, and every AWS image is embedded.
    for e in svg_root.iter():
        for key, value in e.attrib.items():
            if key.endswith("href"):
                assert value.startswith("data:") or value.startswith("#")
    assert "data:image/svg+xml;base64," in svg
    assert not re.search(r'(?:src|href)="https?://', svg)
    assert "image=data:image/svg+xml," in drawio
    for index, edge in enumerate(scene.edges):
        cell = drawio_root.find(f".//mxCell[@id='e{index}']")
        assert cell.get("source") == cell_ids[edge.source_id]
        assert cell.get("target") == cell_ids[edge.destination_id]
    source = renderers.render_mermaid(model, view)
    assert source.startswith("%% Architecture Suite") and "«container»" in source


def test_unicode_visual_text_bounds():
    element = {
        "id": "unicode",
        "name": "caf\u00e9 \u6771\u4eac \u0627\u0644\u0639\u0631\u0628\u064a\u0629 "
        * 4,
        "type": "container",
        "description": "Unicode responsibilities \u03b1\u03b2\u03b3",
    }
    scene = build_scene("Unicode", [element], [])
    box = scene.boxes[0]
    with renderers.browser_page() as page:
        page.set_content(render_scene_svg(scene))
        page.evaluate("document.fonts.ready")
        widths = page.locator("svg text").evaluate_all(
            "nodes => nodes.map(n => n.getBBox().width)"
        )
        assert all(width <= box.width - 20 for width in widths[1:-4])


def test_missing_chromium_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "missing-browser"))
    assert renderers.find_browser() is None
    with pytest.raises(SafetyError, match="Chromium"):
        with renderers.browser_page():
            pass


def test_png_offline_and_blank_detection(tmp_path, model):
    view = model["views"][0]
    scene = build_view_scene_elk(model, view)
    output = tmp_path / "context.png"
    renderers.render_svg_png(render_scene_svg(scene), output, scene.width, scene.height)
    assert renderers.validate_png(output) == (int(scene.width), int(scene.height))
    Image.new("RGB", (100, 100), "white").save(tmp_path / "blank.png")
    with pytest.raises(SafetyError, match="blank"):
        renderers.validate_png(tmp_path / "blank.png")
    Image.new("RGB", (2, 2), "black").save(tmp_path / "tiny.png")
    with pytest.raises(SafetyError):
        renderers.validate_png(tmp_path / "tiny.png")
    with pytest.raises(SafetyError):
        renderers.render_svg_png("<svg/>", output, 6001, 100)


def test_export_write_and_failure_gate(model, tmp_path, monkeypatch):
    assert renderers.normalize_artifact_level() == "all"
    with pytest.raises(ValueError):
        renderers.normalize_artifact_level("dynamic")
    with pytest.raises(ValueError):
        renderers.expected_artifact_paths(model, {"pdf"})
    for level in renderers.ARTIFACT_LEVELS:
        assert renderers.expected_artifact_paths(
            model, {"mermaid"}, ["executive"], level
        )
    result = renderers.write_rendered_artifacts(
        model, tmp_path, {"mermaid", "svg", "drawio", "png"}, ["executive"], "system"
    )
    assert not result
    assert len(list(tmp_path.rglob("*.*"))) == 4
    monkeypatch.setattr(
        renderers, "layout_report", lambda *a, **kw: {"ok": False, "diagrams": {}}
    )
    with pytest.raises(SafetyError):
        renderers.write_rendered_artifacts(
            model, tmp_path, {"mermaid"}, level="container"
        )
    renderers.write_rendered_artifacts(
        model, tmp_path, {"mermaid"}, level="container", allow_layout_findings=True
    )


def test_elk_missing_dependency_and_corruption(monkeypatch, tmp_path):
    from architecture_suite import layout_host

    monkeypatch.setattr(layout_host.shutil, "which", lambda n: None)
    monkeypatch.setenv("ARCHITECTURE_SUITE_LAYOUT_HOST", "node")
    with pytest.raises(SafetyError, match="Node"):
        layout_graph({"id": "root"})
    monkeypatch.setattr(layout_host, "ASSETS", tmp_path)
    (tmp_path / "elk.bundled.js").write_text("corrupt")
    with pytest.raises(SafetyError, match="checksum"):
        layout_graph({"id": "root"})


def test_parse_and_render_every_mermaid_example_offline(tmp_path):
    files = sorted((ROOT / "examples").rglob("*.mmd"))
    assert len(files) >= 40
    # Pinned primary Mermaid implementation, in the same local Chromium used for PNGs.
    script = ROOT / "node_modules/mermaid/dist/mermaid.min.js"
    with renderers.browser_page() as page:
        requests = []
        page.on("request", lambda request: requests.append(request.url))
        page.set_content("<html><body></body></html>")
        page.add_script_tag(path=str(script))
        page.evaluate(
            "mermaid.initialize({startOnLoad:false,securityLevel:'strict',fontFamily:'Arial'})"
        )
        for index, path in enumerate(files):
            source = path.read_text(encoding="utf-8")
            result = page.evaluate(
                "async ({source,id})=>{await mermaid.parse(source); const r=await mermaid.render(id,source); const el=document.createElement('div');el.innerHTML=r.svg;return new XMLSerializer().serializeToString(el.querySelector('svg'))}",
                {"source": source, "id": f"m{index}"},
            )
            assert ET.fromstring(result).tag.endswith("svg"), path
            (tmp_path / f"{index}.svg").write_text(result, encoding="utf-8")
        assert not [r for r in requests if r.startswith("http")]


def test_reserved_renderer_names_do_not_collide():
    elements = [
        {
            "id": ident,
            "name": ident,
            "type": "container",
            "description": "Reserved-name regression",
        }
        for ident in ("root", "arrow", "title", "key", "0", "1")
    ]
    scene = build_scene("Reserved IDs", elements, [])
    assert len(scene.boxes) == 6
    for content in (render_scene_svg(scene), render_scene_drawio(scene)):
        ids = [e.get("id") for e in ET.fromstring(content).iter() if e.get("id")]
        assert len(ids) == len(set(ids))
