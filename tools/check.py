"""Run the local checks in order and stop at the first failure.

    python tools/check.py          # ruff, drift checks, fast tests (pytest -m "not slow")
    python tools/check.py --full   # ruff, drift checks, full tests with coverage, validation gate
"""

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def steps(full):
    plan = [
        [PY, "-m", "ruff", "check", "."],
        [PY, "tools/generate_skills.py", "--check"],
        [PY, "tools/sync_manifests.py", "--check"],
        [PY, "tools/build_manifest.py", "--check"],
    ]
    if full:
        plan += [
            [
                PY, "-m", "pytest", "-n", "auto", "--cov=architecture_suite", "--cov-branch",
                "--cov-report=json:test-results/coverage.json",
                "--junitxml=test-results/junit.xml",
            ],
            [PY, "tools/record_validation.py"],
        ]
    else:
        plan.append([PY, "-m", "pytest", "-m", "not slow", "-n", "auto"])
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--full", action="store_true", help="full suite with coverage and gate")
    args = parser.parse_args(argv)
    for command in steps(args.full):
        print("+", " ".join(command[1:]), flush=True)
        code = subprocess.run(command, cwd=ROOT, check=False).returncode
        if code:
            print(f"failed with exit code {code}: {' '.join(command[1:])}", file=sys.stderr)
            return code
    return 0


if __name__ == "__main__":
    sys.exit(main())
