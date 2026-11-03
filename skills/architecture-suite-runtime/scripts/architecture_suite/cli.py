"""Architecture Suite command-line interface."""

from __future__ import annotations
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import tempfile
from . import __version__
from .analyzer import analyze_repository, draft_plan
from .aws import (
    gcp_icon_root,
    gcp_icon_sources,
    gcp_icon_status,
    install_gcp_icons,
    verify_assets,
)
from .draft import render_plan
from .examples import SCENARIOS, example_model, example_plan
from .layout_host import layout_graph
from .model import load_model, normalized_model, project_model, validate_model
from .overview_layout import normalize_overview_styles
from .plan import compile_plan, errors, lint_plan, parse_plan_document
from .renderers import (
    ARTIFACT_LEVELS,
    browser_page,
    expected_artifact_paths,
    find_browser,
    layout_report,
    write_rendered_artifacts,
)
from .report import render_architecture_report
from .runtime_env import check_stamp
from .safety import (
    SafetyError,
    atomic_output_directory,
    canonical_existing_directory,
    canonical_existing_file,
    canonical_output_directory,
    require_write_authorization,
    scan_repository,
)

DEFAULT_FORMATS = {"mermaid", "drawio", "png"}


def _json_print(value):
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _parse_formats(value):
    formats = (
        DEFAULT_FORMATS.copy()
        if value == "all"
        else {x.strip() for x in value.split(",") if x.strip()}
    )
    if not formats or formats - DEFAULT_FORMATS - {"svg"}:
        raise argparse.ArgumentTypeError("format must be all or mermaid,drawio,png,svg")
    return formats


def parse_overview_styles(values: list[str] | None) -> tuple[str, ...]:
    return normalize_overview_styles(values)


def _selected_model(model, level, styles):
    if level == "all":
        selected = model
        profile = "code"
    else:
        profile = {
            "system": "context",
            "container": "container",
            "component": "component",
            "code": "code",
        }.get(level, "code")
        if level == "overview":
            profile = (
                "container"
                if set(styles) <= {"executive"}
                else "component"
                if set(styles) <= {"executive", "progressive"}
                else "code"
            )
        try:
            selected = project_model(model, profile)
        except (KeyError, TypeError, AttributeError) as exc:
            raise SafetyError(
                "Malformed architecture model cannot be projected"
            ) from exc
    findings = validate_model(selected, profile)
    if findings:
        raise SafetyError("Invalid architecture model: " + json.dumps(findings[:8]))
    return normalized_model(selected)


def cmd_doctor(args) -> int:
    result = {"version": __version__, "python": sys.version.split()[0], "offline": True}

    def check_browser():
        if find_browser() is None:
            raise SafetyError(
                "Local Chromium missing; run python -m playwright install chromium"
            )
        with browser_page():
            pass

    for key, check in (
        ("assets", verify_assets),
        (
            "layout_engine",
            lambda: layout_graph(
                {
                    "id": "root",
                    "children": [{"id": "test", "width": 20, "height": 20}],
                    "layoutOptions": {"elk.algorithm": "layered"},
                }
            ),
        ),
        ("browser", check_browser),
    ):
        try:
            check()
            result[key] = "ok"
        except (OSError, ValueError) as exc:
            result[key] = str(exc)
    # "unmanaged" (no bootstrap stamp: developer or CI environment) is informational.
    result["runtime_deps"] = check_stamp()
    try:  # optional and user-installed, so informational only
        result["gcp_icons"] = gcp_icon_status()
    except (OSError, ValueError) as exc:
        result["gcp_icons"] = str(exc)
    _json_print(result)
    gating = ("assets", "layout_engine", "browser")
    healthy = all(result[k] == "ok" for k in gating) and result["runtime_deps"] in {
        "ok",
        "unmanaged",
    }
    return 0 if healthy else 3


