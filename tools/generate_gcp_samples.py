"""Generate the fictional RidePulse (Google Cloud) samples for all nine skills.

Writes examples/gcp-suite/:
  ridepulse/architecture-plan.md        checked-in input for the eight plan-driven skills
  reverse-engineer-c4/ridepulse-repo/   fictional source fixture (checked in)
  <skill>/                              one rendered folder per skill
  c4-gcp/icon-style-{modern,legacy}/    same deployment in forced icon styles
Run: python tools/generate_gcp_samples.py   (needs `architecture-suite` next to this Python)
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/architecture-suite-runtime/scripts"))
from architecture_suite.draft import render_plan  # noqa: E402
from architecture_suite.examples_gcp import DYNAMIC_SEQUENCE, ridepulse_plan  # noqa: E402

SAMPLES = ROOT / "examples/gcp-suite"
CLI = Path(sys.executable).with_name(
    "architecture-suite.exe" if sys.platform == "win32" else "architecture-suite"
)
PLAN = SAMPLES / "ridepulse/architecture-plan.md"
FORMATS = "mermaid,drawio,png,svg"

JOBS = {
    "c4-diagrams": ["--level", "all", "--overview-style", "progressive"],
    "c4-system": ["--level", "system"],
    "c4-container": ["--level", "container"],
    "c4-component": ["--level", "component"],
    "c4-code": ["--level", "code"],
    "c4-overview": [
        "--level", "overview",
        "--overview-style", "executive,progressive,hierarchy",
    ],
    # These styles exceed browser PNG limits for a system this size: vector formats only.
    "c4-overview/vector-only": [
        "--level", "overview", "--overview-style", "small-multiples,complete",
    ],
    "c4-gcp": ["--level", "all", "--overview-style", "executive"],
    "c4-gcp/icon-style-modern": [
        "--level", "all", "--overview-style", "executive", "--gcp-icon-style", "modern",
    ],
    "c4-gcp/icon-style-legacy": [
        "--level", "all", "--overview-style", "executive", "--gcp-icon-style", "legacy",
    ],
}


def run(*args, label):
    result = subprocess.run([CLI, *map(str, args)], capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(f"{label} failed\n{result.stdout}{result.stderr}")
    return result


def main():
    PLAN.parent.mkdir(parents=True, exist_ok=True)
    PLAN.write_text(render_plan(ridepulse_plan()), encoding="utf-8")
    run("plan-lint", "--plan", PLAN, "--strict", label="plan-lint")
    for skill, extra in JOBS.items():
        target = SAMPLES / skill
        if target.exists():
            shutil.rmtree(target)
        # Forced styles intentionally omit some icons; advisories are expected.
        strict = ["--strict"] if "icon-style" not in skill else []
        run("plan-lint", "--plan", PLAN, *strict, label=f"{skill} plan-lint")
        run(
            "plan-render", "--plan", PLAN, "--output", target,
            "--format", "mermaid,drawio,svg" if skill.endswith("/vector-only") else FORMATS,
            "--confirm-write", *extra,
            label=f"{skill} render",
        )
        if skill == "c4-diagrams":
            (target / "c4-dynamic.mmd").write_text(DYNAMIC_SEQUENCE, encoding="utf-8")
        print(f"{skill}: {sum(1 for p in target.rglob('*') if p.is_file())} files")

    # reverse-engineer-c4: static analysis of the fictional repository.
    reverse = SAMPLES / "reverse-engineer-c4"
    repo = reverse / "ridepulse-repo"
    for stale in (reverse / "analysis", reverse / "plan-draft.md"):
        if stale.is_dir():
            shutil.rmtree(stale)
        elif stale.exists():
            stale.unlink()
    run(
        "plan-draft", "--repo", repo, "--cloud-profile", "gcp",
        "--output", reverse / "plan-draft.md", "--confirm-write",
        label="plan-draft",
    )
    run(
        "analyze", "--repo", repo, "--cloud-profile", "gcp",
        "--output", reverse / "analysis", "--format", FORMATS,
        "--level", "all", "--confirm-write", label="analyze",
    )
    print("reverse-engineer-c4: analysis written")


if __name__ == "__main__":
    main()
