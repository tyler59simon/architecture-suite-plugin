"""Measured wrapping shared by every exporter; no label truncation."""

from __future__ import annotations
from dataclasses import dataclass, field
from functools import lru_cache
import math
import unicodedata
from PIL import ImageFont
from .aws import ASSETS, icon_available
from .safety import safe_text

INK = "#172b4d"
ELEMENT_STYLES = {
    "person": ("#08427b", "#e4f1ff"),
    "software_system": ("#1168bd", "#e4f1ff"),
    "container": ("#438dd5", "#edf6ff"),
    "component": ("#65a6df", "#f2f8ff"),
    "code": ("#94a3b8", "#ffffff"),
}


# Cloud-annotated elements get a role-specific shape and colour so data stores,
# queues and ML endpoints are recognisable without reading the label.
CYLINDER_CAP = 10  # elliptical cap radius, px
CAP_PAD = 12  # extra label inset so text clears the top cap


@dataclass(frozen=True)
class Visual:
    kind: str
    shape: str  # rect | cylinder | pill
    stroke: str
    fill: str


KIND_STYLES = {
    "database": ("cylinder", "#2e7d32", "#eaf6ec"),
    "storage": ("cylinder", "#00838f", "#e4f5f7"),
    "messaging": ("pill", "#e65100", "#fff3e6"),
    "ml": ("rect", "#7b1fa2", "#f5eafa"),
    "security": ("rect", "#c62828", "#fdecec"),
}
KIND_PATTERNS = (  # order matters: storage before database
    ("storage", r"cloud[-_ ]storage|\bs3\b|simple[-_ ]storage|filestore|\befs\b|object storage|bucket|\bblob\b|archive|hyperdisk|persistent[-_ ]disk"),
    ("database", r"spanner|\bsql\b|cloudsql|bigtable|bigquery|firestore|datastore|dynamodb|\brds\b|aurora|redshift|alloydb|memorystore|elasticache|documentdb|neptune|timestream|database|\bdb\b|warehouse|redis|postgres|mysql|mongo|cassandra|\bstore\b"),
    ("messaging", r"pubsub|pub/sub|\bsqs\b|simple[-_ ]queue|\bsns\b|simple[-_ ]notification|eventbridge|kinesis|kafka|\bmsk\b|\bqueue\b|\btopic\b|event bus|eventarc|cloud[-_ ]tasks|\bmq\b"),
    ("ml", r"vertex|sagemaker|bedrock|automl|ai[-_ ]platform|\bml\b|\bmodel\b"),
    ("security", r"\biam\b|\bkms\b|key[-_ ]management|secret|armor|\bwaf\b|cognito|shield|identity"),
)
FRAME_STYLES = {  # deployment boundary nodes
    "cloud": ("#5f6368", "#f8f9fa"),
    "organization": ("#5f6368", "#f8f9fa"),
    "account": ("#5f6368", "#f8f9fa"),
    "folder": ("#80868b", "#f8f9fa"),
    "project": ("#4285f4", "#f3f7fe"),
    "region": ("#80868b", "#fafafa"),
    "vpc": ("#2e7d32", "#f2faf3"),
    "availability-zone": ("#9aa0a6", "#ffffff"),
    "zone": ("#9aa0a6", "#ffffff"),
    "subnet": ("#1a73e8", "#eef4fe"),
    "cluster": ("#e37400", "#fff8ee"),
}


def element_visual(element: dict | None) -> Visual | None:
    """Role-specific look for cloud-annotated elements; None keeps the C4 default."""
    import re

    if not element or not element.get("cloud") or element.get("type") == "code":
        return None
    text = (
        " ".join(str(element.get(k, "")) for k in ("name", "technology"))
        + " "
        + str(element["cloud"].get("service", ""))
    ).lower()
    for kind, pattern in KIND_PATTERNS:
        if re.search(pattern, text):
            shape, stroke, fill = KIND_STYLES[kind]
            return Visual(kind, shape, stroke, fill)
    return None


def box_style(box) -> tuple[str, str, str]:
    """(shape, stroke, fill) for a scene box, shared by every exporter."""
    element = box.element or {}
    visual = element_visual(element)
    if visual:
        return visual.shape, visual.stroke, visual.fill
    if box.role == "frame" and element.get("type") in FRAME_STYLES:
        stroke, fill = FRAME_STYLES[element["type"]]
        return "rect", stroke, fill
    stroke, fill = ELEMENT_STYLES.get(element.get("type"), ("#879bb1", "#f7fafc"))
    return "rect", stroke, fill


