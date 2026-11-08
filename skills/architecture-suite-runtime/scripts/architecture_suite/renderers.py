"""Portable Mermaid plus shared-scene exports. Rasterization is strictly offline."""

from __future__ import annotations
from contextlib import contextmanager
import math
from pathlib import Path
from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright, Error as BrowserError
from .c4_layout import build_view_scene_elk
from .aws import verify_assets
from .emit import render_scene_drawio, render_scene_svg
from .model import VIEW_FOLDERS
from .overview_layout import (
    build_aws_scene,
    build_cloud_scene,
    build_gcp_scene,
    build_overview_scene,
    normalize_overview_styles,
)
from .readability import readability_findings, score_scene
from .safety import SafetyError, contained_path
from .style import box_style, element_visual
from .scene import scene_collisions

ARTIFACT_LEVELS = (
    "all",
    "system",
    "container",
    "component",
    "code",
    "overview",
    "deployment",
)
ARTIFACT_VIEW_TYPES = {
    "system": "context",
    "container": "container",
    "component": "component",
    "code": "code",
}
MAX_PNG_WIDTH = 6000
MAX_PNG_PIXELS = 24_000_000


def normalize_artifact_level(level: str = "all") -> str:
    if level not in ARTIFACT_LEVELS:
        raise ValueError("Unknown artifact level")
    return level


def diagram_specs(
    model: dict, overview_styles=None, level: str = "all"
) -> list[tuple[str, dict]]:
    normalize_artifact_level(level)
    specs = [
        (f"{VIEW_FOLDERS[v['type']]}/{v['id']}", v)
        for v in model["views"]
        if level == "all" or v["type"] == ARTIFACT_VIEW_TYPES.get(level)
    ]
    if level in {"all", "overview"}:
        specs.extend(
            (
                f"05-overview/overview-{s}",
                {"type": "overview", "style": s, "id": "overview-" + s},
            )
            for s in normalize_overview_styles(overview_styles)
        )
    if level in {"all", "deployment"} and model.get("deployment"):
        provider = model["deployment"].get("provider", "aws")
        specs.append(
            (
                f"06-{provider}-deployment/{provider}-deployment",
                {"type": "deployment", "id": f"{provider}-deployment"},
            )
        )
    return specs


def expected_artifact_paths(
    model: dict, formats: set[str], overview_styles=None, level: str = "all"
) -> list[str]:
    extensions = {"mermaid": "mmd", "drawio": "drawio", "png": "png", "svg": "svg"}
    if not formats or set(formats) - set(extensions):
        raise ValueError("Unsupported output format")
    return [
        base + "." + extensions[f]
        for base, _ in diagram_specs(model, overview_styles, level)
        for f in sorted(formats)
    ]


def _scene(model, view):
    if view["type"] == "overview":
        return build_overview_scene(model, view["style"])
    if view["type"] == "deployment":
        return build_cloud_scene(model)
    return build_view_scene_elk(model, view)


def _quoted(value):
    # Mermaid entity codes prevent labels from becoming syntax, directives, or HTML.
    return (
        '"'
        + "".join(f"#{ord(c)};" if c in '"<>&{}[]|`\\\n\r' else c for c in str(value))
        + '"'
    )


