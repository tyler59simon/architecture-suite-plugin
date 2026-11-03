"""Generate one sample folder per skill under examples/suite/<skill>/ using the installed CLI.

Inputs (checked in): examples/suite/living-memory/plan.md (curated from ARCHITECTURE.md),
examples/generated/order-platform/architecture-plan.md (fictional, has AWS deployment).
Run: python tools/generate_sample_suite.py   (needs `architecture-suite` on PATH or in .venv)
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "examples"
CLI = Path(sys.executable).with_name("architecture-suite.exe" if sys.platform == "win32" else "architecture-suite")
LM = SAMPLES / "suite/living-memory/plan.md"
ORDER = SAMPLES / "generated/order-platform/architecture-plan.md"
OUT = SAMPLES / "suite"

# skill -> (plan, extra arguments)
JOBS = {
    "c4-diagrams": (LM, ["--level", "all", "--overview-style", "progressive", "--augmented"]),
    "c4-system": (LM, ["--level", "system", "--augmented"]),
    "c4-container": (LM, ["--level", "container", "--augmented"]),
    "c4-component": (LM, ["--level", "component", "--augmented"]),
    "c4-code": (LM, ["--level", "code", "--augmented"]),
    "c4-overview": (LM, ["--level", "overview", "--overview-style", "all", "--augmented"]),
    "c4-aws": (ORDER, ["--level", "all", "--overview-style", "executive"]),
}


def main():
    for skill, (plan, extra) in JOBS.items():
        target = OUT / skill
        if target.exists():
            shutil.rmtree(target)
        lint = subprocess.run([CLI, "plan-lint", "--plan", plan, "--strict"], capture_output=True, text=True)
        if lint.returncode:
            raise SystemExit(f"{skill}: plan-lint failed\n{lint.stdout}{lint.stderr}")
        run = subprocess.run(
            [CLI, "plan-render", "--plan", plan, "--output", target,
             "--format", "mermaid,drawio,png,svg", "--confirm-write", *extra],
            capture_output=True, text=True,
        )
        if run.returncode:
            raise SystemExit(f"{skill}: render failed\n{run.stdout}{run.stderr}")
        count = sum(1 for p in target.rglob("*") if p.is_file())
        print(f"{skill}: {count} files -> {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
