"""Prove the hashed runtime lock installs from wheels on every supported Python and OS.

    python tools/check_wheels.py            # needs network; downloads nothing, writes nothing

For each supported Python x platform, runs a pip dry-run resolve with
`--only-binary=:all: --require-hashes`, so a missing wheel, a missing transitive pin
or a wrong hash fails here instead of in a user's bootstrap.
"""

from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "skills/architecture-suite-runtime/scripts/requirements-runtime.lock"
SUPPORTED_PYTHONS = ("3.11", "3.12", "3.13", "3.14")
PLATFORMS = {
    "windows-x64": ["win_amd64"],
    "linux-x64": ["manylinux_2_28_x86_64", "manylinux_2_17_x86_64", "manylinux2014_x86_64"],
    "linux-arm64": ["manylinux_2_28_aarch64", "manylinux_2_17_aarch64", "manylinux2014_aarch64"],
    "macos-arm64": ["macosx_14_0_arm64", "macosx_11_0_arm64"],
    "macos-x64": ["macosx_14_0_x86_64", "macosx_11_0_x86_64", "macosx_10_13_x86_64"],
}


def check(python_version, tags, target):
    platform_args = [arg for tag in tags for arg in ("--platform", tag)]
    result = subprocess.run(
        [
            sys.executable, "-m", "pip", "install", "--dry-run", "--quiet",
            "--ignore-installed", "--only-binary=:all:", "--require-hashes",
            "--python-version", python_version, *platform_args,
            "--target", target, "-r", str(LOCK),
        ],
        capture_output=True,
        text=True,
    )
    errors = [line for line in result.stderr.splitlines() if "ERROR" in line]
    return result.returncode == 0, errors[:2]


def main():
    failures = 0
    with tempfile.TemporaryDirectory() as target:
        for version in SUPPORTED_PYTHONS:
            for name, tags in PLATFORMS.items():
                ok, errors = check(version, tags, target)
                print(f"{version} {name}: {'ok' if ok else 'FAIL ' + ' | '.join(errors)}")
                failures += not ok
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