def render_mermaid(model: dict, view: dict) -> str:
    """A portable flowchart preserves C4 stereotypes, scopes, members, and arrows."""
    scene = _scene(model, view)
    ids = {b.id: f"n{i}" for i, b in enumerate(scene.boxes)}
    children = {}
    for b in scene.boxes:
        children.setdefault(b.parent_id, []).append(b)
    lines = [
        "%% Architecture Suite schema 2.0; portable layout is independent of ELK",
        "flowchart LR",
    ]

    def emit(parent, indent):
        for b in children.get(parent, []):
            if b.role == "frame":
                lines.append(
                    indent + f"subgraph {ids[b.id]}[{_quoted(b.label.plain())}]"
                )
                emit(b.id, indent + "  ")
                # Mermaid requires a member for an otherwise empty frame.
                if not children.get(b.id):
                    lines.append(
                        indent
                        + f"  {ids[b.id]}_empty[{_quoted('No established contents')}]"
                    )
                lines.append(indent + "end")
            else:
                text = _quoted(b.label.plain())
                shape = box_style(b)[0]
                opening, closing = {
                    "cylinder": ("[(", ")]"),
                    "pill": ("([", "])"),
                }.get(shape, ("[", "]"))
                lines.append(indent + f"{ids[b.id]}{opening}{text}{closing}")
                if element_visual(b.element):
                    _, stroke, fill = box_style(b)
                    lines.append(
                        indent + f"style {ids[b.id]} fill:{fill},stroke:{stroke}"
                    )

    emit(None, "  ")
    for edge in scene.edges:
        text = edge.label.label.plain() if edge.label else "depends on"
        lines.append(
            f"  {ids[edge.source_id]} -->|{_quoted(text)}| {ids[edge.destination_id]}"
        )
    lines.append(
        '  notation_key["Name · «type» · technology · responsibility#10;Frame = scope; arrow = directed dependency"]'
    )
    return "\n".join(lines) + "\n"


def render_svg(model: dict, view: dict) -> str:
    return render_scene_svg(_scene(model, view))


def render_drawio(model: dict, view: dict) -> str:
    return render_scene_drawio(_scene(model, view))


def layout_measurements(model: dict, overview_styles=None, level: str = "all") -> dict:
    return {
        base: {"width": scene.width, "height": scene.height, **score_scene(scene)}
        for base, view in diagram_specs(model, overview_styles, level)
        for scene in [_scene(model, view)]
    }


def layout_report(model: dict, overview_styles=None, level: str = "all") -> dict:
    results = {}
    for base, view in diagram_specs(model, overview_styles, level):
        scene = _scene(model, view)
        results[base] = {
            "findings": scene_collisions(scene) + readability_findings(scene),
            **score_scene(scene),
        }
    return {"ok": not any(v["findings"] for v in results.values()), "diagrams": results}


def verify_model_layout(
    model: dict, overview_styles=None, *, level: str = "all"
) -> tuple[int, list[str]]:
    report = layout_report(model, overview_styles, level)
    return len(report["diagrams"]), [
        f"{base}: {finding['code']}: {', '.join(finding.get('elements', []))}"
        for base, value in report["diagrams"].items()
        for finding in value["findings"]
    ]


def measure_model_layout(
    model: dict, overview_styles=None, *, level: str = "all"
) -> tuple[list[str], dict]:
    values = layout_measurements(model, overview_styles, level)
    advisories = [f"{base}: {a}" for base, v in values.items() for a in v["advisories"]]
    return advisories, {
        "scenes": float(len(values)),
        "crossings": sum(v["crossings"] for v in values.values()),
        "bends": sum(v["bends"] for v in values.values()),
        "worst_aspect_ratio": max(
            (v["aspect_ratio"] for v in values.values()), default=0
        ),
    }


def render_overview_mermaid(model: dict, style: str = "progressive") -> str:
    return render_mermaid(model, {"type": "overview", "style": style})


def render_overview_drawio(model: dict, style: str = "progressive") -> str:
    return render_scene_drawio(build_overview_scene(model, style))


def render_overview_svg(model: dict, style: str = "progressive") -> str:
    return render_scene_svg(build_overview_scene(model, style))


def render_aws_deployment_mermaid(model: dict) -> str:
    return render_mermaid(model, {"type": "deployment"})


def render_aws_deployment_drawio(model: dict) -> str:
    return render_scene_drawio(build_aws_scene(model))


def render_aws_deployment_svg(model: dict) -> str:
    return render_scene_svg(build_aws_scene(model))


def render_gcp_deployment_mermaid(model: dict) -> str:
    return render_mermaid(model, {"type": "deployment"})


def render_gcp_deployment_drawio(model: dict) -> str:
    return render_scene_drawio(build_gcp_scene(model))


def render_gcp_deployment_svg(model: dict) -> str:
    return render_scene_svg(build_gcp_scene(model))


