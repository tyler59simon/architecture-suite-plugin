"""Record exact development and runtime dependencies.

    python tools/lock_python.py            # needs network: fetches release hashes from PyPI

Writes `requirements-lock.txt` (development, pins only, from the active environment) and
`skills/architecture-suite-runtime/scripts/requirements-runtime.lock` (runtime closure of the
skill's pyproject dependencies, with every published SHA-256 per release so
`pip install --require-hashes` works on every supported platform).

Dependency markers are evaluated for every supported Python on Windows, Linux and macOS, so
platform-specific dependencies are not silently dropped. A dependency that is needed somewhere
but not installed locally stops the lock: install it and rerun.
"""

from importlib.metadata import PackageNotFoundError, distribution, distributions
import json
from pathlib import Path
import sys
import tomllib
import urllib.request

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "skills/architecture-suite-runtime/scripts"
SUPPORTED_PYTHONS = ("3.11", "3.12", "3.13", "3.14")
PLATFORMS = (
    {"sys_platform": "win32", "platform_system": "Windows", "os_name": "nt"},
    {"sys_platform": "linux", "platform_system": "Linux", "os_name": "posix"},
    {"sys_platform": "darwin", "platform_system": "Darwin", "os_name": "posix"},
)
ENVIRONMENTS = [
    {**platform, "python_version": version, "python_full_version": version + ".0", "extra": ""}
    for version in SUPPORTED_PYTHONS
    for platform in PLATFORMS
]


def runtime_requirements():
    project = tomllib.loads((RUNTIME / "pyproject.toml").read_text(encoding="utf-8"))
    return [Requirement(spec) for spec in project["project"]["dependencies"]]


def needed(requirement):
    return requirement.marker is None or any(
        requirement.marker.evaluate(env) for env in ENVIRONMENTS
    )


def runtime_closure():
    seen = {}

    def visit(requirement):
        try:
            package = distribution(requirement.name)
        except PackageNotFoundError:
            raise SystemExit(
                f"{requirement.name} is needed on some supported platform but is not "
                "installed here; install it into this environment and rerun."
            )
        key = package.metadata["Name"]
        if key in seen:
            return
        seen[key] = package.version
        for spec in package.requires or []:
            child = Requirement(spec)
            if needed(child):
                visit(child)

    for requirement in runtime_requirements():
        visit(requirement)
    return dict(sorted(seen.items(), key=lambda item: item[0].lower()))


def release_hashes(name, version):
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urllib.request.urlopen(url, timeout=30) as response:
        files = json.load(response)["urls"]
    digests = sorted({f["digests"]["sha256"] for f in files})
    if not digests:
        raise SystemExit(f"PyPI lists no files for {name}=={version}")
    return digests


def main():
    excluded = {"pip", "setuptools", "architecture-suite"}
    lock = sorted(
        (
            f"{d.metadata['Name']}=={d.version}"
            for d in distributions()
            if d.metadata["Name"].lower() not in excluded
        ),
        key=str.lower,
    )
    (ROOT / "requirements-lock.txt").write_text(
        "\n".join(lock) + "\n", encoding="utf-8", newline="\n"
    )
    lines = []
    for name, version in runtime_closure().items():
        hashes = release_hashes(name, version)
        lines.append(
            f"{name}=={version} \\\n"
            + " \\\n".join(f"    --hash=sha256:{digest}" for digest in hashes)
        )
    (RUNTIME / "requirements-runtime.lock").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"runtime lock: {len(lines)} packages", file=sys.stderr)


if __name__ == "__main__":
    main()
