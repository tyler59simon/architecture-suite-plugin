"""Browser selection for PNG and Visio icons: Playwright's Chromium, installed Chrome/Edge,
and Chrome's own headless mode when Playwright is missing."""

import io
import json
import math
import os
import sys
from pathlib import Path

import pytest
from PIL import Image

from architecture_suite import renderers
from architecture_suite.cli import main
from architecture_suite.emit import render_scene_svg
from architecture_suite.layout_host import layout_graph
from architecture_suite.renderers import ChromeCli
from architecture_suite.safety import SafetyError

SYSTEM_CHROME = renderers.find_system_chrome()
needs_chrome = pytest.mark.skipif(
    SYSTEM_CHROME is None, reason="no installed Chrome or Edge"
)
RED = (
    '<html><head><meta http-equiv="Content-Security-Policy" content="default-src '
    "'none'; style-src 'unsafe-inline'\"></head><body style=\"margin:0\">"
    '<div style="width:{w}px;height:{h}px;background:red"></div></body></html>'
)


@pytest.fixture
def fake_chrome(tmp_path, monkeypatch):
    """An installed-browser path that is not a browser, so launching it fails."""
    path = tmp_path / "not-a-browser.exe"
    path.write_bytes(b"not a browser")
    monkeypatch.setenv("ARCHITECTURE_SUITE_CHROME", str(path))
    return path


def test_browser_choice(monkeypatch):
    monkeypatch.delenv("ARCHITECTURE_SUITE_BROWSER", raising=False)
    assert renderers.browser_choice() == "auto"
    monkeypatch.setenv("ARCHITECTURE_SUITE_BROWSER", "chrome-cli")
    assert renderers.browser_choice() == "chrome-cli"
    monkeypatch.setenv("ARCHITECTURE_SUITE_BROWSER", "firefox")
    with pytest.raises(SafetyError, match="must be auto"):
        renderers.browser_choice()


def test_find_system_chrome_override_and_search(tmp_path, monkeypatch, fake_chrome):
    assert renderers.find_system_chrome() == fake_chrome
    monkeypatch.setenv("ARCHITECTURE_SUITE_CHROME", str(tmp_path / "missing.exe"))
    with pytest.raises(SafetyError, match="not a file"):
        renderers.find_system_chrome()
    monkeypatch.delenv("ARCHITECTURE_SUITE_CHROME")
    monkeypatch.setattr(renderers, "_system_chrome_candidates", lambda: [tmp_path / "x"])
    assert renderers.find_system_chrome() is None
    monkeypatch.setattr(renderers, "_system_chrome_candidates", lambda: [fake_chrome])
    assert renderers.find_system_chrome() == fake_chrome


def test_system_chrome_candidates_per_platform(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("ProgramFiles", r"C:\Program Files")
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\u\AppData\Local")
    windows = renderers._system_chrome_candidates()
    assert len(windows) == 4 and windows[0].name == "chrome.exe"
    assert windows[-1].name == "msedge.exe"
    monkeypatch.setattr(sys, "platform", "darwin")
    assert renderers._system_chrome_candidates()[0].name == "Google Chrome"
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        renderers.shutil, "which", lambda name: "/usr/bin/" + name if "edge" in name else None
    )
    assert renderers._system_chrome_candidates() == [Path("/usr/bin/microsoft-edge")]


def test_resolve_browser_order(monkeypatch, fake_chrome):
    api, bundled = object(), Path("chromium")
    resolve = renderers._resolve_browser
    assert resolve("auto", api, bundled) == ("playwright", bundled)
    assert resolve("playwright", api, bundled) == ("playwright", bundled)
    assert resolve("playwright", api, None) is None
    assert resolve("auto", api, None) == ("chrome", fake_chrome)
    assert resolve("chrome", api, bundled) == ("chrome", fake_chrome)
    assert resolve("auto", None, None) == ("chrome-cli", fake_chrome)
    assert resolve("chrome-cli", None, None) == ("chrome-cli", fake_chrome)
    for choice in ("playwright", "chrome"):
        with pytest.raises(SafetyError, match="needs the playwright package"):
            resolve(choice, None, None)
    monkeypatch.setattr(renderers, "find_system_chrome", lambda: None)
    assert resolve("auto", None, None) is None


