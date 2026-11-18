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
from architecture_suite.cloud_signals import detect_aws
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
    for function, path, text in (
        (canonical_existing_directory, file, "no such directory"),
        (canonical_existing_file, source, "no such file"),
        (canonical_existing_file, source / "missing", "no such file"),
    ):
        # Missing input is an input error (ValueError, exit 2), not a safety error.
        with pytest.raises(ValueError, match=text) as caught:
            function(path, "--flag")
        assert not isinstance(caught.value, SafetyError)
        assert str(caught.value).startswith("--flag: ")
    for function, path in (
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


def test_publish_survives_read_only_files(tmp_path):
    """A read-only file in the old output must not turn a good publish into a failure."""
    import stat

    output = tmp_path / "published"
    (output / "keep").mkdir(parents=True)
    notes = output / "keep" / "notes.txt"
    notes.write_text("mine")
    notes.chmod(stat.S_IREAD)
    try:
        with atomic_output_directory(output) as stage:
            (stage / "diagram.svg").write_text("<svg/>")
        assert (output / "diagram.svg").is_file()
        assert notes.read_text() == "mine"
        assert not list(tmp_path.glob(".architecture-stage-*"))
    finally:
        notes.chmod(stat.S_IWRITE | stat.S_IREAD)


def test_cleanup_failure_warns_without_masking(tmp_path, monkeypatch, capsys):
    import shutil

    from architecture_suite import safety

    def locked(path, **kwargs):
        raise PermissionError("file in use")

    output = tmp_path / "published"
    output.mkdir()
    (output / "old.svg").write_text("<svg/>")  # promotion then leaves a backup to delete
    monkeypatch.setattr(shutil, "rmtree", locked)
    with atomic_output_directory(output) as stage:
        (stage / "diagram.svg").write_text("<svg/>")
    assert (output / "diagram.svg").is_file()
    assert "could not remove temporary folder" in capsys.readouterr().err
    with pytest.raises(RuntimeError, match="export failed"):  # the original error wins
        with atomic_output_directory(output):
            raise RuntimeError("export failed")
    monkeypatch.undo()
    for leftover in tmp_path.glob(".architecture-stage-*"):
        safety._remove_temporary(leftover)


def test_unseeded_stage_drops_old_files(tmp_path):
    output = tmp_path / "installed"
    output.mkdir()
    (output / "removed_module.py").write_text("old")
    with atomic_output_directory(output, seed_existing=False) as stage:
        (stage / "module.py").write_text("new")
    assert sorted(p.name for p in output.iterdir()) == ["module.py"]


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


def _publish(output, owner, files, *, extra=None, fail=False):
    """Write `files` (name -> text) as `owner` through the transactional publisher."""
    from architecture_suite.safety import ownership_changes

    changes = ownership_changes(output, owner, list(files))
    with atomic_output_directory(output, owner=owner, command=owner, files=list(files)) as stage:
        for name, text in files.items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        if extra:
            extra(stage)
        if fail:
            raise RuntimeError("export failed")
    return changes


def test_output_manifest_removes_stale_keeps_edited_and_unlisted(tmp_path):
    from architecture_suite.safety import OUTPUT_MANIFEST, ownership_changes

    output = tmp_path / "out"
    output.mkdir()
    (output / "legacy.txt").write_text("user file")
    old = {"02-containers/a.svg": "a", "02-containers/b.svg": "b", "03-components/c.svg": "c"}
    # First run: nothing is adopted or deleted; the manifest records what was written.
    assert _publish(output, "c4", old) == {"remove": [], "conflicts": [], "overwrites_edited": []}
    manifest = json.loads((output / OUTPUT_MANIFEST).read_text())
    assert sorted(manifest["owners"]["c4"]["files"]) == sorted(old)
    assert "legacy.txt" not in json.dumps(manifest)
    (output / "02-containers/b.svg").write_text("edited by hand")
    new = {"02-containers/a.svg": "a2"}
    preview = ownership_changes(output, "c4", list(new))
    assert preview == {
        "remove": ["03-components/c.svg"],
        "conflicts": ["02-containers/b.svg"],
        "overwrites_edited": [],
    }
    assert _publish(output, "c4", new) == preview
    assert not (output / "03-components").exists()  # stale file and its empty folder
    assert (output / "02-containers/b.svg").read_text() == "edited by hand"
    assert (output / "legacy.txt").read_text() == "user file"
    files = json.loads((output / OUTPUT_MANIFEST).read_text())["owners"]["c4"]["files"]
    assert sorted(files) == ["02-containers/a.svg"]  # the edited file was released
    assert ownership_changes(output, "c4", []) == {
        "remove": ["02-containers/a.svg"], "conflicts": [], "overwrites_edited": []
    }
    assert ownership_changes(tmp_path / "missing", "c4", []) == {
        "remove": [], "conflicts": [], "overwrites_edited": []
    }
    # A file this run writes again, edited since the last run, is reported.
    (output / "02-containers/a.svg").write_text("edited again")
    assert ownership_changes(output, "c4", ["02-containers/a.svg"])["overwrites_edited"] == [
        "02-containers/a.svg"
    ]


def test_output_manifest_owners_are_isolated(tmp_path):
    from architecture_suite.safety import OUTPUT_MANIFEST

    output = tmp_path / "out"
    _publish(output, "c4", {"02-containers/a.svg": "a", "shared.md": "c4"})
    _publish(output, "scenario-render", {"scenario.svg": "s"})
    _publish(output, "scenario-render", {"scenario.mmd": "s"})
    assert (output / "02-containers/a.svg").is_file()  # another owner's files survive
    assert not (output / "scenario.svg").exists()
    _publish(output, "scenario-render", {"scenario.mmd": "s", "shared.md": "scenario"})
    owners = json.loads((output / OUTPUT_MANIFEST).read_text())["owners"]
    assert "shared.md" in owners["scenario-render"]["files"]
    assert "shared.md" not in owners["c4"]["files"]  # ownership moved with the write
    _publish(output, "c4", {"02-containers/a.svg": "a"})
    assert (output / "shared.md").read_text() == "scenario"


@pytest.mark.parametrize(
    "files",
    [
        {"../escape.txt": "0" * 64},
        {"C:/absolute.txt" if os.name == "nt" else "/absolute.txt": "0" * 64},
        {"a.txt": "not-a-hash"},
        {".architecture-suite-manifest.json": "0" * 64},
        "bad json",
    ],
)
def test_output_manifest_rejects_unsafe_or_malformed_entries(tmp_path, files):
    from architecture_suite.safety import OUTPUT_MANIFEST, ownership_changes

    output = tmp_path / "out"
    output.mkdir()
    (output / "a.txt").write_text("keep")
    text = (
        files
        if isinstance(files, str)
        else json.dumps(
            {"schema_version": "architecture-output-manifest/v1", "owners": {"c4": {"files": files}}}
        )
    )
    (output / OUTPUT_MANIFEST).write_text(text)
    with pytest.raises(SafetyError):
        ownership_changes(output, "c4", [])
    with pytest.raises(SafetyError):
        _publish(output, "c4", {"b.txt": "b"})
    assert (output / "a.txt").read_text() == "keep" and not (output / "b.txt").exists()


def test_output_manifest_rollback_and_missing_outputs(tmp_path, monkeypatch):
    from architecture_suite.safety import OUTPUT_MANIFEST

    output = tmp_path / "out"
    _publish(output, "c4", {"old.svg": "old"})
    before = (output / OUTPUT_MANIFEST).read_bytes()
    with pytest.raises(RuntimeError):
        _publish(output, "c4", {"new.svg": "new"}, fail=True)
    assert (output / "old.svg").is_file() and (output / OUTPUT_MANIFEST).read_bytes() == before
    with pytest.raises(SafetyError, match="not written"):
        _publish(output, "c4", {"new.svg": "new"}, extra=lambda stage: (stage / "new.svg").unlink())
    assert (output / "old.svg").is_file()
    original = Path.rename

    def fail_promotion(self, target):
        if self.name.startswith(".architecture-stage-") and not self.name.endswith("-backup"):
            raise OSError("simulated promotion failure")
        return original(self, target)

    monkeypatch.setattr(Path, "rename", fail_promotion)
    with pytest.raises(OSError):
        _publish(output, "c4", {"new.svg": "new"})
    assert (output / "old.svg").is_file() and (output / OUTPUT_MANIFEST).read_bytes() == before


@pytest.mark.parametrize(
    "text",
    [
        "token=abcd1234",
        'password = "hunter2"',
        "api_key='sensitivevalue'",
        '"password": "sensitivevalue"',
        "secret: Zx81kQp0wLm3",
        "access_token: eyJhbGciOiJIUzI1NiIsInR5cCI6",
        "postgres://app:pw@db/orders",
        "redis://app:pw@cache:6379/0",
        "redis://:pw@cache:6379",
        "rediss://:pw@cache:6380",
        "amqp://guest:pw@mq:5672/",
        "amqps://:pw@mq",
        "AKIA" + "A" * 16,
    ],
)
def test_credentials_are_detected(text):
    assert "REDACTED" in redact(text)


@pytest.mark.parametrize(
    "text",
    [
        "login(self, username: str, password: str) -> bool",
        "refresh(self, token: str)",
        "Stores the session token: Redis-backed cache",
        "Reset password: email link",
        "secret: none",
    ],
)
def test_ordinary_text_is_not_a_credential(text):
    assert redact(text) == text


def test_plan_credential_finding_names_the_field(plan):
    from architecture_suite.plan import lint_plan

    plan["containers"][0]["description"] = "Calls the API with token=abcd1234"
    found = [f for f in lint_plan(plan) if f.code == "credential"]
    assert [f.where for f in found] == ["containers.0.description"]
    plan["containers"][0]["description"] = "Stores the session token: Redis-backed cache"
    assert not [f for f in lint_plan(plan) if f.code == "credential"]


def test_cloud_signals_count_declarations_not_references():
    """One container per declared resource: references and attachment types are not resources."""
    from architecture_suite.cloud_signals import detect_gcp

    files = {
        "main.tf": (
            'resource "aws_s3_bucket" "logs" {}\n'
            'resource "aws_s3_bucket_policy" "logs" {\n'
            "  bucket = aws_s3_bucket.logs.id\n"
            "}\n"
            'resource "aws_lambda_function" "fn" {\n'
            "  environment { variables = { BUCKET = aws_s3_bucket.logs.id } }\n"
            "}\n"
            'resource "aws_lambda_permission" "allow" {\n'
            "  function_name = aws_lambda_function.fn.function_name\n"
            "}\n"
        ),
        "template.yaml": (
            "Resources:\n"
            "  Bucket:\n    Type: AWS::S3::Bucket\n"
            "  Policy:\n    Type: AWS::S3::BucketPolicy\n"
            "  Fn:\n    Type: 'AWS::Lambda::Function'\n"
            "  Allow:\n    Type: AWS::Lambda::Permission\n"
        ),
        "stack.json": '{"Resources": {"T": {"Type": "AWS::DynamoDB::Table"}}}',
        "gcp.tf": (
            'resource "google_storage_bucket" "b" {}\n'
            'resource "google_storage_bucket_iam_member" "m" {\n'
            "  bucket = google_storage_bucket.b.name\n"
            "}\n"
        ),
    }
    found = sorted(
        (s["reference"], s["line"], s["kind"]) for s in detect_aws(files) if s["kind"] == "infrastructure"
    )
    assert found == [
        ("main.tf", 1, "infrastructure"),
        ("main.tf", 5, "infrastructure"),
        ("stack.json", 1, "infrastructure"),
        ("template.yaml", 3, "infrastructure"),
        ("template.yaml", 7, "infrastructure"),
    ]
    assert [(s["reference"], s["line"]) for s in detect_gcp(files)] == [("gcp.tf", 1)]
