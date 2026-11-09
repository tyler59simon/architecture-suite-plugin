import io
import json
import zipfile
import xml.etree.ElementTree as ET
from copy import deepcopy

import pytest
from PIL import Image

from architecture_suite import renderers
from architecture_suite.cli import main
from architecture_suite.emit import render_scene_vsdx
from architecture_suite.plan import compile_plan
from architecture_suite.style import box_style

NS = {"v": "http://schemas.microsoft.com/office/visio/2012/main"}


def _package(data: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        return {name: package.read(name) for name in package.namelist()}


def _page(data: bytes) -> ET.Element:
    return ET.fromstring(_package(data)["visio/pages/page1.xml"])


def _cells(shape) -> dict:
    return {c.get("N"): c.get("V") for c in shape.findall("v:Cell", NS)}


def _shapes(page, prefix) -> dict:
    return {
        s.get("NameU")[len(prefix) :]: s
        for s in page.findall("v:Shapes/v:Shape", NS)
        if (s.get("NameU") or "").startswith(prefix)
    }


def _container_scene(model):
    view = next(v for v in model["views"] if v["type"] == "container")
    return renderers._scene(model, view)


def test_vsdx_package_shapes_geometry_and_glue(model):
    scene = _container_scene(model)
    data = renderers.scene_vsdx(scene)
    assert data == renderers.scene_vsdx(scene)  # byte-identical across runs
    parts = _package(data)
    for name in (
        "[Content_Types].xml",
        "_rels/.rels",
        "docProps/core.xml",
        "docProps/app.xml",
        "visio/document.xml",
        "visio/_rels/document.xml.rels",
        "visio/pages/pages.xml",
        "visio/pages/_rels/pages.xml.rels",
        "visio/pages/page1.xml",
    ):
        assert name in parts
    for name, value in parts.items():
        if name.endswith((".xml", ".rels")):
            ET.fromstring(value)
    types = parts["[Content_Types].xml"].decode()
    assert "application/vnd.ms-visio.drawing.main+xml" in types
    assert "application/vnd.ms-visio.page+xml" in types

    page = _page(data)
    boxes, edges = _shapes(page, "box-"), _shapes(page, "edge-")
    assert set(boxes) == {b.id for b in scene.boxes}
    assert set(edges) == {e.id for e in scene.edges if e.points}
    ids = {s.get("NameU"): s.get("ID") for s in page.findall("v:Shapes/v:Shape", NS)}
    connects = {
        (c.get("FromSheet"), c.get("FromCell")): c.get("ToSheet")
        for c in page.findall("v:Connects/v:Connect", NS)
    }
    for edge in scene.edges:
        sheet = ids[f"edge-{edge.id}"]
        assert connects[(sheet, "BeginX")] == ids[f"box-{edge.source_id}"]
        assert connects[(sheet, "EndX")] == ids[f"box-{edge.destination_id}"]
        cells = _cells(edges[edge.id])
        assert float(cells["BeginX"]) == pytest.approx(edge.points[0][0] / 96, abs=1e-5)
        assert float(cells["EndY"]) == pytest.approx(
            (scene.height - edge.points[-1][1]) / 96, abs=1e-5
        )

    box = next(b for b in scene.boxes if b.role != "frame")
    cells = _cells(boxes[box.id])
    # Visio's y axis points up from the bottom of the page.
    assert float(cells["PinX"]) == pytest.approx((box.x + box.width / 2) / 96, abs=1e-5)
    assert float(cells["PinY"]) == pytest.approx(
        (scene.height - box.y - box.height / 2) / 96, abs=1e-5
    )
    assert float(cells["Width"]) == pytest.approx(box.width / 96, abs=1e-5)
    assert boxes[box.id].find("v:Text", NS) is not None
    text = "".join(boxes[box.id].find("v:Text", NS).itertext())
    assert text == box.label.plain()

    frames = [b for b in scene.boxes if b.role == "frame"]
    assert frames and all(_cells(boxes[f.id])["LinePattern"] == "2" for f in frames)
    cylinder = next(b for b in scene.boxes if box_style(b)[0] == "cylinder")
    rows = {r.get("T") for r in boxes[cylinder.id].iter(f"{{{NS['v']}}}Row")}
    assert {"EllipticalArcTo", "Ellipse"} <= rows

    pngs = [v for k, v in parts.items() if k.startswith("visio/media/")]
    icons = {b.label.icon for b in scene.boxes if b.label.icon}
    assert icons and len(pngs) == len(icons)
    for png in pngs:
        with Image.open(io.BytesIO(png)) as image:
            assert image.format == "PNG" and min(image.size) >= 40
    assert len(page.findall(".//v:ForeignData", NS)) == sum(
        1 for b in scene.boxes if b.label.icon
    )


def test_vsdx_claim_cues(plan):
    claimed = deepcopy(plan)
    claimed["containers"][2]["status"] = "proposed"
    target = claimed["containers"][2]["name"]
    index = next(
        i for i, f in enumerate(claimed["flows"]) if target in (f["from"], f["to"])
    )
    claimed["flows"][index]["status"] = "inferred"
    model, _ = compile_plan(claimed)
    ident = next(e["id"] for e in model["elements"] if e["name"] == target)
    scene = _container_scene(model)
    page = _page(renderers.scene_vsdx(scene))
    boxes = _shapes(page, "box-")
    claimed_box = next(b for b in scene.boxes if (b.element or {}).get("id") == ident)
    assert _cells(boxes[claimed_box.id])["LinePattern"] == "3"
    assert any(_cells(s)["LinePattern"] == "3" for s in _shapes(page, "edge-").values())
    text = "".join(page.itertext())
    assert "«proposed»" in text and "claim not observed" in text


def test_vsdx_without_icons_needs_no_browser(model, monkeypatch):
    scene = _container_scene(model)
    for box in scene.boxes:
        box.label.icon = None
    monkeypatch.setattr(renderers, "browser_page", None)  # any browser use would fail
    parts = _package(renderers.scene_vsdx(scene))
    assert not any(name.startswith("visio/media/") for name in parts)
    assert "visio/pages/_rels/page1.xml.rels" not in parts
    assert render_scene_vsdx(scene) == renderers.scene_vsdx(scene)


def test_cli_publishes_visio_on_request(inputs, tmp_path, capsys):
    output = tmp_path / "out"
    argv = ["render", "--model", str(inputs[0]), "--output", str(output)]
    argv += ["--format", "visio", "--level", "container", "--confirm-write"]
    assert main(argv) == 0
    capsys.readouterr()
    diagrams = sorted(p.name for p in output.glob("0*/*") if p.is_file())
    assert diagrams == ["containers.vsdx"]
    drawing = (output / "02-containers/containers.vsdx").read_bytes()
    assert "visio/pages/page1.xml" in _package(drawing)
    default = ["render", "--model", str(inputs[0]), "--output", str(tmp_path / "default")]
    assert main(default + ["--level", "container", "--dry-run"]) == 0
    assert not any(f.endswith(".vsdx") for f in json.loads(capsys.readouterr().out)["files"])


def test_scenario_render_visio(inputs, tmp_path, capsys):
    scenario = tmp_path / "scenario.json"
    scenario.write_text(
        json.dumps(
            {
                "schema_version": "architecture-scenario/v1",
                "name": "Order submission",
                "participants": ["customer", "api"],
                "steps": [{"from": "customer", "to": "api", "description": "Submit order"}],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "scenario"
    argv = ["scenario-render", "--model", str(inputs[0]), "--scenario", str(scenario)]
    assert main(argv + ["--output", str(output), "--format", "visio", "--confirm-write"]) == 0
    assert json.loads(capsys.readouterr().out)["files"] == [
        ".architecture-suite-manifest.json",
        "scenario.vsdx",
    ]
    assert "Submit order" in "".join(_page((output / "scenario.vsdx").read_bytes()).itertext())