def test_playwright_api_missing(monkeypatch):
    assert renderers._playwright_api() is not None
    monkeypatch.setattr(renderers, "sync_playwright", None)
    assert renderers._playwright_api() is None


@pytest.mark.browser
def test_browser_page_without_playwright(monkeypatch, fake_chrome):
    monkeypatch.setattr(renderers, "_playwright_api", lambda: None)
    monkeypatch.setenv("ARCHITECTURE_SUITE_BROWSER", "auto")
    with renderers.browser_page() as page:
        assert isinstance(page, ChromeCli) and page.executable == fake_chrome
    assert renderers.find_browser() == fake_chrome
    monkeypatch.setenv("ARCHITECTURE_SUITE_BROWSER", "chrome")
    with pytest.raises(SafetyError, match="needs the playwright package"):
        with renderers.browser_page():
            pass
    monkeypatch.setenv("ARCHITECTURE_SUITE_BROWSER", "auto")
    monkeypatch.setattr(renderers, "find_system_chrome", lambda: None)
    assert renderers.find_browser() is None
    with pytest.raises(SafetyError, match="No usable browser"):
        with renderers.browser_page():
            pass


@pytest.mark.browser
def test_auto_drops_to_chrome_cli_when_launch_fails(monkeypatch, fake_chrome):
    monkeypatch.setattr(renderers, "_bundled_chromium", lambda p: None)
    monkeypatch.setenv("ARCHITECTURE_SUITE_BROWSER", "auto")
    assert renderers.find_browser() == fake_chrome
    with renderers.browser_page() as page:
        assert isinstance(page, ChromeCli) and page.executable == fake_chrome
    monkeypatch.setenv("ARCHITECTURE_SUITE_BROWSER", "chrome")
    with pytest.raises(SafetyError, match="Local browser unavailable"):
        with renderers.browser_page():
            pass
    monkeypatch.setenv("ARCHITECTURE_SUITE_BROWSER", "playwright")
    with pytest.raises(SafetyError, match="Local Chromium unavailable"):
        with renderers.browser_page():
            pass
    monkeypatch.setenv("ARCHITECTURE_SUITE_BROWSER", "auto")
    monkeypatch.setattr(renderers, "find_system_chrome", lambda: None)
    with pytest.raises(SafetyError, match="No usable browser"):
        with renderers.browser_page():
            pass


@pytest.mark.browser
def test_auto_tries_installed_browser_when_bundled_chromium_fails(
    monkeypatch, tmp_path, fake_chrome
):
    """auto means "the first that works": a broken bundled Chromium is not the end."""
    empty = tmp_path / "no-browsers"
    empty.mkdir()
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(empty))  # bundled launch fails
    monkeypatch.setattr(renderers, "_bundled_chromium", lambda p: fake_chrome)
    monkeypatch.setenv("ARCHITECTURE_SUITE_BROWSER", "auto")
    with renderers.browser_page() as page:  # Playwright + installed fails too: its CLI
        assert isinstance(page, ChromeCli) and page.executable == fake_chrome
    monkeypatch.setattr(renderers, "find_system_chrome", lambda: None)
    with pytest.raises(SafetyError, match="Local browser unavailable"):
        with renderers.browser_page():
            pass


@pytest.mark.browser
def test_stale_chrome_override_does_not_break_working_chromium(monkeypatch, tmp_path):
    """The installed-browser fallback is looked up only after Chromium fails."""
    monkeypatch.setenv("ARCHITECTURE_SUITE_CHROME", str(tmp_path / "gone.exe"))
    monkeypatch.setenv("ARCHITECTURE_SUITE_BROWSER", "auto")
    with renderers.browser_page() as page:
        assert not isinstance(page, ChromeCli)


@pytest.mark.browser
def test_browser_layout_needs_playwright(monkeypatch, fake_chrome):
    monkeypatch.setenv("ARCHITECTURE_SUITE_LAYOUT_HOST", "browser")
    monkeypatch.setenv("ARCHITECTURE_SUITE_BROWSER", "chrome-cli")
    with pytest.raises(SafetyError, match="Browser layout needs Playwright"):
        layout_graph({"id": "root", "children": []})


