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
from architecture_suite.plan import render_plan
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
    args = parser.parse_args(["render", "--model", "x", "--output", "y", "--format", "all"])
    assert args.format == {"mermaid", "drawio", "png", "svg", "visio", "plantuml"}  # "all" means every format
    assert DEFAULT_FORMATS == {"mermaid", "png"}  # Draw.io, SVG, Visio and PlantUML are opt-in
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


@pytest.mark.browser
@pytest.mark.slow
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
    capsys.readouterr()
    assert main(base + ["--level", "all", "--dry-run"]) == 0  # renders the levels it has
    assert json.loads(capsys.readouterr().out)["levels_skipped"] == ["component", "code"]
    assert main(base + ["--level", "deployment", "--confirm-write"]) == 0
    capsys.readouterr()
    diagrams = sorted(
        p.relative_to(output).as_posix() for p in output.glob("0*/*") if p.is_file()
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
@pytest.mark.browser
@pytest.mark.slow
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
    # Re-rendering another level retires unchanged container files; edits are kept.
    capsys.readouterr()
    system = [arg if arg != "container" else "system" for arg in argv]
    edited = output / "02-containers/containers.mmd"
    edited.write_text("hand edit", encoding="utf-8")
    (output / "notes.md").write_text("mine", encoding="utf-8")
    assert main(system + ["--dry-run"]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["conflicts"] == ["02-containers/containers.mmd"]
    assert preview["overwrites_edited"] == []
    assert "02-containers/containers.svg" in preview["would_remove"]
    assert main(system + ["--confirm-write", "--confirm-overwrite"]) == 0
    assert json.loads(capsys.readouterr().out)["removed"] == preview["would_remove"]
    assert edited.read_text(encoding="utf-8") == "hand edit"
    assert (output / "notes.md").read_text(encoding="utf-8") == "mine"
    assert not (output / "02-containers/containers.svg").exists()
    assert (output / "01-system-context/system-context.svg").is_file()
    for text in [*output.rglob("*.mmd"), output / "architecture-report.md"]:
        assert b"\r" not in text.read_bytes()  # LF on every OS


@pytest.mark.browser
@pytest.mark.slow
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


@pytest.mark.browser
@pytest.mark.slow
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
        == 2
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


@pytest.mark.browser
@pytest.mark.slow
def test_doctor_ready_and_missing(monkeypatch, capsys):
    assert main(["doctor"]) == 0
    assert json.loads(capsys.readouterr().out)["offline"]

    def fail():
        raise ValueError("missing browser")

    monkeypatch.setattr(cli, "find_browser", fail)
    assert main(["doctor"]) == 3
    assert "missing browser" in capsys.readouterr().out


@pytest.mark.browser
@pytest.mark.slow
def test_examples_dry_and_write(tmp_path, capsys):
    output = tmp_path / "examples"
    argv = ["examples", "--output", str(output), "--overview-style", "executive"]
    assert main(argv + ["--dry-run"]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["systems"] == 3
    assert {Path(f).suffix for f in preview["files"] if "/0" in f} == {".mmd", ".png"}
    assert not output.exists()
    assert main(argv + ["--format", "visio", "--dry-run"]) == 0
    assert any(f.endswith(".vsdx") for f in json.loads(capsys.readouterr().out)["files"])
    assert main(argv + ["--format", "plantuml", "--dry-run"]) == 0
    assert any(f.endswith(".puml") for f in json.loads(capsys.readouterr().out)["files"])
    # Use the real exporter without PNG for this CLI transaction test.
    # PNG and the offline browser are exercised by export tests.
    assert main(argv + ["--format", "mermaid,drawio", "--confirm-write"]) == 0
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


def test_internal_errors_exit_4(inputs, monkeypatch, capsys):
    """A bug must not look like lint findings (1) or bad input (2)."""
    _, plan_path = inputs

    def broken(*args, **kwargs):
        raise KeyError("missing")

    monkeypatch.setattr(cli, "lint_plan", broken)
    assert main(["plan-lint", "--plan", str(plan_path)]) == 4
    err = capsys.readouterr().err
    assert "internal error: KeyError" in err and "please report" in err


def _subparsers(parser):
    import argparse

    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return action


def test_every_subcommand_and_flag_has_help():
    action = _subparsers(build_parser())
    helped = {choice.dest for choice in action._choices_actions if choice.help}
    assert helped == set(action.choices)
    for name, sub in action.choices.items():
        for option in sub._actions:
            assert option.help, (name, option.option_strings)
        assert "--format" not in sub.format_help() or "mermaid" in sub.format_help()


def test_format_names_are_case_insensitive(inputs, tmp_path, capsys):
    parser = build_parser()
    args = parser.parse_args(["render", "--model", "x", "--output", "y", "--format", "PNG,Mermaid"])
    assert args.format == {"png", "mermaid"}
    assert parser.parse_args(
        ["render", "--model", "x", "--output", "y", "--format", "ALL"]
    ).format == {"mermaid", "drawio", "png", "svg", "visio", "plantuml"}


def test_missing_input_names_flag_and_path_with_exit_2(tmp_path, capsys):
    missing = tmp_path / "nope.json"
    assert main(["verify", "--model", str(missing)]) == 2
    err = capsys.readouterr().err
    assert f"--model: no such file: {missing.resolve()}" in err
    assert main(["plan-lint", "--plan", str(tmp_path / "p.md")]) == 2
    assert "--plan: no such file" in capsys.readouterr().err
    assert main(["plan-draft", "--repo", str(tmp_path / "r"), "--output", str(tmp_path / "o.md")]) == 2
    assert "--repo: no such directory" in capsys.readouterr().err


def test_oversized_input_is_an_input_error(tmp_path, capsys):
    big = tmp_path / "big.json"
    with big.open("wb") as stream:
        stream.truncate(20_000_001)
    assert main(["verify", "--model", str(big)]) == 2
    assert "--model: file exceeds 20 MB" in capsys.readouterr().err


def test_broken_model_json_names_file_and_hint(inputs, capsys):
    inputs[0].write_text("{broken")
    assert main(["verify", "--model", str(inputs[0])]) == 2
    err = capsys.readouterr().err
    assert str(inputs[0]) in err and "expected architecture-model.json from" in err


def test_invalid_model_prints_one_finding_per_line(inputs, capsys):
    inputs[0].write_text(json.dumps({"schema_version": "2.0", "elements": [], "views": []}))
    assert main(["verify", "--model", str(inputs[0]), "--level", "container"]) == 3
    err = capsys.readouterr().err
    assert "Invalid architecture model:\n" in err
    assert "[{" not in err and ": " in err.split("\n", 1)[1]


def test_plan_yaml_error_reports_file_line(tmp_path, capsys):
    plan = tmp_path / "plan.md"
    lines = [
        "# Plan", "", "```yaml", "system: {}", "```", "", "text", "",
        "```yaml", "system:", "  name: a: b", "```",
    ]
    plan.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert main(["plan-lint", "--plan", str(plan)]) == 2
    assert "Malformed YAML at line 11" in capsys.readouterr().err


@pytest.mark.browser
@pytest.mark.slow
def test_envelope_keys_are_additive(inputs, tmp_path, capsys):
    out = tmp_path / "env"
    argv = ["plan-render", "--plan", str(inputs[1]), "--output", str(out), "--level", "container"]
    assert main(argv + ["--dry-run"]) == 0
    dry = json.loads(capsys.readouterr().out)
    assert dry["ok"] is True and dry["dry_run"] is True
    assert dry["write_confirmation_required"] is True
    assert "overview_styles" not in dry
    assert main(argv + ["--confirm-write"]) == 0
    written = json.loads(capsys.readouterr().out)
    assert written["dry_run"] is False and written["written"] is True
    assert written["write_confirmation_required"] is False
    assert {"files", "formats", "conflicts", "overwrites_edited", "removed"} <= set(written)
    assert main(argv[:-2] + ["--level", "overview", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["overview_styles"]


def test_examples_envelope(tmp_path, capsys):
    out = tmp_path / "ex"
    assert main(["examples", "--output", str(out), "--format", "mermaid", "--dry-run"]) == 0
    dry = json.loads(capsys.readouterr().out)
    assert dry["ok"] is True and dry["dry_run"] is True


@pytest.mark.browser
def test_doctor_announces_itself_on_stderr(monkeypatch, capsys):
    monkeypatch.setattr(cli, "verify_assets", lambda: None)
    main(["doctor"])
    assert "checking runtime..." in capsys.readouterr().err


@pytest.mark.slow
def test_publish_builds_each_scene_once(inputs, tmp_path, monkeypatch):
    from architecture_suite import renderers

    real = renderers._scene
    built = []

    def counting(model, view, view_scenes=None):
        built.append(view["type"] + ":" + str(view.get("style", view.get("level", ""))))
        return real(model, view, view_scenes)

    monkeypatch.setattr(renderers, "_scene", counting)
    argv = [
        "plan-render", "--plan", str(inputs[1]), "--output", str(tmp_path / "out"),
        "--format", "mermaid,plantuml,svg", "--level", "container", "--confirm-write",
    ]
    assert main(argv) == 0
    specs = renderers.diagram_specs(
        json.loads(inputs[0].read_text()), parse_overview_styles(None), "container"
    )
    assert len(built) == len(specs) > 0


@pytest.mark.slow
def test_small_multiples_publish_lays_out_each_view_once(inputs, tmp_path, monkeypatch):
    from architecture_suite import overview_layout, renderers

    real = renderers.build_view_scene_elk
    laid_out = []

    def counting(model, view):
        laid_out.append(view["id"])
        return real(model, view)

    monkeypatch.setattr(renderers, "build_view_scene_elk", counting)
    monkeypatch.setattr(overview_layout, "build_view_scene_elk", counting)
    argv = [
        "plan-render", "--plan", str(inputs[1]), "--output", str(tmp_path / "out"),
        "--format", "mermaid", "--overview-style", "small-multiples", "--confirm-write",
    ]
    assert main(argv) == 0
    views = [v["id"] for v in json.loads(inputs[0].read_text())["views"]]
    assert sorted(laid_out) == sorted(views)
