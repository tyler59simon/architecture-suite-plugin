"""Path-based entry point: always runs this skill's own code, with dependencies from the
interpreter's environment (normally the venv created by bootstrap.py)."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from architecture_suite.runtime_env import python_supported, supported_range  # noqa: E402

BOOTSTRAP = Path(__file__).resolve().parent / "bootstrap.py"

if not python_supported():
    print(
        f"Architecture Suite needs Python {supported_range()}, not {sys.version.split()[0]}. "
        f"Run `python {BOOTSTRAP}` once, then use the runtime's own Python "
        "(~/.architecture-suite/runtime/Scripts/python.exe on Windows, bin/python elsewhere).",
        file=sys.stderr,
    )
    raise SystemExit(3)
try:
    from architecture_suite.cli import main
except ModuleNotFoundError as exc:
    print(
        f"Architecture Suite dependency missing: {exc.name}. Run `python {BOOTSTRAP}` once "
        "(needs network), then use the runtime's own Python "
        "(~/.architecture-suite/runtime/Scripts/python.exe on Windows, bin/python elsewhere).",
        file=sys.stderr,
    )
    raise SystemExit(3)

raise SystemExit(main())
