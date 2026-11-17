"""Generate the fictional RidePulse ride-dispatch example on Google Cloud.

    python tools/generate_gcp_samples.py   (needs `architecture-suite` next to this Python)

Writes examples/ride-dispatch/:
  plans/architecture-plan.md         checked-in, editable input
  diagrams/                          C4 levels 1-4, overviews, Google Cloud deployment,
                                     a ride-request sequence (c4-dynamic.mmd)
  diagrams/large-overviews/          small-multiples and complete (SVG/Draw.io only)
  icon-styles/modern/                containers and deployment in the modern icon style
  icon-styles/legacy/                deployment only
                                     (both minus files identical to diagrams/)
  from-source-code/ridepulse-repo/   fictional source repository (checked in)
  from-source-code/plan-draft.md     plan-draft output for that repository
  from-source-code/analysis/         analyze output for that repository
Every fact here is fictional.
"""

import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/architecture-suite-runtime/scripts"))
from architecture_suite.plan import render_plan  # noqa: E402
from examples_gcp import DYNAMIC_SEQUENCE, ridepulse_plan  # noqa: E402
from sample_dedupe import drop_identical  # noqa: E402

OUT = ROOT / "examples/ride-dispatch"
# Console scripts live in the interpreter's scripts folder (Scripts\ on Windows, bin/ elsewhere),
# which is not always the folder holding the interpreter itself.
CLI = Path(sysconfig.get_path("scripts")) / (
    "architecture-suite.exe" if sys.platform == "win32" else "architecture-suite"
)
PLAN = OUT / "plans/architecture-plan.md"
FORMATS = "mermaid,drawio,png,svg"
VECTOR = "mermaid,drawio,svg"

README = """# RidePulse: ride dispatch on Google Cloud (fictional)

A real-time ride dispatch and fleet telemetry platform on Google Cloud.

| What | Where |
| --- | --- |
| Editable plan | [plans/architecture-plan.md](plans/architecture-plan.md) |
| L1 system context | [diagrams/01-system-context](diagrams/01-system-context) |
| L2 containers | [diagrams/02-containers](diagrams/02-containers) |
| L3 components | [diagrams/03-components](diagrams/03-components) |
| L4 code | [diagrams/04-code](diagrams/04-code) |
| Overviews (executive, progressive, hierarchy) | [diagrams/05-overview](diagrams/05-overview) |
| Google Cloud deployment | [diagrams/06-gcp-deployment](diagrams/06-gcp-deployment) |
| Ride request sequence | [diagrams/c4-dynamic.mmd](diagrams/c4-dynamic.mmd) |
| Small-multiples and complete overviews (SVG/Draw.io) | [diagrams/large-overviews](diagrams/large-overviews) |
| Modern vs legacy Google Cloud icons | [icon-styles/modern](icon-styles/modern) (containers and deployment), [icon-styles/legacy](icon-styles/legacy) (deployment only); a file identical to its `diagrams/` twin is not repeated |
| Reverse-engineered from source code | [from-source-code](from-source-code) |

`from-source-code/` shows the `reverse-engineer-c4` workflow: a small fictional repository
(`ridepulse-repo/`), the editable draft `plan-draft` produced from it, and the diagrams `analyze`
renders directly. Compare the draft with the curated plan to see what a reviewer adds.

Regenerate with `python tools/generate_gcp_samples.py`. Every fact here is fictional.
"""


def run(*args, label):
    result = subprocess.run([str(CLI), *map(str, args)], capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(f"{label} failed\n{result.stdout}{result.stderr}")
    return result


def render(target, *extra, formats=FORMATS, label):
    if target.exists():
        shutil.rmtree(target)
    run("plan-render", "--plan", PLAN, "--output", target, "--format", formats,
        "--confirm-write", *extra, label=label)


def main():
    PLAN.parent.mkdir(parents=True, exist_ok=True)
    PLAN.write_bytes(render_plan(ridepulse_plan()).encode("utf-8"))
    run("plan-lint", "--plan", PLAN, "--strict", label="plan-lint")

    diagrams = OUT / "diagrams"
    render(diagrams, "--level", "all", "--overview-style", "executive,progressive,hierarchy",
           label="diagrams")
    (diagrams / "c4-dynamic.mmd").write_bytes(DYNAMIC_SEQUENCE.encode("utf-8"))
    # These styles exceed browser PNG limits for a system this size: vector formats only.
    render(diagrams / "large-overviews", "--level", "overview",
           "--overview-style", "small-multiples,complete", formats=VECTOR, label="large overviews")

    for style in ("modern", "legacy"):
        target = OUT / "icon-styles" / style
        # Forced styles intentionally omit some icons; lint advisories are expected.
        render(target, "--level", "all", "--overview-style", "executive",
               "--gcp-icon-style", style, label=f"{style} icons")
        # Icons only differ on containers and the deployment. Modern keeps both views; legacy keeps
        # the deployment. Files that match the default render are dropped in both.
        keep = {"02-containers", "06-gcp-deployment"} if style == "modern" else {"06-gcp-deployment"}
        for child in target.iterdir():
            if child.is_dir() and child.name not in keep:
                shutil.rmtree(child)
        drop_identical(diagrams, target)

    source = OUT / "from-source-code"
    repo = source / "ridepulse-repo"
    for stale in (source / "analysis", source / "plan-draft.md"):
        if stale.is_dir():
            shutil.rmtree(stale)
        elif stale.exists():
            stale.unlink()
    run("plan-draft", "--repo", repo, "--cloud-profile", "gcp",
        "--output", source / "plan-draft.md", "--confirm-write", label="plan-draft")
    run("analyze", "--repo", repo, "--cloud-profile", "gcp", "--output", source / "analysis",
        "--format", FORMATS, "--level", "all", "--confirm-write", label="analyze")

    (OUT / "README.md").write_bytes(README.encode("utf-8"))
    print(f"ride-dispatch: {sum(1 for p in OUT.rglob('*') if p.is_file())} files")


if __name__ == "__main__":
    main()
