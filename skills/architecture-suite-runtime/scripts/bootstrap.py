"""One-time runtime setup for the Architecture Suite skills. Needs network access.

    python bootstrap.py [--target DIR] [--no-browser]

Creates a virtual environment (default ~/.architecture-suite/runtime) holding only the pinned,
hash-verified dependencies from requirements-runtime.lock, installs the pinned Chromium for PNG
rendering, then runs `doctor`. Skill code is never installed into the venv: the skills always
run their own copy through scripts/architecture-suite.py, so plugin updates take effect
immediately. Re-run this script when `doctor` reports that dependencies changed.

If the interpreter running this script is outside the supported range, a supported one is
located (Windows `py` launcher, or python3.X on PATH) and used instead.
"""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from architecture_suite.runtime_env import (  # noqa: E402  (standard library only)
    LOCK,
    SUPPORTED_PYTHON,
    python_supported,
    supported_range,
    write_stamp,
)

DEFAULT_TARGET = Path.home() / ".architecture-suite" / "runtime"
REEXEC_GUARD = "ARCHITECTURE_SUITE_BOOTSTRAP_REEXEC"


class BootstrapError(Exception):
    """A failed step with a one-line explanation and a next step for the user."""


def candidate_minors():
    (_, low), (_, high) = SUPPORTED_PYTHON
    return range(high, low - 1, -1)  # newest first


def find_supported_python():
    """Return the path of a supported interpreter, or None."""
    if python_supported():
        return sys.executable
    for minor in candidate_minors():
        if sys.platform == "win32" and shutil.which("py"):
            probe = ["py", f"-3.{minor}", "-c", "import sys; print(sys.executable)"]
            result = subprocess.run(probe, capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        found = shutil.which(f"python3.{minor}")
        if found:
            return found
    return None


def venv_python(target):
    return Path(target) / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def run(step, command):
    try:
        subprocess.run([str(part) for part in command], check=True)
    except subprocess.CalledProcessError as exc:
        raise BootstrapError(f"{step} failed (exit {exc.returncode}); see the output above.")
    except OSError as exc:
        raise BootstrapError(f"{step} could not start: {exc}")


def existing_minor(target):
    """Python minor version of an existing venv at target, or None."""
    config = Path(target) / "pyvenv.cfg"
    if not config.is_file():
        return None
    for line in config.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        if key.strip() in {"version", "version_info"}:
            return ".".join(value.strip().split(".")[:2])
    return None


def bootstrap(target, browser=True):
    target = Path(target).expanduser().resolve()
    current = f"{sys.version_info[0]}.{sys.version_info[1]}"
    stale = target.exists() and existing_minor(target) not in {None, current}
    print(f"Architecture Suite runtime: {target} (Python {current})")
    try:
        venv.EnvBuilder(with_pip=True, clear=stale).create(target)
    except OSError as exc:
        raise BootstrapError(f"Creating the virtual environment failed: {exc}")
    python = venv_python(target)
    run(
        "Installing pinned dependencies",
        [python, "-m", "pip", "install", "--disable-pip-version-check",
         "--require-hashes", "--only-binary=:all:", "-r", LOCK],
    )
    if browser:
        run("Installing Chromium", [python, "-m", "playwright", "install", "chromium"])
    write_stamp(target)
    doctor = subprocess.run([str(python), str(SCRIPTS / "architecture-suite.py"), "doctor"])
    if doctor.returncode and browser:
        raise BootstrapError("doctor reported a problem; see the JSON above.")
    print(
        "\nReady. Run the CLI with:\n  "
        f"{python} {SCRIPTS / 'architecture-suite.py'} <command>"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument(
        "--no-browser", action="store_true",
        help="skip Chromium (PNG export and browser layout unavailable)",
    )
    args = parser.parse_args(argv)
    if not python_supported():
        python = None if os.environ.get(REEXEC_GUARD) else find_supported_python()
        if python is None:
            print(
                f"Architecture Suite needs Python {supported_range()}; this is "
                f"{sys.version.split()[0]} and no supported interpreter was found. "
                "Install one (for example `winget install Python.Python.3.13`, "
                "`brew install python@3.13` or your distribution's python3.13) and rerun.",
                file=sys.stderr,
            )
            return 2
        print(f"Python {sys.version.split()[0]} is unsupported; using {python}")
        env = {**os.environ, REEXEC_GUARD: "1"}
        return subprocess.run([python, str(Path(__file__).resolve()), *(argv or sys.argv[1:])], env=env).returncode
    try:
        bootstrap(args.target, browser=not args.no_browser)
    except BootstrapError as exc:
        print(f"Bootstrap failed: {exc}", file=sys.stderr)
        print(
            "Check network access (pip must reach pypi.org; Playwright downloads Chromium), "
            "then rerun this script.",
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
