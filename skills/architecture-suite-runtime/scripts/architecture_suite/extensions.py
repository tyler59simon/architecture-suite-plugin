"""CLI surfaces for opt-in sidecars; legacy C4 contracts remain unchanged."""

import json
from pathlib import Path
from .model import load_model, validate_model
from .safety import (
    canonical_existing_file,
    canonical_output_directory,
    atomic_output_directory,
    require_write_authorization,
    contained_path,
)
from .plan import parse_yaml
from .changes import diff_models, check_rules, markdown_report
from .infrastructure import import_infrastructure, topology_plan
from .draft import render_plan
from .scenarios import validate_scenario, scenario_scene, scenario_mermaid
from .emit import render_scene_svg, render_scene_drawio
from .renderers import render_svg_png
from .explorer import explorer_html
from .inventory import dependency_inventory
from .safety import scan_repository


def _read(path):
    p = canonical_existing_file(Path(path))
    return parse_yaml(p.read_text(encoding="utf-8"))


def _model(path):
    m = load_model(canonical_existing_file(Path(path)))
    # Partial models remain useful: validate only the deepest supplied C4 view.
    order = {"context": 1, "container": 2, "component": 3, "code": 4}
    profile = max(
        (v["type"] for v in m.get("views", []) if v.get("type") in order),
        key=order.get,
        default="context",
    )
    findings = validate_model(m, profile)
    if findings:
        raise ValueError("Invalid model: " + json.dumps(findings[:3]))
    return m


def cmd_extension(args):
    try:
        return _cmd_extension(args)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Malformed extension document: " + type(exc).__name__) from exc


def _cmd_extension(args):
    status = 0
    files = {}
    binary = None
    if args.command == "inventory":
        scan = scan_repository(Path(args.repo))
        report = dependency_inventory(scan.texts)
        report["scan"] = {"truncated": scan.truncated, "gaps": scan.skipped}
        files["dependency-inventory.json"] = report
    elif args.command == "import-infra":
        report = import_infrastructure(
            args.input, _read(args.bindings) if args.bindings else None
        )
        if args.model:
            ids = {
                e["id"]
                for e in _model(args.model)["elements"]
                if e["type"] == "container"
            }
            if not set(report["bindings"].values()) <= ids:
                raise ValueError("Bindings must name existing C4 containers")
        elif report["bindings"]:
            raise ValueError("Bindings require --model")
        files = {
            "topology.json": report,
            "architecture-plan.md": render_plan(topology_plan(report)),
        }
    elif args.command == "diff":
        report = diff_models(
            _model(args.before),
            _model(args.after),
            _read(args.identities) if args.identities else None,
        )
        files = {
            "architecture-diff.json": report,
            "architecture-diff.md": markdown_report(report),
        }
    elif args.command == "check":
        report = check_rules(
            _model(args.model),
            _read(args.rules),
            _read(args.baseline) if args.baseline else None,
        )
        files = {
            "architecture-check.json": report,
            "architecture-check.md": markdown_report(report),
            "baseline.json": {
                "schema_version": "architecture-baseline/v1",
                "fingerprints": report["fingerprints"],
            },
        }
        status = 1 if args.fail_on == "error" and report["new_errors"] else 0
    elif args.command.startswith("scenario-"):
        model = _model(args.model)
        scenario = validate_scenario(_read(args.scenario), model)
        if args.command == "scenario-lint":
            print(json.dumps({"ok": True, "name": scenario["name"]}))
            return 0
        scene = scenario_scene(scenario, model)
        formats = (
            set(args.format.split(","))
            if args.format != "all"
            else {"mermaid", "svg", "drawio", "png"}
        )
        if not formats or formats - {"mermaid", "svg", "drawio", "png"}:
            raise ValueError("Invalid scenario format")
        for fmt in formats:
            name = (
                "scenario."
                + {"mermaid": "mmd", "svg": "svg", "drawio": "drawio", "png": "png"}[
                    fmt
                ]
            )
            files[name] = (
                scenario_mermaid(scenario, model)
                if fmt == "mermaid"
                else render_scene_svg(scene)
                if fmt == "svg"
                else render_scene_drawio(scene)
                if fmt == "drawio"
                else None
            )
        binary = scene
    else:
        model = _model(args.model)
        files = {
            "explorer.html": explorer_html(
                model,
                [_read(p) for p in args.scenario],
                _read(args.diff) if args.diff else None,
            )
        }
    output = canonical_output_directory(Path(args.output))
    summary = {
        "operation": args.command,
        "files": sorted(files),
        "status": "findings" if status else "ok",
    }
    if args.dry_run:
        print(json.dumps(summary))
        return status
    require_write_authorization(output, args.confirm_write, args.confirm_overwrite)
    with atomic_output_directory(output) as stage:
        for name, value in files.items():
            path = contained_path(stage, name)
            if value is None:
                render_svg_png(
                    render_scene_svg(binary), path, binary.width, binary.height
                )
            else:
                path.write_text(
                    value
                    if isinstance(value, str)
                    else json.dumps(value, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
    print(json.dumps(summary))
    return status


def register_commands(commands):
    for name in (
        "inventory",
        "import-infra",
        "scenario-lint",
        "scenario-render",
        "diff",
        "check",
        "explore",
    ):
        p = commands.add_parser(name)
        if name == "inventory":
            p.add_argument("--repo", required=True)
        if name == "import-infra":
            p.add_argument("--input", action="append", required=True)
            p.add_argument("--bindings")
            p.add_argument("--model")
        if name in {"scenario-lint", "scenario-render", "check", "explore"}:
            p.add_argument("--model", required=True)
        if name in {"scenario-lint", "scenario-render"}:
            p.add_argument("--scenario", required=True)
        if name == "scenario-render":
            p.add_argument("--format", default="all")
        if name == "explore":
            p.add_argument("--scenario", action="append", default=[])
            p.add_argument("--diff")
        if name == "diff":
            p.add_argument("--before", required=True)
            p.add_argument("--after", required=True)
            p.add_argument("--identities")
        if name == "check":
            p.add_argument("--rules", required=True)
            p.add_argument("--baseline")
            p.add_argument("--fail-on", choices=("none", "error"), default="none")
        if name != "scenario-lint":
            p.add_argument("--output", required=True)
            for flag in ("dry-run", "confirm-write", "confirm-overwrite"):
                p.add_argument("--" + flag, action="store_true")
        p.set_defaults(func=cmd_extension)
