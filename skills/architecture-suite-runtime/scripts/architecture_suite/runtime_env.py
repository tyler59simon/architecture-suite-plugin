"""Runtime environment stamp shared by bootstrap.py and `doctor`.

Standard library only: bootstrap.py imports this before any dependency is installed.

The bootstrap venv provides dependencies only; code always runs from the installed skill
through scripts/architecture-suite.py. The stamp records which dependency lock the venv was
built from, so `doctor` can tell when a plugin update changed the lock and bootstrap must be
re-run.
"""

import hashlib
import json
from pathlib import Path
import sys

SUPPORTED_PYTHON = ((3, 11), (3, 14))  # inclusive
LOCK = Path(__file__).resolve().parents[1] / "requirements-runtime.lock"
STAMP_NAME = "architecture-suite-runtime.json"


def python_supported(version_info=None):
    """True when the interpreter is inside the supported range."""
    version = tuple((version_info or sys.version_info)[:2])
    return SUPPORTED_PYTHON[0] <= version <= SUPPORTED_PYTHON[1]


def supported_range():
    (low_major, low_minor), (high_major, high_minor) = SUPPORTED_PYTHON
    return f"{low_major}.{low_minor}-{high_major}.{high_minor}"


def lock_digest(lock=LOCK):
    """SHA-256 of the lock with line endings normalized, so checkouts on any OS agree."""
    data = Path(lock).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def write_stamp(prefix, lock=LOCK):
    """Record the lock a runtime venv was built from."""
    stamp = {
        "lock_sha256": lock_digest(lock),
        "python": ".".join(map(str, sys.version_info[:3])),
    }
    path = Path(prefix) / STAMP_NAME
    path.write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")
    return path


def check_stamp(prefix=None, lock=LOCK):
    """Return 'ok', 'unmanaged' (no stamp: a developer or CI environment) or a mismatch message."""
    path = Path(prefix or sys.prefix) / STAMP_NAME
    if not path.is_file():
        return "unmanaged"
    try:
        recorded = json.loads(path.read_text(encoding="utf-8")).get("lock_sha256")
    except (OSError, ValueError):
        recorded = None
    if recorded == lock_digest(lock):
        return "ok"
    return (
        "dependencies changed since bootstrap; re-run "
        "python <skills-dir>/architecture-suite-runtime/scripts/bootstrap.py"
    )
