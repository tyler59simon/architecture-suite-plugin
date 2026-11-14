"""Checksum-pinned ELK 0.9.3 in a bounded local Node process."""

from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import shutil
from .aws import ASSETS
from .safety import SafetyError, run_bounded

ELK_VERSION = "0.9.3"
ELK_SHA256 = "b0745abd7f23cd91690a1587e377edbe19fd7233c783300290936720546216d4"


def layout_graph(graph: dict, *, timeout_seconds: float = 120.0) -> dict:
    bundle = ASSETS / "elk.bundled.js"
    if (
        not bundle.is_file()
        or hashlib.sha256(bundle.read_bytes()).hexdigest() != ELK_SHA256
    ):
        raise SafetyError("ELK 0.9.3 missing or checksum mismatch; run setup")
    host = os.environ.get("ARCHITECTURE_SUITE_LAYOUT_HOST", "auto")
    if host not in {"auto", "node", "browser"}:
        raise SafetyError("ARCHITECTURE_SUITE_LAYOUT_HOST must be node or browser")
    node = os.environ.get("ARCHITECTURE_SUITE_NODE") or shutil.which("node")
    if not node and host == "node":
        raise SafetyError("Node.js is required for offline ELK layout")
    if host == "browser" or not node:
        return _browser_layout(graph, timeout_seconds)
    return json.loads(_layout(json.dumps(graph, sort_keys=True), node, timeout_seconds))


def _browser_layout(graph, timeout):
    from .renderers import browser_page

    with browser_page() as page:
        page.set_default_timeout(timeout * 1000)
        page.set_content("<html><body></body></html>")
        page.add_script_tag(path=str(ASSETS / "elk.bundled.js"))
        return page.evaluate("async graph => await new ELK().layout(graph)", graph)


@lru_cache(maxsize=128)
def _layout(source: str, node: str, timeout: float) -> str:
    return run_bounded(
        [node, str(Path(__file__).with_name("elk-runner.js"))],
        input_text=source,
        timeout_seconds=timeout,
    )
