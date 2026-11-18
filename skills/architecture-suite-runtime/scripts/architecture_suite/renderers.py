"""Portable Mermaid and PlantUML text plus shared-scene exports. Rasterization is strictly offline."""

from __future__ import annotations
import base64
from contextlib import contextmanager, nullcontext
import io
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from PIL import Image, ImageChops

try:  # optional: without Playwright, PNGs use an installed Chrome/Edge (ChromeCli)
    from playwright.sync_api import Error as BrowserError, sync_playwright
except ImportError:
    BrowserError = sync_playwright = None
from .scene import build_view_scene_elk, scene_collisions
from .aws import icon_bytes, verify_assets
from .emit import _claimed, render_scene_drawio, render_scene_svg, render_scene_vsdx
from .model import VIEW_FOLDERS
from .overview_layout import (
    build_cloud_scene,
    build_overview_scene,
    normalize_overview_styles,
)
from .readability import readability_findings, score_scene
from .safety import SafetyError, contained_path, run_bounded, safe_text
from .style import box_style, claim_cue, element_visual

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
MIN_PNG_SCALE = 0.5
EXTENSIONS = {"mermaid": "mmd", "drawio": "drawio", "png": "png", "svg": "svg", "visio": "vsdx", "plantuml": "puml"}


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
    if not formats or set(formats) - set(EXTENSIONS):
        raise ValueError("Unsupported output format")
    return [
        base + "." + EXTENSIONS[f]
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
        + "".join(f"#{ord(c)};" if c in '"<>&{}[]|`\\\n\r#' else c for c in str(value))
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
        # An explicit layout direction carries over; auto keeps the portable default.
        "flowchart TB" if view.get("direction") == "down" else "flowchart LR",
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
    # Claims that are not observed: dotted outline/arrow plus the «status» text cue.
    claimed = [ids[b.id] for b in scene.boxes if b.role != "frame" and _claimed(b)]
    links = [str(i) for i, edge in enumerate(scene.edges) if _claimed(edge)]
    if claimed:
        lines.append("  classDef claim stroke-dasharray:3 3")
        lines.append(f"  class {','.join(claimed)} claim")
    if links:
        lines.append(f"  linkStyle {','.join(links)} stroke-dasharray:3 3")
    claims = bool(claimed or links or any(_claimed(b) for b in scene.boxes))
    lines.append(
        '  notation_key["Name · «type» · technology · responsibility#10;Frame = scope; arrow = directed dependency'
        + ("#10;Dotted or «inferred/proposed/unknown» = claim not observed" if claims else "")
        + '"]'
    )
    return "\n".join(lines) + "\n"


def _puml_text(value) -> str:
    """A value that stays text inside a quoted PlantUML macro argument."""
    # Unicode escapes keep quotes, backslashes and creole tags (<b>) from becoming syntax,
    # and stop the preprocessor from running %functions() or expanding $variables.
    escapes = {
        '"': "<U+0022>",
        "\\": "<U+005C>",
        "%": "<U+0025>",
        "$": "<U+0024>",
        "<": "<U+003C>",
        ">": "<U+003E>",
        "\r": "",
        "\n": "\\n",
    }
    # safe_text first, as every other format does: redact credentials, drop control chars.
    return "".join(escapes.get(c, c) for c in safe_text(value or ""))


# C4-PlantUML macros: (plain, cylinder, pill) per element type.
PLANTUML_CARDS = {
    "container": ("Container", "ContainerDb", "ContainerQueue"),
    "component": ("Component", "ComponentDb", "ComponentQueue"),
    "code": ("Component", "ComponentDb", "ComponentQueue"),
}


def render_plantuml(model: dict, view: dict) -> str:
    """C4-PlantUML text from the shared scene; PlantUML computes its own layout."""
    scene = _scene(model, view)
    ids = {b.id: f"n{i}" for i, b in enumerate(scene.boxes)}
    children = {}
    for b in scene.boxes:
        children.setdefault(b.parent_id, []).append(b)
    deployment = view["type"] == "deployment"
    library = (
        "C4_Deployment"
        if deployment
        else "C4_Component"
        if view["type"] in {"component", "code", "overview"}
        else "C4_Container"
    )
    claims = any(_claimed(b) for b in scene.boxes) or any(_claimed(e) for e in scene.edges)
    lines = [
        "@startuml",
        "' Architecture Suite schema 2.0; PlantUML computes its own layout",
        f"!include <C4/{library}>",
        "LAYOUT_TOP_DOWN()" if view.get("direction") == "down" else "LAYOUT_LEFT_RIGHT()",
    ]
    if claims:
        lines += [
            'AddElementTag("claim", $borderStyle=DashedLine(), '
            '$legendText="claim not observed (inferred, proposed or unknown)")',
            'AddRelTag("claim", $lineStyle=DashedLine(), '
            '$legendText="claim not observed (inferred, proposed or unknown)")',
        ]

    def args(*values, tagged=False):
        quoted = ", ".join(f'"{_puml_text(v)}"' for v in values)
        return quoted + (', $tags="claim"' if tagged else "")

    def emit(parent, indent):
        for b in children.get(parent, []):
            element = b.element or {}
            alias = ids[b.id]
            name = element.get("name") or b.label.plain()
            if b.role == "frame":
                kind = element.get("type")
                if deployment:
                    opening = f"Deployment_Node({alias}, {args(name, kind or '')})"
                elif kind == "software_system":
                    opening = f"System_Boundary({alias}, {args(name)})"
                elif kind == "container":
                    opening = f"Container_Boundary({alias}, {args(name)})"
                else:
                    opening = f"Boundary({alias}, {args(name, kind or '')})"
                lines.append(indent + opening + " {")
                emit(b.id, indent + "  ")
                lines.append(indent + "}")
                continue
            kind = element.get("type")
            if not element:
                # Small-multiples panel titles carry no element.
                lines.append(indent + f'rectangle "{_puml_text(b.label.plain())}" as {alias}')
                continue
            cue = claim_cue(element.get("status"))
            description = "\n".join(
                x
                for x in (element.get("description"), *element.get("members", []), cue)
                if x
            )
            tagged = _claimed(b)
            if kind in PLANTUML_CARDS:
                shape = {"cylinder": 1, "pill": 2}.get(box_style(b)[0], 0)
                macro = PLANTUML_CARDS[kind][shape]
                technology = element.get("technology") or element.get("kind", "")
                body = args(name, technology, description, tagged=tagged)
            else:
                macro = "Person" if kind == "person" else "System"
                macro += "_Ext" if element.get("external") else ""
                body = args(name, description, tagged=tagged)
            lines.append(indent + f"{macro}({alias}, {body})")

    emit(None, "")
    for edge in scene.edges:
        text = edge.label.label.plain() if edge.label else "depends on"
        lines.append(
            f"Rel({ids[edge.source_id]}, {ids[edge.destination_id]}, "
            + args(text, tagged=_claimed(edge))
            + ")"
        )
    lines += ["SHOW_LEGEND()", "@enduml"]
    return "\n".join(lines) + "\n"


def render_svg(model: dict, view: dict) -> str:
    return render_scene_svg(_scene(model, view))


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


BROWSER_CHOICES = ("auto", "playwright", "chrome", "chrome-cli")
BROWSER_HELP = (
    "No usable browser for PNG export; run python -m playwright install chromium, "
    "or install Google Chrome or Microsoft Edge"
)
LAUNCH_ARGS = [
    "--disable-background-networking",
    "--disable-component-update",
    "--no-proxy-server",
]


def browser_choice() -> str:
    """The ARCHITECTURE_SUITE_BROWSER setting (the CLI's --browser)."""
    choice = os.environ.get("ARCHITECTURE_SUITE_BROWSER", "auto")
    if choice not in BROWSER_CHOICES:
        raise SafetyError(
            "ARCHITECTURE_SUITE_BROWSER must be auto, playwright, chrome or chrome-cli"
        )
    return choice


def _system_chrome_candidates() -> list[Path]:
    if sys.platform == "win32":
        roots = [
            os.environ.get(name)
            for name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")
        ]
        return [
            Path(root) / exe
            for exe in (
                "Google/Chrome/Application/chrome.exe",
                "Microsoft/Edge/Application/msedge.exe",
            )
            for root in roots
            if root
        ]
    if sys.platform == "darwin":
        return [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        ]
    names = (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "microsoft-edge",
    )
    return [Path(found) for found in map(shutil.which, names) if found]


def find_system_chrome() -> Path | None:
    """An installed Chrome or Edge: ARCHITECTURE_SUITE_CHROME, else the usual locations."""
    override = os.environ.get("ARCHITECTURE_SUITE_CHROME")
    if override:
        path = Path(override).expanduser()
        if not path.is_file():
            raise SafetyError(f"ARCHITECTURE_SUITE_CHROME is not a file: {path}")
        return path
    return next((path for path in _system_chrome_candidates() if path.is_file()), None)


def _playwright_api():
    return None if sync_playwright is None else (sync_playwright, BrowserError)


def _bundled_chromium(p) -> Path | None:
    path = Path(p.chromium.executable_path)
    return path if path.is_file() else None


def _resolve_browser(choice, api, bundled):
    """(engine, executable) for this choice, or None when no browser is usable.

    auto prefers Playwright's own Chromium, then Playwright driving an installed
    Chrome/Edge, then that browser's own headless mode when Playwright is missing.
    """
    if api is None and choice in {"playwright", "chrome"}:
        raise SafetyError(
            f"--browser {choice} needs the playwright package; rerun bootstrap "
            "or use --browser chrome-cli"
        )
    if choice == "playwright" or (choice == "auto" and bundled is not None):
        return ("playwright", bundled) if bundled is not None else None
    system = find_system_chrome()
    if system is None:
        return None
    return ("chrome-cli" if api is None else "chrome"), system


class ChromeCli:
    """Chrome or Edge driven through its own headless screenshot mode, without Playwright.

    Compared with Playwright, offline is enforced by the page's CSP and a DNS block
    rather than request routing, rendering waits a fixed virtual-time budget rather
    than for document.fonts.ready, and each screenshot starts a new browser.
    """

    def __init__(self, executable: Path):
        self.executable = Path(executable)

    # Headless Chrome paints only part of a short window (an 80 px tall window paints
    # 2 rows), so small captures use a larger window and are cropped afterwards.
    MIN_WINDOW = 400

    def screenshot(
        self, html: str, width: int, height: int, *, transparent: bool = False
    ) -> bytes:
        window = (max(width, self.MIN_WINDOW), max(height, self.MIN_WINDOW))
        folder = Path(tempfile.mkdtemp(prefix="architecture-suite-chrome-"))
        try:
            page, output = folder / "page.html", folder / "page.png"
            page.write_text(html, encoding="utf-8")
            run_bounded(
                [
                    str(self.executable),
                    "--headless",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-extensions",
                    *LAUNCH_ARGS,
                    "--host-resolver-rules=MAP * ~NOTFOUND",
                    f"--user-data-dir={folder / 'profile'}",
                    f"--window-size={window[0]},{window[1]}",
                    "--default-background-color="
                    + ("00000000" if transparent else "ffffffff"),
                    "--virtual-time-budget=5000",
                    f"--screenshot={output}",
                    page.as_uri(),
                ],
                timeout_seconds=60.0,
            )
            if not output.is_file():
                raise SafetyError("Headless Chrome wrote no screenshot")
            with Image.open(output) as image:
                if image.size != window:
                    raise SafetyError(
                        f"Headless Chrome screenshot is {image.size}, expected {window}"
                    )
                if window == (width, height):
                    return output.read_bytes()
                buffer = io.BytesIO()
                image.crop((0, 0, width, height)).save(buffer, format="PNG")
                return buffer.getvalue()
        finally:
            _remove_tree(folder)


def _remove_tree(folder: Path, attempts: int = 10) -> None:
    """Remove a ChromeCli temp folder, waiting briefly for browser processes to
    release profile files (Windows refuses to delete files that are still open)."""
    for _ in range(attempts - 1):
        try:
            shutil.rmtree(folder)
            return
        except FileNotFoundError:
            return
        except OSError:
            time.sleep(0.2)
    shutil.rmtree(folder, ignore_errors=True)


def _chrome_cli(executable: Path | None = None) -> ChromeCli:
    executable = executable or find_system_chrome()
    if executable is None:
        raise SafetyError(BROWSER_HELP)
    return ChromeCli(executable)


@contextmanager
def browser_page():
    """A page for rasterizing: a Playwright page, or a ChromeCli without Playwright."""
    choice = browser_choice()
    api = None if choice == "chrome-cli" else _playwright_api()
    if api is None:
        _resolve_browser(choice, api, None)  # explains a missing playwright package
        yield _chrome_cli()
        return
    sync_playwright, BrowserError = api
    fallback = None
    try:
        with sync_playwright() as p:
            found = _resolve_browser(choice, api, _bundled_chromium(p))
            if found is None:
                raise SafetyError(
                    "Local Chromium unavailable; run python -m playwright install chromium"
                    if choice == "playwright"
                    else BROWSER_HELP
                )
            engine, executable = found

            def launch(engine, executable):
                return p.chromium.launch(
                    headless=True,
                    executable_path=None if engine == "playwright" else str(executable),
                    args=LAUNCH_ARGS,
                )

            try:
                browser = launch(engine, executable)
            except BrowserError:
                if choice != "auto":
                    raise
                browser = None
                if engine == "playwright":
                    # auto means "the first that works": only now look for an
                    # installed browser, so a stale override cannot break Chromium.
                    system = find_system_chrome()
                    if system is None:
                        raise
                    engine, executable = "chrome", system
                    try:
                        browser = launch(engine, executable)
                    except BrowserError:
                        pass
                if browser is None:
                    fallback = executable  # the installed browser's own CLI
            if browser is not None:
                try:
                    context = browser.new_context(offline=True, device_scale_factor=1)
                    context.route("**/*", lambda route: route.abort())
                    yield context.new_page()
                finally:
                    browser.close()
    except BrowserError as exc:
        raise SafetyError(
            "Local browser unavailable or rendering failed; run python -m playwright "
            "install chromium, or use --browser chrome with Google Chrome or Microsoft Edge"
        ) from exc
    if fallback is not None:
        yield _chrome_cli(fallback)


def find_browser() -> Path | None:
    """The browser executable PNG export will use, or None when there is none."""
    choice = browser_choice()
    api = None if choice == "chrome-cli" else _playwright_api()
    if api is None:
        found = _resolve_browser(choice, api, None)
    else:
        with api[0]() as p:
            found = _resolve_browser(choice, api, _bundled_chromium(p))
    return found[1] if found else None


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
    # Large overviews are shrunk to fit the caps, but not below half size (text gets unreadable).
    scale = min(
        1, MAX_PNG_WIDTH / max(width, 1), math.sqrt(MAX_PNG_PIXELS / max(width * height, 1))
    )
    if min(width, height) <= 0 or scale < MIN_PNG_SCALE:
        raise SafetyError(
            f"{Path(png_file).name} ({width}x{height}) exceeds PNG size limits "
            f"({MAX_PNG_WIDTH} px wide, {MAX_PNG_PIXELS // 1_000_000} MP) even at half size; "
            "use --format mermaid,svg,drawio for this view, or a smaller --overview-style "
            "such as executive"
        )
    fit = ""
    if scale < 1:
        width, height = math.floor(width * scale), math.floor(height * scale)
        fit = f"<style>body>svg{{display:block;width:{width}px;height:{height}px}}</style>"

    html = (
        '<html><head><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; font-src data:; style-src \'unsafe-inline\'">'
        + fit
        + '</head><body style="margin:0">'
        + svg
        + "</body></html>"
    )

    def capture(active):
        if isinstance(active, ChromeCli):
            path.write_bytes(active.screenshot(html, width, height))
            return
        active.set_viewport_size({"width": width, "height": height})
        active.set_content(
            html,
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


def rasterize_icons(scene, page) -> dict[str, bytes]:
    """PNG copies of the scene's SVG icons at twice their largest drawn size."""
    sizes = {}
    for box in scene.boxes:
        if box.label.icon:
            sizes[box.label.icon] = max(sizes.get(box.label.icon, 0), box.label.icon_size)
    icons = {}
    for name, size in sorted(sizes.items()):
        side = 2 * size
        uri = base64.b64encode(icon_bytes(name)).decode()
        html = (
            '<html><head><meta http-equiv="Content-Security-Policy" '
            "content=\"default-src 'none'; img-src data:; style-src 'unsafe-inline'\">"
            '</head><body style="margin:0">'
            f'<img src="data:image/svg+xml;base64,{uri}" width="{side}" height="{side}" '
            'style="display:block"></body></html>'
        )
        if isinstance(page, ChromeCli):
            icons[name] = page.screenshot(html, side, side, transparent=True)
            continue
        page.set_viewport_size({"width": side, "height": side})
        page.set_content(
            html,
            wait_until="load",
            timeout=30000,
        )
        page.evaluate(
            "async () => { await Promise.all("
            "[...document.images].map(i=>i.decode().catch(()=>{}))); }"
        )
        icons[name] = page.screenshot(
            omit_background=True, animations="disabled", timeout=30000
        )
    return icons


def scene_vsdx(scene, *, page=None) -> bytes:
    """Visio export; icons are rasterized offline, opening a browser only if needed."""
    if not any(box.label.icon for box in scene.boxes):
        return render_scene_vsdx(scene)
    if page is None:
        with browser_page() as active:
            return render_scene_vsdx(scene, rasterize_icons(scene, active))
    return render_scene_vsdx(scene, rasterize_icons(scene, page))


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
    needs_browser = {"png", "visio"} & set(formats)
    with browser_page() if needs_browser else nullcontext(None) as page:
        for base, view in diagram_specs(model, overview_styles, level):
            scene = _scene(model, view)
            for fmt in sorted(formats):
                path = contained_path(output, base + "." + EXTENSIONS[fmt])
                path.parent.mkdir(parents=True, exist_ok=True)
                if fmt == "visio":
                    path.write_bytes(scene_vsdx(scene, page=page))
                elif fmt == "png":
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
                        else render_plantuml(model, view)
                        if fmt == "plantuml"
                        else render_scene_drawio(scene)
                        if fmt == "drawio"
                        else render_scene_svg(scene)
                    )
                    path.write_text(content, encoding="utf-8", newline="\n")
    return [
        f"{base}: {finding['code']}: {', '.join(finding.get('elements', []))}"
        for base, value in verification["diagrams"].items()
        for finding in value["findings"]
    ]
