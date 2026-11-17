"""Developer tools: drift checks, version bump and the local check runner."""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from architecture_suite import __version__

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generate_skills_check(monkeypatch, capsys):
    tool = load("generate_skills")
    assert tool.main(["--check"]) == 0
    monkeypatch.setattr(tool, "RUNTIME", tool.RUNTIME + "\nExtra line.\n")
    assert tool.main(["--check"]) == 1
    assert "differs: skills/c4-system/SKILL.md" in capsys.readouterr().err
    assert "Extra line" not in (ROOT / "skills/c4-system/SKILL.md").read_text(encoding="utf-8")


def test_sync_manifests_check(tmp_path, capsys):
    tool = load("sync_manifests")
    assert tool.main(["--check"]) == 0
    assert tool.main(["--check"], root=tmp_path) == 1
    assert capsys.readouterr().err.count("differs:") == 3
    assert tool.main([], root=tmp_path) == 0
    assert tool.main(["--check"], root=tmp_path) == 0
    target = tmp_path / ".factory-plugin/plugin.json"
    target.write_text(target.read_text(encoding="utf-8").replace(__version__, "0.0.1"))
    assert tool.main(["--check"], root=tmp_path) == 1
    assert "differs: .factory-plugin/plugin.json" in capsys.readouterr().err


def test_build_manifest_check(tmp_path, capsys):
    tool = load("build_manifest")
    assert tool.main(["--check"]) == 0
    (tmp_path / "a.txt").write_text("one")
    assert tool.main(["--check"], assets=tmp_path) == 1
    assert tool.main([], assets=tmp_path) == 0
    assert tool.main(["--check"], assets=tmp_path) == 0
    (tmp_path / "a.txt").write_text("two")
    assert tool.main(["--check"], assets=tmp_path) == 1
    assert "differs:" in capsys.readouterr().err


def test_bump_version_rewrites_every_location(tmp_path, capsys):
    tool = load("bump_version")
    for relative, _, _ in tool.LOCATIONS:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    changed = tool.bump("9.8.7", root=tmp_path)
    assert sorted(changed) == sorted(relative for relative, _, _ in tool.LOCATIONS)
    assert tool.current_version(tmp_path) == "9.8.7"
    assert json.loads((tmp_path / "package.json").read_text())["version"] == "9.8.7"
    lock = json.loads((tmp_path / "package-lock.json").read_text())
    assert lock["version"] == lock["packages"][""]["version"] == "9.8.7"
    assert "#architecture-suite-9.8.7" in (tmp_path / "README.md").read_text(encoding="utf-8")
    assert f'"{__version__}"' not in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")


def test_bump_version_writes_nothing_when_a_later_location_mismatches(tmp_path):
    tool = load("bump_version")
    for relative, _, _ in tool.LOCATIONS:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    readme = tmp_path / "README.md"  # the last location: already edited by hand
    readme.write_text(readme.read_text(encoding="utf-8").replace(__version__, "0.0.1"), encoding="utf-8")
    before = {relative: (tmp_path / relative).read_bytes() for relative, _, _ in tool.LOCATIONS}
    with pytest.raises(SystemExit, match="README.md"):
        tool.bump("9.8.7", root=tmp_path)
    assert {r: (tmp_path / r).read_bytes() for r in before} == before


def test_bump_version_dry_run_and_format(capsys):
    tool = load("bump_version")
    before = (ROOT / "package.json").read_bytes()
    assert tool.main(["9.8.7", "--dry-run"]) == 0
    assert capsys.readouterr().out.count("would change") == len(tool.LOCATIONS)
    assert (ROOT / "package.json").read_bytes() == before
    for bad in ("1.2", "v1.2.3", "1.2.x"):
        with pytest.raises(SystemExit):
            tool.main([bad, "--dry-run"])


def test_check_runs_fast_or_full_steps():
    tool = load("check")
    fast = [" ".join(step[1:]) for step in tool.steps(False)]
    full = [" ".join(step[1:]) for step in tool.steps(True)]
    assert fast[0] == full[0] == "-m ruff check ."
    assert sum("--check" in step for step in fast) == 3
    assert fast[-1] == '-m pytest -m not slow -n auto'
    assert "--cov=architecture_suite" in full[-2]
    assert full[-1] == "tools/record_validation.py"
