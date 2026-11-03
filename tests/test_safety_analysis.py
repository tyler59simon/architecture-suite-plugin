from pathlib import Path
import json
import os
import subprocess
import sys
import pytest
from architecture_suite.safety import (
    SafetyError,
    atomic_output_directory,
    canonical_existing_directory,
    canonical_existing_file,
    canonical_output_directory,
    contained_path,
    redact,
    require_write_authorization,
    run_bounded,
    safe_text,
    scan_repository,
)
from architecture_suite.analyzer import analyze_repository
from architecture_suite.aws_analyzer import detect_aws
from architecture_suite.model import validate_model
from architecture_suite import aws


def test_paths_and_authorization(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    file = source / "file.py"
    file.write_text("pass")
    assert canonical_existing_directory(source) == source
    assert canonical_existing_file(file) == file
    assert canonical_output_directory(tmp_path / "new") == tmp_path / "new"
    assert (
        contained_path(source, "nested/artifact.svg") == source / "nested/artifact.svg"
    )
    for function, path in (
        (canonical_existing_directory, file),
        (canonical_existing_file, source),
        (canonical_existing_file, source / "missing"),
        (canonical_output_directory, file),
        (canonical_output_directory, Path.cwd()),
        (canonical_output_directory, Path.home()),
        (canonical_output_directory, Path(source.anchor)),
    ):
        with pytest.raises(SafetyError):
            function(path)
    for relative in ("../escape", str(tmp_path / "absolute"), "."):
        with pytest.raises(SafetyError):
            contained_path(source, relative)
    for write, overwrite in ((False, False), (False, True), (True, False)):
        with pytest.raises(SafetyError):
            require_write_authorization(source, write, overwrite)
    require_write_authorization(source, True, True)
    require_write_authorization(tmp_path / "missing", True, False)
    require_write_authorization(file, True, True)


def test_atomic_publication_and_rollback(tmp_path, monkeypatch):
    output = tmp_path / "published"
    output.mkdir()
    (output / "keep").write_text("original")
    with pytest.raises(RuntimeError):
        with atomic_output_directory(output) as stage:
            (stage / "keep").write_text("changed")
            raise RuntimeError("export failed")
    assert (output / "keep").read_text() == "original"
    with atomic_output_directory(output) as stage:
        (stage / "diagram.svg").write_text("<svg/>")
    assert (output / "keep").read_text() == "original"
    assert (output / "diagram.svg").is_file()
    original = Path.rename

    def fail_promotion(self, target):
        if self.name.startswith(".architecture-stage-") and not self.name.endswith(
            "-backup"
        ):
            raise OSError("simulated promotion failure")
        return original(self, target)

    monkeypatch.setattr(Path, "rename", fail_promotion)
    with pytest.raises(OSError):
        with atomic_output_directory(output) as stage:
            (stage / "keep").write_text("bad")
    assert (output / "keep").read_text() == "original"
    assert not list(tmp_path.glob(".architecture-stage-*"))


def test_symlink_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sensitive.py").write_text("private")
    root = tmp_path / "root"
    root.mkdir()
    link = root / "link"
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True
        )
        assert completed.returncode == 0
    else:
        link.symlink_to(outside, target_is_directory=True)
    try:
        with pytest.raises(SafetyError):
            canonical_existing_directory(link)
        with pytest.raises(SafetyError):
            contained_path(root, "link/artifact")
        with pytest.raises(SafetyError):
            canonical_output_directory(root)
        scan = scan_repository(root)
        assert not any("sensitive" in p for p in scan.texts)
    finally:
        link.rmdir() if os.name == "nt" else link.unlink()


def test_bounded_processes():
    assert run_bounded([sys.executable, "-c", "print('ok')"]).strip() == "ok"
    for command, options in (
        (
            [sys.executable, "-c", "import time;time.sleep(1)"],
            {"timeout_seconds": 0.01},
        ),
        (["no-such-executable-architecture-suite"], {}),
        ([sys.executable, "-c", "raise RuntimeError('password=abcdefghi')"], {}),
        ([sys.executable, "-c", "print('a'*1000)"], {"max_output_bytes": 10}),
        ([sys.executable, "-c", "pass"], {"timeout_seconds": 0}),
        ([sys.executable, "-c", "pass"], {"max_output_bytes": 0}),
    ):
        with pytest.raises(SafetyError):
            run_bounded(command, **options)