def test_chrome_cli_screenshot_failures(monkeypatch, tmp_path):
    cli = ChromeCli(tmp_path / "chrome.exe")
    monkeypatch.setattr(renderers, "run_bounded", lambda command, **kw: "")
    with pytest.raises(SafetyError, match="wrote no screenshot"):
        cli.screenshot("<html></html>", 500, 500)

    def wrong_size(command, **kw):
        out = next(arg.split("=", 1)[1] for arg in command if arg.startswith("--screenshot="))
        Image.new("RGB", (10, 10), "red").save(out)
        return ""

    monkeypatch.setattr(renderers, "run_bounded", wrong_size)
    with pytest.raises(SafetyError, match="expected"):
        cli.screenshot("<html></html>", 500, 500)


def test_browser_flag_is_restored_after_the_call(monkeypatch):
    monkeypatch.delenv("ARCHITECTURE_SUITE_BROWSER", raising=False)
    seen = []
    monkeypatch.setattr(
        "architecture_suite.cli.cmd_doctor",
        lambda args: seen.append(renderers.browser_choice()) or 0,
    )
    assert main(["--browser", "playwright", "doctor"]) == 0
    assert seen == ["playwright"]
    assert "ARCHITECTURE_SUITE_BROWSER" not in os.environ


def test_remove_tree_waits_for_open_files(monkeypatch, tmp_path):
    folder = tmp_path / "profile"
    folder.mkdir()
    real, calls = renderers.shutil.rmtree, []

    def busy_once(path, **kw):
        calls.append(kw)
        if len(calls) == 1:
            raise PermissionError("file in use")
        return real(path, **kw)

    monkeypatch.setattr(renderers.shutil, "rmtree", busy_once)
    monkeypatch.setattr(renderers.time, "sleep", lambda seconds: None)
    renderers._remove_tree(folder)
    assert not folder.exists() and len(calls) == 2
    renderers._remove_tree(folder)  # already gone
    folder.mkdir()

    def always_busy(path, **kw):
        if not kw.get("ignore_errors"):
            raise PermissionError("file in use")

    monkeypatch.setattr(renderers.shutil, "rmtree", always_busy)
    renderers._remove_tree(folder, attempts=3)  # gives up quietly after the retries


@needs_chrome
@pytest.mark.parametrize("size",[(80, 80), (660, 120), (500, 500)])
@pytest.mark.browser
def test_chrome_cli_paints_the_whole_capture(size):
    # Headless Chrome paints only part of a short window; captures must still be full.
    width, height = size
    data = ChromeCli(SYSTEM_CHROME).screenshot(
        RED.format(w=width, h=height), width, height, transparent=True
    )
    with Image.open(io.BytesIO(data)) as image:
        assert image.size == size
        assert image.convert("RGBA").getextrema() == ((255, 255), (0, 0), (0, 0), (255, 255))


@needs_chrome
@pytest.mark.parametrize("choice", [
    pytest.param("chrome", marks=pytest.mark.skipif(
        bool(os.environ.get("CI")),
        reason="known limit in 1.3.0: Page.screenshot times out with the installed Chrome "
        "on CI runners (Linux and Windows); it works on a desktop",
    )),
    "chrome-cli",
])
@pytest.mark.browser
@pytest.mark.slow
def test_installed_chrome_renders_png_and_icons(choice, model, monkeypatch, tmp_path):
    monkeypatch.setenv("ARCHITECTURE_SUITE_BROWSER", choice)
    view = next(v for v in model["views"] if v["type"] == "container")
    scene = renderers._scene(model, view)
    output = tmp_path / "container.png"
    renderers.render_svg_png(render_scene_svg(scene), output, scene.width, scene.height)
    assert renderers.validate_png(output) == (math.ceil(scene.width), math.ceil(scene.height))
    with renderers.browser_page() as page:
        icons = renderers.rasterize_icons(scene, page)
    assert icons
    for data in icons.values():
        with Image.open(io.BytesIO(data)) as icon:
            assert icon.convert("RGBA").getchannel("A").getbbox() is not None


@needs_chrome
@pytest.mark.browser
@pytest.mark.slow
def test_cli_browser_flag_reaches_doctor(monkeypatch, capsys):
    monkeypatch.setenv("ARCHITECTURE_SUITE_BROWSER", "auto")
    assert main(["--browser", "chrome-cli", "doctor"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["browser"] == "ok" and result["browser_engine"] == "chrome-cli"
    assert Path(result["browser_path"]) == SYSTEM_CHROME
    assert renderers.browser_choice() == "auto"  # the flag applies to that call only
