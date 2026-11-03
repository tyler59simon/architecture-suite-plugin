"""Generate the shipped examples through the runtime."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/architecture-suite-runtime/scripts"))
from architecture_suite.cli import main as cli  # noqa: E402
from architecture_suite.examples import example_model  # noqa: E402
from architecture_suite.renderers import diagram_specs, render_mermaid, render_svg  # noqa: E402


def main():
    samples = ROOT / "examples"
    status = cli(
        [
            "examples",
            "--output",
            str(samples / "generated"),
            "--overview-style",
            "all",
            "--confirm-write",
            "--confirm-overwrite",
        ]
    )
    if status:
        raise SystemExit(status)
    for index, name in enumerate(
        ("order-platform", "research-portal", "telemetry-platform")
    ):
        model = example_model(index)
        for base, view in diagram_specs(model, ["all"]):
            (samples / "generated" / name / (base + ".svg")).write_text(
                render_svg(model, view), encoding="utf-8"
            )
    model = example_model()
    for name, view in (
        ("c4-context", model["views"][0]),
        ("c4-container", model["views"][1]),
        ("c4-component", model["views"][2]),
        ("c4-code", next(v for v in model["views"] if v["type"] == "code")),
        (
            "c4-overview",
            {"id": "overview-progressive", "type": "overview", "style": "progressive"},
        ),
        ("aws-deployment", {"id": "aws-deployment", "type": "deployment"}),
    ):
        (samples / (name + ".mmd")).write_text(
            render_mermaid(model, view), encoding="utf-8"
        )
    (samples / "c4-dynamic.mmd").write_text(
        """%% Illustrative scenario; authored separately from schema 2.0 C4 views.
sequenceDiagram
  actor Customer
  participant API
  participant PaymentProvider as Payment Provider
  participant Queue as Order Queue
  Customer->>API: Submit request (HTTPS)
  API->>PaymentProvider: Authorize payment
  PaymentProvider-->>API: Authorization result
  API->>Queue: Queue accepted work
  API-->>Customer: Return confirmation
""",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