def test_scan_limits_encoding_secrets(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text(
        "api_key='sensitivevalue'\nkey='AKIA" + "A" * 16 + "'", encoding="utf-8"
    )
    (tmp_path / "b.py").write_bytes(b"\xff\xfe")
    (tmp_path / "c.py").write_text("x" * 200)
    (tmp_path / "skip.bin").write_bytes(b"\x00")
    (tmp_path / ".env").write_text("SECRET=realvalue")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules/secret.py").write_text("private")
    result = scan_repository(tmp_path, max_file_bytes=100)
    assert set(result.texts) == {"a.py"}
    assert len(result.skipped) == 2
    assert "sensitivevalue" not in result.texts["a.py"]
    assert "AKIA" not in result.texts["a.py"]
    assert safe_text("a\x00b") == "ab"
    assert "REDACTED" in redact("-----BEGIN RSA PRIVATE KEY-----")
    assert scan_repository(tmp_path, max_files=1).truncated
    assert scan_repository(tmp_path, max_total_bytes=1).truncated
    with pytest.raises(SafetyError):
        scan_repository(tmp_path, max_files=0)
    import architecture_suite.safety as safety

    ticks = iter([0, 100])
    monkeypatch.setattr(safety.time, "monotonic", lambda: next(ticks))
    assert scan_repository(tmp_path, timeout_seconds=1).truncated


@pytest.mark.parametrize(
    "manifest,source,code,stack",
    [
        (
            "app.csproj",
            "App.cs",
            "public class App { public string Handle(int x) { return x.ToString(); } }",
            ".NET",
        ),
        (
            "pom.xml",
            "App.java",
            "public class App { public String handle(int x) { return null; } }",
            "JVM",
        ),
        (
            "build.gradle.kts",
            "App.kt",
            "fun handle(x: Int): String { return x.toString() }",
            "JVM",
        ),
        (
            "go.mod",
            "app.go",
            'package main\nfunc Handle(x int) string { return "x" }',
            "Go",
        ),
        (
            "package.json",
            "app.ts",
            "export function handle(x: number) { return x; }",
            "Node",
        ),
        (
            "pyproject.toml",
            "app.py",
            "class App:\n    def handle(self, x: int) -> str:\n        return str(x)\n\ndef helper(x):\n    return x\n",
            "Python",
        ),
    ],
)
def test_five_stacks(tmp_path, manifest, source, code, stack):
    (tmp_path / manifest).write_text(
        "{}" if manifest.endswith("json") else "# manifest", encoding="utf-8"
    )
    (tmp_path / source).write_text(code, encoding="utf-8")
    model, scan = analyze_repository(tmp_path)
    assert not validate_model(model)
    assert any(e.get("technology") == stack for e in model["elements"])
    assert any(e["type"] == "code" for e in model["elements"])
    for e in model["evidence"]:
        assert e["reference"] in scan.texts
        assert 1 <= e["line"] <= len(scan.texts[e["reference"]].splitlines())
    assert not any(e["type"] == "person" for e in model["elements"])


def test_nested_scopes_imports_and_ambiguous_inputs(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]")
    (tmp_path / "first.py").write_text(
        "import second\ndef first():\n    return second.work()"
    )
    (tmp_path / "second.py").write_text("def work():\n    return 1")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested/pyproject.toml").write_text("[project]")
    (tmp_path / "nested/task.py").write_text("def task():\n    pass")
    model, scan = analyze_repository(tmp_path)
    assert not validate_model(model)
    assert len([e for e in model["elements"] if e["type"] == "container"]) == 2
    assert any(
        r["description"] == "Imports source module" for r in model["relationships"]
    )
    assert not any("adjacent" in a.lower() for a in model["assumptions"])
    (tmp_path / "pyproject.toml").unlink()
    (tmp_path / "nested/pyproject.toml").unlink()
    model, _ = analyze_repository(tmp_path, max_files=1, profile="container")
    assert any("No recognized manifest" in g for g in model["gaps"])
    assert any("truncated" in g for g in model["gaps"])
    (tmp_path / "broken.py").write_text("syntax !!!")
    model, _ = analyze_repository(tmp_path, profile="container")
    assert not validate_model(model, "container")


def test_no_supported_sources_and_aws(tmp_path):
    (tmp_path / "notes.md").write_text("business brief")
    model, _ = analyze_repository(tmp_path, profile="context")
    assert any("No supported" in g for g in model["gaps"])
    assert not validate_model(model, "context")
    (tmp_path / "main.tf").write_text(
        'resource "aws_s3_bucket" "archive" {}\nresource "aws_db_instance" "db" {}'
    )
    (tmp_path / "main.py").write_text("import boto3\nclient = boto3.client('s3')\n")
    files = scan_repository(tmp_path).texts
    signals = detect_aws(files)
    assert {s["kind"] for s in signals} == {"infrastructure", "sdk"}
    assert len(signals) == 3
    model, _ = analyze_repository(tmp_path, cloud_profile="aws", profile="container")
    assert any(
        e.get("cloud", {}).get("service") == "Amazon-Simple-Storage-Service"
        for e in model["elements"]
    )
    assert any("SDK usage" in g for g in model["gaps"])
    assert "deployment" not in model  # SDK evidence cannot establish placement.


def test_aws_assets_and_rejection(tmp_path, monkeypatch):
    assert len(aws.verify_assets()) > 800
    assert aws.resolve_service("Amazon ECS") == "Amazon-Elastic-Container-Service"
    assert aws.resolve_service("EC2") == "Amazon-EC2"
    assert aws.resolve_service("nonsense") is None
    assert aws.normalize_cloud_profile("AWS") == "aws"
    assert aws.normalize_cloud_profile("none") is None
    with pytest.raises(ValueError):
        aws.normalize_cloud_profile("azure")
    assert aws.icon_bytes("AWS-Lambda").startswith(b"<")
    with pytest.raises(SafetyError):
        aws.icon_bytes("missing")
    for data in (
        b"<svg><script/></svg>",
        b'<svg href="https://example.org/icon"/>',
        b'<svg onload="x"/>',
        b"<!DOCTYPE svg><svg/>",
        b"<html/>",
    ):
        with pytest.raises(SafetyError):
            aws.validate_svg(data)
    monkeypatch.setattr(aws, "ASSETS", tmp_path)
    (tmp_path / "manifest.json").write_text(json.dumps({"corrupt": "wrong"}))
    (tmp_path / "corrupt").write_text("bytes")
    with pytest.raises(SafetyError):
        aws.verify_assets()
    (tmp_path / "aws").mkdir()
    (tmp_path / "aws/icon.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    (tmp_path / "aws-catalog.json").write_text(
        json.dumps({"icon": {"file": "icon.svg"}})
    )
    (tmp_path / "manifest.json").write_text(json.dumps({"aws/icon.svg": "wrong"}))
    with pytest.raises(SafetyError, match="checksum"):
        aws.icon_bytes("icon")
