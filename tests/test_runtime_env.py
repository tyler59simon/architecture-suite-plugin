"""Runtime stamp, doctor's dependency gate, the launcher and bootstrap helpers."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from architecture_suite import cli, runtime_env
from architecture_suite.cli import main

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/architecture-suite-runtime/scripts"


def load_bootstrap():
    spec = importlib.util.spec_from_file_location("bootstrap", SCRIPTS / "bootstrap.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_supported_python_range():
    assert runtime_env.python_supported((3, 11, 0))
    assert runtime_env.python_supported((3, 14, 2))
    assert not runtime_env.python_supported((3, 10, 9))
    assert not runtime_env.python_supported((3, 15, 0))
    assert runtime_env.python_supported() == (sys.version_info[:2] >= (3, 11))
    assert runtime_env.supported_range() == "3.11-3.14"


def test_lock_digest_ignores_line_endings(tmp_path):
    lf, crlf = tmp_path / "lf.lock", tmp_path / "crlf.lock"
    lf.write_bytes(b"a==1\nb==2\n")
    crlf.write_bytes(b"a==1\r\nb==2\r\n")
    assert runtime_env.lock_digest(lf) == runtime_env.lock_digest(crlf)
    assert runtime_env.lock_digest() == runtime_env.lock_digest(runtime_env.LOCK)


def test_stamp_states(tmp_path):
    lock = tmp_path / "requirements.lock"
    lock.write_text("a==1\n")
    assert runtime_env.check_stamp(tmp_path, lock) == "unmanaged"
    stamp = runtime_env.write_stamp(tmp_path, lock)
    assert json.loads(stamp.read_text())["python"].startswith(f"{sys.version_info[0]}.")
    assert runtime_env.check_stamp(tmp_path, lock) == "ok"
    lock.write_text("a==2\n")
    assert "re-run" in runtime_env.check_stamp(tmp_path, lock)
    stamp.write_text("not json")
    assert "re-run" in runtime_env.check_stamp(tmp_path, lock)


def test_doctor_fails_when_dependencies_changed(monkeypatch, capsys):
    monkeypatch.setattr(cli, "check_stamp", lambda: "dependencies changed since bootstrap; re-run")
    assert main(["doctor"]) == 3
    assert "re-run" in json.loads(capsys.readouterr().out)["runtime_deps"]
    monkeypatch.setattr(cli, "check_stamp", lambda: "ok")
    assert main(["doctor"]) == 0


def test_launcher_runs_this_skills_code():
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "architecture-suite.py"), "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0 and "doctor" in result.stdout


def test_bootstrap_helpers(tmp_path, monkeypatch, capsys):
    bootstrap = load_bootstrap()
    assert list(bootstrap.candidate_minors()) == [14, 13, 12, 11]
    assert bootstrap.find_supported_python() == sys.executable
    assert bootstrap.venv_python(tmp_path).parent.name in {"Scripts", "bin"}
    assert bootstrap.existing_minor(tmp_path) is None
    (tmp_path / "pyvenv.cfg").write_text("home = x\nversion = 3.13.17\n")
    assert bootstrap.existing_minor(tmp_path) == "3.13"
    with pytest.raises(bootstrap.BootstrapError, match="failed"):
        bootstrap.run("Step", [sys.executable, "-c", "raise SystemExit(4)"])
    with pytest.raises(bootstrap.BootstrapError, match="could not start"):
        bootstrap.run("Step", [str(tmp_path / "missing-executable")])

    monkeypatch.setattr(bootstrap, "python_supported", lambda: False)
    monkeypatch.setenv(bootstrap.REEXEC_GUARD, "1")
    assert bootstrap.main([]) == 2
    assert "needs Python 3.11-3.14" in capsys.readouterr().err


def test_bootstrap_reports_failures(tmp_path, monkeypatch, capsys):
    bootstrap = load_bootstrap()

    def broken(target, browser=True):
        raise bootstrap.BootstrapError("Installing pinned dependencies failed (exit 1)")

    monkeypatch.setattr(bootstrap, "bootstrap", broken)
    assert bootstrap.main(["--target", str(tmp_path)]) == 3
    assert "Bootstrap failed" in capsys.readouterr().err
