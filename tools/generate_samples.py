"""Generate the three small fictional AWS starter systems into examples/starter-systems/.

    python tools/generate_samples.py

Uses the runtime's `examples` command (C4 levels 1-4, all five overview styles and the AWS
deployment) and adds SVG for every view.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/architecture-suite-runtime/scripts"))
from architecture_suite.cli import main as cli  # noqa: E402
from architecture_suite.examples import example_model  # noqa: E402
from architecture_suite.renderers import diagram_specs, render_svg  # noqa: E402


def main():
    samples = ROOT / "examples"
    status = cli(
        [
            "examples",
            "--output",
            str(samples / "starter-systems"),
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
            (samples / "starter-systems" / name / (base + ".svg")).write_text(
                render_svg(model, view), encoding="utf-8"
            )


if __name__ == "__main__":
    main()
