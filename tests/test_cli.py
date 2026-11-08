import json
from pathlib import Path
import subprocess
import sys
import sysconfig
import pytest
from architecture_suite.cli import (
    main,
    build_parser,
    DEFAULT_FORMATS,
    parse_overview_styles,
)
from architecture_suite.draft import render_plan
from architecture_suite import __version__, cli


def test_defaults_and_invalid_arguments():
    parser = build_parser()
    args = parser.parse_args(["analyze", "--repo", "x", "--output", "y"])
    assert args.format == DEFAULT_FORMATS
    assert (
        args.level == "all"
        and args.max_files == 2000
        and args.max_file_bytes == 1000000
        and args.max_total_bytes == 50000000
        and args.timeout == 45.0
    )
    args = parser.parse_args(["plan-draft", "--repo", "x", "--output", "y"])
    assert args.classification == "Internal" and args.max_file_bytes == 400000
    assert parse_overview_styles(None) == ("progressive",)
    assert parse_overview_styles(["complete,executive", "executive"]) == (
        "executive",
        "complete",
    )
    for argv in (
        ["--version"],
        [],
        ["unknown"],
        ["render", "--model", "x", "--output", "y", "--format", "pdf"],
        ["analyze", "--repo", "x", "--output", "y", "--cloud-profile", "azure"],
    ):
        with pytest.raises(SystemExit):
            parser.parse_args(argv)


def test_deployment_level_needs_no_component_or_code_views(tmp_path, capsys):
    plan = {
        "system": {
            "name": "Shop",
            "description": "Online shop",
            "classification": "Internal",
            "scope": "Checkout",
        },
        "containers": [
            {
                "name": "Orders API",
                "description": "Takes orders",
                "technology": "Python",
                "aws_service": "AWS Lambda",
                "evidence": "brief:1",
            }
        ],
        "flows": [],
        "deployment": {
            "nodes": [{"name": "Production account", "type": "account"}],
            "placements": [{"element": "Orders API", "node": "Production account"}],
        },
    }
    source = tmp_path / "plans" / "plan.md"
    source.parent.mkdir()
    source.write_text(render_plan(plan), encoding="utf-8")
    output = tmp_path / "out"
    base = ["plan-render", "--plan", str(source), "--output", str(output)]
    base += ["--format", "mermaid,drawio,svg"]
    assert main(["plan-lint", "--plan", str(source), "--strict"]) == 0
    assert main(base + ["--level", "all", "--dry-run"]) == 3  # still needs L1-L4 evidence
    assert main(base + ["--level", "deployment", "--confirm-write"]) == 0
    capsys.readouterr()
    diagrams = sorted(
        p.relative_to(output).as_posix() for p in output.rglob("*") if p.suffix != ".md"
        and p.is_file() and p.name != "plan-fidelity.json"
    )
    assert diagrams == [
        "06-aws-deployment/aws-deployment.drawio",
        "06-aws-deployment/aws-deployment.mmd",
        "06-aws-deployment/aws-deployment.svg",
    ]
    plan.pop("deployment")
    source.write_text(render_plan(plan), encoding="utf-8")
    assert main(base + ["--level", "deployment", "--dry-run"]) == 3
    assert "no deployment section" in capsys.readouterr().err