def cmd_install_gcp_icons(args) -> int:
    if not (args.modern or args.legacy_zip or args.from_dir):
        raise ValueError("give --modern, --legacy-zip and/or --from")
    sources = gcp_icon_sources(
        modern=canonical_existing_directory(Path(args.modern)) if args.modern else None,
        legacy_zip=canonical_existing_file(Path(args.legacy_zip)) if args.legacy_zip else None,
        from_dir=canonical_existing_directory(Path(args.from_dir)) if args.from_dir else None,
    )
    target = canonical_output_directory(Path(args.target) if args.target else gcp_icon_root())
    if args.dry_run:
        _json_print({"operation": "install-gcp-icons", "target": str(target), "found": len(sources)})
        return 0
    require_write_authorization(target, args.confirm_write, args.confirm_overwrite)
    with atomic_output_directory(target) as stage:
        result = install_gcp_icons(sources, stage)
    _json_print({"target": str(target), **result})
    if not result["installed"]:
        return 2
    return 1 if result["checksum_mismatch"] else 0


def cmd_plan_lint(args) -> int:
    plan = parse_plan_document(
        canonical_existing_file(Path(args.plan)).read_text(encoding="utf-8")
    )
    findings = lint_plan(plan, args.gcp_icon_style)
    _json_print(
        {
            "operation": "plan-lint",
            "ok": not errors(findings) and not (args.strict and findings),
            "finding_count": len(findings),
            "error_count": len(errors(findings)),
            "advisory_count": len(findings) - len(errors(findings)),
            "strict": args.strict,
            "status": "findings" if findings else "clean",
            "findings": [asdict(f) for f in findings],
        }
    )
    return 1 if errors(findings) or (args.strict and findings) else 0


def cmd_plan_draft(args) -> int:
    root = canonical_existing_directory(Path(args.repo))
    output = Path(args.output).absolute()
    # The output itself can be a file, but never a link or an input source file.
    from .safety import _no_links

    _no_links(output)
    if output.exists() and not output.is_file():
        raise SafetyError("Plan output must be a file")
    if output.resolve().is_relative_to(root) and output.suffix.lower() not in {
        ".md",
        ".markdown",
    }:
        raise SafetyError("A plan inside the repository must use a Markdown filename")
    scan = scan_repository(
        root,
        max_files=args.max_files,
        max_file_bytes=args.max_file_bytes,
        max_total_bytes=args.max_total_bytes,
        timeout_seconds=args.timeout,
    )
    plan = draft_plan(root, scan, args.classification, args.cloud_profile)
    summary = {
        "operation": "plan-draft",
        "output": str(output),
        "files_scanned": list(scan.texts),
        "prompt_injection_paths": list(scan.prompt_injection_paths),
        "truncated": scan.truncated,
        "gaps": plan["gaps"],
    }
    if args.dry_run:
        _json_print(summary)
        return 0
    require_write_authorization(output, args.confirm_write, args.confirm_overwrite)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".architecture-plan-", dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(render_plan(plan))
        _no_links(output)
        os.replace(temp, output)
    finally:
        if Path(temp).exists():
            Path(temp).unlink()
    _json_print(summary)
    return 0


def cmd_verify(args) -> int:
    styles = parse_overview_styles(args.overview_style)
    _check_styles(args)
    model = _selected_model(
        load_model(canonical_existing_file(Path(args.model))), args.level, styles
    )
    result = layout_report(model, styles, args.level)
    result.update(
        operation="verify",
        status="clean" if result["ok"] else "findings",
        verified_scenes=len(result["diagrams"]),
    )
    _json_print(result)
    return 0 if result["ok"] else 1


def _check_styles(args):
    if getattr(args, "overview_style", None) and getattr(args, "level", "all") not in {
        "all",
        "overview",
    }:
        raise SafetyError(
            "--overview-style can be used only with --level all or overview"
        )