@contextmanager
def browser_page():
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-background-networking",
                    "--disable-component-update",
                    "--no-proxy-server",
                ],
            )
            try:
                context = browser.new_context(offline=True, device_scale_factor=1)
                context.route("**/*", lambda route: route.abort())
                yield context.new_page()
            finally:
                browser.close()
    except BrowserError as exc:
        raise SafetyError(
            "Local Chromium unavailable or rendering failed; run python -m playwright install chromium"
        ) from exc


def find_browser() -> Path | None:
    with sync_playwright() as p:
        path = Path(p.chromium.executable_path)
        return path if path.is_file() else None


def validate_png(path: Path) -> tuple[int, int]:
    with Image.open(path) as im:
        im.load()
        if (
            im.format != "PNG"
            or min(im.size) < 10
            or im.width > MAX_PNG_WIDTH
            or im.width * im.height > MAX_PNG_PIXELS
        ):
            raise SafetyError("Invalid PNG dimensions or format")
        rgb = im.convert("RGB")
        diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, "white")).convert(
            "L"
        )
        ink = sum(count for value, count in enumerate(diff.histogram()) if value > 20)
        if ink / (im.width * im.height) < 0.002:
            raise SafetyError("PNG is blank or nearly blank")
        return im.size


def render_svg_png(
    svg_file: str | Path, png_file: Path, width: float, height: float, *, page=None
) -> None:
    svg = (
        svg_file.read_text(encoding="utf-8") if isinstance(svg_file, Path) else svg_file
    )
    path = png_file
    width, height = math.ceil(width), math.ceil(height)
    if (
        width > MAX_PNG_WIDTH
        or width * height > MAX_PNG_PIXELS
        or min(width, height) <= 0
    ):
        raise SafetyError(
            "PNG exceeds browser size limits; choose narrower scopes or another format"
        )

    def capture(active):
        active.set_viewport_size({"width": width, "height": height})
        active.set_content(
            '<html><head><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; font-src data:; style-src \'unsafe-inline\'"></head><body style="margin:0">'
            + svg
            + "</body></html>",
            wait_until="load",
            timeout=30000,
        )
        active.evaluate(
            "async () => { await document.fonts.ready; await Promise.all([...document.images].map(i=>i.decode().catch(()=>{}))); }"
        )
        active.screenshot(path=str(path), animations="disabled", timeout=30000)

    if page is None:
        with browser_page() as active:
            capture(active)
    else:
        capture(page)
    validate_png(path)


def write_rendered_artifacts(
    model: dict,
    output: Path,
    formats: set[str],
    overview_styles=None,
    level: str = "all",
    *,
    allow_layout_findings: bool = False,
) -> list[str]:
    verify_assets()
    expected_artifact_paths(model, formats, overview_styles, level)
    verification = layout_report(model, overview_styles, level)
    if not verification["ok"] and not allow_layout_findings:
        raise SafetyError(
            "Layout verification failed; inspect verify findings before publishing"
        )
    from contextlib import nullcontext

    with browser_page() if "png" in formats else nullcontext(None) as page:
        for base, view in diagram_specs(model, overview_styles, level):
            scene = _scene(model, view)
            for fmt in sorted(formats):
                ext = {
                    "mermaid": "mmd",
                    "drawio": "drawio",
                    "svg": "svg",
                    "png": "png",
                }[fmt]
                path = contained_path(output, base + "." + ext)
                path.parent.mkdir(parents=True, exist_ok=True)
                if fmt == "png":
                    render_svg_png(
                        render_scene_svg(scene),
                        path,
                        scene.width,
                        scene.height,
                        page=page,
                    )
                else:
                    content = (
                        render_mermaid(model, view)
                        if fmt == "mermaid"
                        else render_scene_drawio(scene)
                        if fmt == "drawio"
                        else render_scene_svg(scene)
                    )
                    path.write_text(content, encoding="utf-8")
    return [
        f"{base}: {finding['code']}: {', '.join(finding.get('elements', []))}"
        for base, value in verification["diagrams"].items()
        for finding in value["findings"]
    ]