@pytest.mark.parametrize(
    "command,input_flag", [("render", "--model"), ("plan-render", "--plan")]
)
def test_publish_dry_write_overwrite(inputs, tmp_path, capsys, command, input_flag):
    input = inputs[0] if command == "render" else inputs[1]
    output = tmp_path / "artifacts"
    argv = [
        command,
        input_flag,
        str(input),
        "--output",
        str(output),
        "--format",
        "mermaid,drawio,svg",
        "--level",
        "container",
    ]
    assert main(argv + ["--dry-run"]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert not output.exists()
    assert main(argv) == 3
    assert not output.exists()
    assert main(argv + ["--confirm-write"]) == 0
    capsys.readouterr()
    assert sorted(
        p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()
    ) == sorted(preview["files"])
    before = {p: p.read_bytes() for p in output.rglob("*") if p.is_file()}
    assert main(argv + ["--confirm-write"]) == 3
    assert all(p.read_bytes() == b for p, b in before.items())
    assert main(argv + ["--confirm-write", "--confirm-overwrite"]) == 0
    if command == "plan-render":
        assert not (output / "architecture-model.json").exists()
        assert json.loads((output / "plan-fidelity.json").read_text())["lossless"]
        assert (
            main(
                argv
                + [
                    "--confirm-write",
                    "--confirm-overwrite",
                    "--emit-model",
                    "--augmented",
                ]
            )
            == 0
        )
        assert (output / "architecture-model.json").is_file()
        assert json.loads((output / "plan-fidelity.json").read_text())["augmented"]


def test_plan_draft_lint_and_analyze(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]")
    (repo / "main.py").write_text("def work(x):\n    return x")
    plan = tmp_path / "draft.md"
    base = ["plan-draft", "--repo", str(repo), "--output", str(plan)]
    assert main(base + ["--dry-run"]) == 0
    assert not plan.exists()
    assert main(base) == 3
    assert main(base + ["--confirm-write"]) == 0
    assert main(base + ["--confirm-write"]) == 3
    assert main(base + ["--confirm-write", "--confirm-overwrite"]) == 0
    assert main(["plan-lint", "--plan", str(plan)]) == 0
    inside = ["plan-draft", "--repo", str(repo), "--output", str(repo / "docs/plan.md")]
    assert main(inside + ["--confirm-write"]) == 3  # never inside the analyzed repository
    assert not (repo / "docs").exists()
    out = tmp_path / "analysis"
    base = [
        "analyze",
        "--repo",
        str(repo),
        "--output",
        str(out),
        "--format",
        "mermaid",
        "--level",
        "container",
    ]
    assert main(base + ["--dry-run"]) == 0
    assert not out.exists()
    assert main(base + ["--confirm-write"]) == 0
    assert (out / "architecture-model.json").is_file()
    assert (
        main(
            ["analyze", "--repo", str(repo), "--output", str(repo / "out"), "--dry-run"]
        )
        == 3
    )
    assert (
        main(
            [
                "plan-draft",
                "--repo",
                str(repo),
                "--output",
                str(repo / "main.py"),
                "--confirm-write",
            ]
        )
        == 3
    )
    assert (
        main(
            [
                "plan-draft",
                "--repo",
                str(repo),
                "--output",
                str(repo),
                "--confirm-write",
            ]
        )
        == 3
    )


def test_lint_strict_and_invalid_inputs(inputs, plan, tmp_path, capsys):
    plan["people"][0].pop("evidence")
    inputs[1].write_text(render_plan(plan), encoding="utf-8")
    assert main(["plan-lint", "--plan", str(inputs[1])]) == 0
    assert main(["plan-lint", "--plan", str(inputs[1]), "--strict"]) == 1
    plan["flows"][0]["to"] = "missing"
    inputs[1].write_text(render_plan(plan), encoding="utf-8")
    assert main(["plan-lint", "--plan", str(inputs[1])]) == 1
    assert (
        main(
            [
                "plan-render",
                "--plan",
                str(inputs[1]),
                "--output",
                str(tmp_path / "out"),
                "--dry-run",
            ]
        )
        == 3
    )
    inputs[0].write_text("{broken")
    assert main(["verify", "--model", str(inputs[0])]) == 2


def test_verify_and_style_constraints(inputs, tmp_path, model, capsys, monkeypatch):
    assert main(["verify", "--model", str(inputs[0]), "--level", "system"]) == 0
    assert main(["verify", "--model", str(inputs[0]), "--overview-style", "all"]) == 0
    assert (
        main(
            [
                "verify",
                "--model",
                str(inputs[0]),
                "--level",
                "code",
                "--overview-style",
                "executive",
            ]
        )
        == 3
    )
    assert (
        main(
            [
                "render",
                "--model",
                str(inputs[0]),
                "--output",
                str(tmp_path / "out"),
                "--dry-run",
                "--overview-style",
                "bad",
            ]
        )
        == 2
    )
    model["elements"][0]["id"] = "../bad"
    inputs[0].write_text(json.dumps(model))
    assert main(["verify", "--model", str(inputs[0])]) == 3
    inputs[0].write_text(
        json.dumps(
            __import__(
                "architecture_suite.examples", fromlist=["example_model"]
            ).example_model()
        )
    )
    monkeypatch.setattr(
        cli, "layout_report", lambda *a, **kw: {"ok": False, "diagrams": {}}
    )
    assert main(["verify", "--model", str(inputs[0])]) == 1


def test_doctor_ready_and_missing(monkeypatch, capsys):
    assert main(["doctor"]) == 0
    assert json.loads(capsys.readouterr().out)["offline"]

    def fail():
        raise ValueError("missing browser")

    monkeypatch.setattr(cli, "find_browser", fail)
    assert main(["doctor"]) == 3
    assert "missing browser" in capsys.readouterr().out


def test_examples_dry_and_write(tmp_path, capsys, monkeypatch):
    output = tmp_path / "examples"
    argv = ["examples", "--output", str(output), "--overview-style", "executive"]
    assert main(argv + ["--dry-run"]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["systems"] == 3
    assert not output.exists()
    # Use the real exporter but SVG instead of PNG for this CLI transaction test.
    # PNG, offline browser and the unchanged default-format examples are exercised by export tests.
    monkeypatch.setattr(cli, "DEFAULT_FORMATS", {"mermaid", "drawio"})
    assert main(argv + ["--confirm-write"]) == 0
    assert len(list(output.glob("*/architecture-model.json"))) == 3


def test_module_and_console_entrypoints(tmp_path):
    for command in (
        [sys.executable, "-m", "architecture_suite", "--version"],
        [
            # The scripts folder, not the interpreter's folder: they differ for a system
            # (non-venv) Python on Windows, as on CI runners.
            str(
                Path(sysconfig.get_path("scripts"))
                / (
                    "architecture-suite.exe"
                    if sys.platform == "win32"
                    else "architecture-suite"
                )
            ),
            "--version",
        ],
    ):
        result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
        assert result.returncode == 0
        assert __version__ in result.stdout


def test_malformed_model_projection_is_a_controlled_failure(inputs):
    inputs[0].write_text(json.dumps({"schema_version": "2.0", "elements": [None]}))
    assert main(["verify", "--model", str(inputs[0]), "--level", "container"]) == 3