def cmd_publish(args) -> int:
    _check_styles(args)
    output = canonical_output_directory(Path(args.output))
    styles = parse_overview_styles(args.overview_style)
    fidelity, plan = None, None
    if args.command == "plan-render":
        input_path = canonical_existing_file(Path(args.plan))
        plan = parse_plan_document(input_path.read_text(encoding="utf-8"))
        blocking = errors(lint_plan(plan, args.gcp_icon_style))
        if blocking:
            raise SafetyError("Plan has blocking findings: " + blocking[0].render())
        model, fidelity = compile_plan(plan, args.gcp_icon_style)
    elif args.command == "analyze":
        input_path = canonical_existing_directory(Path(args.repo))
        if output.is_relative_to(input_path) or input_path.is_relative_to(output):
            raise SafetyError("Analysis output must be outside the source repository")
        model, _ = analyze_repository(
            input_path,
            classification=args.classification,
            max_files=args.max_files,
            max_file_bytes=args.max_file_bytes,
            max_total_bytes=args.max_total_bytes,
            timeout_seconds=args.timeout,
            cloud_profile=args.cloud_profile,
        )
    else:
        input_path = canonical_existing_file(Path(args.model))
        model = load_model(input_path)
    if input_path.is_relative_to(output):
        raise SafetyError("Output must not contain its input")
    model = _selected_model(model, args.level, styles)
    formats = args.format
    paths = expected_artifact_paths(model, formats, styles, args.level)
    paths.append("architecture-report.md")
    if fidelity:
        paths.extend(["plan-fidelity.md", "plan-fidelity.json"])
    if args.command != "plan-render" or args.emit_model:
        paths.append("architecture-model.json")
    summary = {
        "operation": args.command,
        "output_root": str(output),
        "files": paths,
        "expected_file_count": len(paths),
        "formats": sorted(formats),
        "overview_styles": list(styles),
        "write_confirmation_required": True,
        "overwrite_confirmation_required": output.exists() and any(output.iterdir()),
    }
    if args.dry_run:
        _json_print(summary)
        return 0
    require_write_authorization(output, args.confirm_write, args.confirm_overwrite)
    with atomic_output_directory(output) as stage:
        write_rendered_artifacts(
            model,
            stage,
            formats,
            styles,
            args.level,
            allow_layout_findings=getattr(args, "allow_layout_findings", False),
        )
        verification = layout_report(model, styles, args.level)
        (stage / "architecture-report.md").write_text(
            render_architecture_report(model, verification=verification),
            encoding="utf-8",
        )
        if "architecture-model.json" in paths:
            (stage / "architecture-model.json").write_text(
                json.dumps(model, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        if fidelity:
            account = {
                **fidelity.as_dict(),
                "augmented": args.augmented,
                "layout": verification,
                "advisories": [asdict(f) for f in lint_plan(plan, args.gcp_icon_style) if not f.blocking],
            }
            (stage / "plan-fidelity.json").write_text(
                json.dumps(account, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            (stage / "plan-fidelity.md").write_text(
                "# Plan fidelity\n\n```json\n"
                + json.dumps(account, indent=2, ensure_ascii=False)
                + "\n```\n",
                encoding="utf-8",
            )
    _json_print(summary)
    return 0


def cmd_examples(args) -> int:
    output = canonical_output_directory(Path(args.output))
    styles = parse_overview_styles(args.overview_style)
    paths = []
    for index, scenario in enumerate(SCENARIOS):
        paths.extend(
            scenario["id"] + "/" + p
            for p in expected_artifact_paths(
                example_model(index), DEFAULT_FORMATS, styles
            )
        )
        paths.extend(
            scenario["id"] + "/" + p
            for p in ("architecture-model.json", "architecture-plan.md")
        )
    paths.append("index.md")
    paths.append("README.md")
    if args.dry_run:
        _json_print(
            {"operation": "examples", "files": paths, "systems": len(SCENARIOS)}
        )
        return 0
    require_write_authorization(output, args.confirm_write, args.confirm_overwrite)
    with atomic_output_directory(output) as stage:
        for index, scenario in enumerate(SCENARIOS):
            folder = stage / scenario["id"]
            folder.mkdir(exist_ok=True)
            model = example_model(index)
            write_rendered_artifacts(model, folder, DEFAULT_FORMATS, styles)
            (folder / "architecture-model.json").write_text(
                json.dumps(model, indent=2), encoding="utf-8"
            )
            (folder / "architecture-plan.md").write_text(
                render_plan(example_plan(index)), encoding="utf-8"
            )
        (stage / "README.md").write_text(
            "# Fictional Architecture Suite examples\n\nGenerated by the runtime; all facts are illustrative.\n",
            encoding="utf-8",
        )
        (stage / "index.md").write_text(
            "# Fictional examples\n\n"
            + "\n".join(
                f"- [{s['name']}]({s['id']}/architecture-plan.md)" for s in SCENARIOS
            )
            + "\n",
            encoding="utf-8",
        )
    _json_print({"operation": "examples", "files": paths})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="architecture-suite")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    from .extensions import register_commands

    register_commands(commands)
    commands.add_parser(
        "doctor", help="Inspect offline runtime readiness"
    ).set_defaults(func=cmd_doctor)
    icons = commands.add_parser(
        "install-gcp-icons",
        help="Install optional Google Cloud icons from your own download (https://cloud.google.com/icons)",
    )
    icons.add_argument("--modern", help="extracted modern icon folder")
    icons.add_argument("--legacy-zip", help="legacy icon archive (.zip)")
    icons.add_argument("--from", dest="from_dir", help="folder laid out as modern/ and legacy/")
    icons.add_argument("--target", help="install folder (default ~/.architecture-suite/gcp-icons)")
    for flag in ("dry-run", "confirm-write", "confirm-overwrite"):
        icons.add_argument("--" + flag, action="store_true")
    icons.set_defaults(func=cmd_install_gcp_icons)
    for name in (
        "analyze",
        "render",
        "plan-draft",
        "plan-lint",
        "plan-render",
        "verify",
        "examples",
    ):
        p = commands.add_parser(name)
        if name in {"analyze", "plan-draft"}:
            p.add_argument("--repo", required=True)
            p.add_argument(
                "--classification",
                default="Internal"
                if name == "plan-draft"
                else "Inherited from source repository",
            )
            p.add_argument(
                "--cloud-profile", choices=("none", "aws", "gcp"), default="none"
            )
            for flag, default in (
                ("max-files", 2000),
                ("max-file-bytes", 400000 if name == "plan-draft" else 1000000),
                ("max-total-bytes", 50000000),
            ):
                p.add_argument("--" + flag, type=int, default=default)
            p.add_argument("--timeout", type=float, default=45.0)
        if name in {"render", "verify"}:
            p.add_argument("--model", required=True)
        if name in {"plan-lint", "plan-render"}:
            p.add_argument("--plan", required=True)
            p.add_argument(
                "--gcp-icon-style",
                choices=("auto", "modern", "legacy"),
                default=None,
                help="GCP icon set; overrides gcp_icon_style in the plan",
            )
        if name == "plan-lint":
            p.add_argument("--strict", action="store_true")
            p.set_defaults(func=cmd_plan_lint)
            continue
        if name != "plan-draft":
            p.add_argument(
                "--overview-style", action="append", metavar="STYLE[,STYLE...]"
            )
            if name != "examples":
                p.add_argument("--level", choices=ARTIFACT_LEVELS, default="all")
        if name == "verify":
            p.set_defaults(func=cmd_verify)
            continue
        p.add_argument("--output", required=True)
        if name in {"render", "analyze", "plan-render"}:
            p.add_argument(
                "--format", type=_parse_formats, default=DEFAULT_FORMATS.copy()
            )
        if name == "plan-render":
            p.add_argument("--emit-model", action="store_true")
            p.add_argument("--augmented", action="store_true")
            p.add_argument("--allow-layout-findings", action="store_true")
        for flag in ("dry-run", "confirm-write", "confirm-overwrite"):
            p.add_argument("--" + flag, action="store_true")
        p.set_defaults(
            func=cmd_plan_draft
            if name == "plan-draft"
            else cmd_examples
            if name == "examples"
            else cmd_publish
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except SafetyError as exc:
        print(f"architecture-suite: {exc}", file=sys.stderr)
        return 3
    except (OSError, ValueError, RecursionError) as exc:
        print(f"architecture-suite: error: {exc}", file=sys.stderr)
        return 2