@lru_cache(maxsize=16)
def _font(size: int):
    # Pin the basic engine: Pillow picks Raqm when libraqm/fribidi is present (common on
    # Linux), which measures differently and would make wrapping depend on the host.
    return ImageFont.truetype(
        str(ASSETS / "font.ttf"), size, layout_engine=ImageFont.Layout.BASIC
    )


def text_width(text: str, font_px: int = 13, *, bold: bool = False) -> int:
    # The font file is regular; SVG and Draw.io also use regular for measured content.
    measured = _font(font_px).getlength(text)
    if any(ord(c) > 0x052F for c in text):
        # Roboto covers Latin/Greek/Cyrillic. Bound fallback-script glyphs conservatively
        # so local CJK/Arabic/emoji font substitution cannot overflow a measured card.
        fallback_bound = sum(
            max(
                _font(font_px).getlength(c),
                font_px * (2 if unicodedata.east_asian_width(c) in {"W", "F"} else 1.3),
            )
            if ord(c) > 0x052F
            else _font(font_px).getlength(c)
            for c in text
        )
        measured = max(measured, fallback_bound)
    return math.ceil(measured + 1)


def line_height(font_px: int) -> int:
    return int(font_px * 1.5)


_BREAK_AFTER = " /-_.,;:"


def _tokens(paragraph: str) -> list[str]:
    """Split into words; keep each break character attached to the token it ends."""
    tokens, current = [], ""
    for char in paragraph:
        current += char
        if char in _BREAK_AFTER:
            tokens.append(current)
            current = ""
    if current:
        tokens.append(current)
    return tokens


def wrap_to_width(text: str, width: int, font_px: int = 13) -> list[str]:
    """Word-aware wrapping; a single token wider than the line is split by character."""
    if width < font_px * 2:
        raise ValueError("Label width is too small")
    lines = []
    for paragraph in safe_text(text).splitlines() or [""]:
        current = ""
        for token in _tokens(paragraph):
            if not current or text_width((current + token).rstrip(), font_px) <= width:
                current += token
                if text_width(current.rstrip(), font_px) <= width:
                    continue
            else:
                lines.append(current.rstrip())
                current = token.lstrip()
                if text_width(current.rstrip(), font_px) <= width:
                    continue
            # Oversized single token: fall back to character breaks.
            pending, current = current, ""
            for char in pending:
                if current and text_width(current + char, font_px) > width:
                    lines.append(current.rstrip())
                    current = char.lstrip()
                else:
                    current += char
        lines.append(current.rstrip())
    return lines


@dataclass(frozen=True)
class TextLine:
    text: str
    font: int = 13
    bold: bool = False
    color: str = INK

    @property
    def height(self) -> int:
        return line_height(self.font)

    @property
    def width(self) -> int:
        return text_width(self.text, self.font, bold=self.bold)


@dataclass
class Label:
    lines: list[TextLine] = field(default_factory=list)
    icon: str | None = None
    icon_size: int = 40
    top_pad: int = 0

    @property
    def width(self) -> int:
        return max((ln.width for ln in self.lines), default=0)

    @property
    def height(self) -> int:
        return (
            sum(ln.height for ln in self.lines)
            + (self.icon_size + 8 if self.icon else 0)
            + self.top_pad
        )

    def plain(self) -> str:
        return "\n".join(ln.text for ln in self.lines)


CLAIM_CUES = {"inferred": "«inferred»", "proposed": "«proposed»", "unknown": "«unknown»"}


def claim_cue(status: str | None) -> str:
    """Text cue for a claim that is not observed; empty when observed or not stated."""
    return CLAIM_CUES.get(status, "")


def element_label(
    element: dict, *, compact: bool = False, code_icons: bool = False
) -> Label:
    cue = claim_cue(element.get("status"))
    lines = [
        TextLine(t, size)
        for text, size in (
            (element["name"], 15),
            (f"«{element.get('kind', element['type'])}»" + (" " + cue if cue else ""), 12),
            (element.get("technology", ""), 12),
            (element.get("description", ""), 13),
        )
        if text
        for t in wrap_to_width(text, 240, size)
    ]
    if not compact:
        lines.extend(
            TextLine(t, 12)
            for member in element.get("members", [])
            for t in wrap_to_width(member, 240, 12)
        )
    service = (
        element.get("cloud", {}).get("service")
        if element.get("type") != "code" or code_icons
        else None
    )
    # Optional GCP icons may not be installed, and a forced icon style may lack artwork
    # ("icon": false); the element then renders without one but keeps its service.
    show = element.get("cloud", {}).get("icon", True)
    icon = service if show and icon_available(service) else None
    visual = element_visual(element)
    pad = CAP_PAD if visual and visual.shape == "cylinder" else 0
    return Label(lines, icon=icon, top_pad=pad)
