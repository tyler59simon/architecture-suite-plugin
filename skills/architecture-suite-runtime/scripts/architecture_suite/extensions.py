"""CLI surfaces for opt-in sidecars; legacy C4 contracts remain unchanged."""

import argparse
import json
from pathlib import Path
from .model import format_findings, load_model, validate_model
from .safety import (
    OUTPUT_MANIFEST,
    SafetyError,
    canonical_existing_directory,
    canonical_existing_file,
    canonical_output_directory,
    atomic_output_directory,
    require_write_authorization,
    contained_path,
    ownership_changes,
)
from .plan import parse_yaml, render_plan
from .changes import diff_models, check_rules, markdown_report
from .infrastructure import import_infrastructure, topology_plan
from .scenarios import (
    validate_scenario,
    scenario_scene,
    scenario_mermaid,
    scenario_plantuml,
)
from .emit import render_scene_svg, render_scene_drawio
from .renderers import EXTENSIONS, render_svg_png, scene_vsdx
from .explorer import explorer_html
from .inventory import dependency_inventory
from .safety import scan_repository


class HelpFormatter(argparse.ArgumentDefaultsHelpFormatter):
    """Show defaults, except the noise of None, False and the default format set."""

    def _get_help_string(self, action):
        if action.default in (None, False) or isinstance(action.default, set):
            return action.help
        return super()._get_help_string(action)


def _read(path, label=""):
    p = canonical_existing_file(Path(path), label)
    return parse_yaml(p.read_text(encoding="utf-8-sig"))  # tolerate a BOM


def _document(path, version, fields, label=""):
    # Companion documents follow their JSON schemas: the version and field types are required.
    doc = _read(path, label)
    if (
        not isinstance(doc, dict)
        or doc.get("schema_version") != version
        or not all(isinstance(doc.get(k), t) for k, t in fields.items())
    ):
        raise ValueError(
            f"Expected {version} with " + ", ".join(sorted(fields)) + ": " + str(path)
        )
    return doc


def _model(path, label="--model"):
    m = load_model(canonical_existing_file(Path(path), label), label)
    # Partial models remain useful: validate only the deepest supplied C4 view.
    order = {"context": 1, "container": 2, "component": 3, "code": 4}
    profile = max(
        (v["type"] for v in m.get("views", []) if v.get("type") in order),
        key=order.get,
        default="context",
    )
    findings = validate_model(m, profile)
    if findings:
        raise ValueError("Invalid model:\n" + format_findings(findings, 3))
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
        repo = canonical_existing_directory(Path(args.repo), "--repo")
        target = canonical_output_directory(Path(args.output))
        if target.is_relative_to(repo) or repo.is_relative_to(target):
            raise SafetyError("Inventory output must be outside the analyzed repository")
        scan = scan_repository(repo)
        report = dependency_inventory(scan.texts)
        report["scan"] = {"truncated": scan.truncated, "gaps": scan.skipped}
        files["dependency-inventory.json"] = report
    elif args.command == "import-infra":
        report = import_infrastructure(
            args.input, _read(args.bindings, "--bindings") if args.bindings else None
        )
        if args.model:
            ids = {
                e["id"]
                for e in _model(args.model, "--model")["elements"]
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
            _model(args.before, "--before"),
            _model(args.after, "--after"),
            _read(args.identities, "--identities") if args.identities else None,
        )
        files = {
            "architecture-diff.json": report,
            "architecture-diff.md": markdown_report(report),
        }
    elif args.command == "check":
        report = check_rules(
            _model(args.model, "--model"),
            _document(args.rules, "architecture-rules/v1", {"rules": list}, "--rules"),
            _document(
                args.baseline,
                "architecture-baseline/v1",
                {"fingerprints": list},
                "--baseline",
            )
            if args.baseline
            else None,
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
        model = _model(args.model, "--model")
        scenario = validate_scenario(_read(args.scenario, "--scenario"), model)
        if args.command == "scenario-lint":
            print(json.dumps({"ok": True, "name": scenario["name"]}))
            return 0
        scene = scenario_scene(scenario, model)
        formats = (
            {x.strip().lower() for x in args.format.split(",") if x.strip()}
            if args.format.strip().lower() != "all"
            else set(EXTENSIONS)
        )
        if not formats or formats - set(EXTENSIONS):
            raise ValueError(
                "Invalid scenario format: use all or " + ",".join(sorted(EXTENSIONS))
            )
        for fmt in formats:
            name = "scenario." + EXTENSIONS[fmt]
            files[name] = (
                scenario_mermaid(scenario, model)
                if fmt == "mermaid"
                else scenario_plantuml(scenario, model)
                if fmt == "plantuml"
                else render_scene_svg(scene)
                if fmt == "svg"
                else render_scene_drawio(scene)
                if fmt == "drawio"
                else scene_vsdx(scene)
                if fmt == "visio"
                else None
            )
        binary = scene
    else:
        model = _model(args.model, "--model")
        files = {
            "explorer.html": explorer_html(
                model,
                [_read(p, "--scenario") for p in args.scenario],
                _document(
                    args.diff,
                    "architecture-diff/v1",
                    {"changes": list, "changed": bool},
                    "--diff",
                )
                if args.diff
                else None,
            )
        }
    output = canonical_output_directory(Path(args.output))
    changes = ownership_changes(output, args.command, list(files))
    summary = {
        "operation": args.command,
        "files": sorted([*files, OUTPUT_MANIFEST]),
        "status": "findings" if status else "ok",
        "conflicts": changes["conflicts"],
        "overwrites_edited": changes["overwrites_edited"],
    }
    if args.dry_run:
        print(json.dumps({**summary, "would_remove": changes["remove"]}))
        return status
    require_write_authorization(output, args.confirm_write, args.confirm_overwrite)
    summary["removed"] = changes["remove"]
    with atomic_output_directory(
        output, owner=args.command, command=args.command, files=list(files)
    ) as stage:
        for name, value in files.items():
            path = contained_path(stage, name)
            if value is None:
                render_svg_png(
                    render_scene_svg(binary), path, binary.width, binary.height
                )
            elif isinstance(value, bytes):
                path.write_bytes(value)
            else:
                path.write_text(
                    value
                    if isinstance(value, str)
                    else json.dumps(value, indent=2, ensure_ascii=False),
                    encoding="utf-8", newline="\n",
                )
    print(json.dumps(summary))
    return status


def register_commands(commands):
    model_help = "architecture-model.json from plan-render --emit-model or analyze"
    for name, summary in (
        ("inventory", "list dependencies found in a repository"),
        ("import-infra", "import Terraform, CloudFormation/CDK, Kubernetes or Compose files into a topology and plan"),
        ("scenario-lint", "check an architecture-scenario/v1 file against a model"),
        ("scenario-render", "render a request-flow (sequence) diagram from a scenario"),
        ("diff", "compare two models and report structural changes"),
        ("check", "check a model against architecture-rules/v1"),
        ("explore", "build the read-only offline HTML explorer"),
    ):
        p = commands.add_parser(
            name,
            help=summary,
            description=summary,
            formatter_class=HelpFormatter,
        )
        if name == "inventory":
            p.add_argument(
                "--repo", required=True, help="repository folder to scan (read-only)"
            )
        if name == "import-infra":
            p.add_argument(
                "--input",
                action="append",
                required=True,
                help="infrastructure file; repeat for several",
            )
            p.add_argument("--bindings", help="JSON mapping of resource ids to container ids")
            p.add_argument("--model", help="model whose containers --bindings refers to")
        if name in {"scenario-lint", "scenario-render", "check", "explore"}:
            p.add_argument("--model", required=True, help=model_help)
        if name in {"scenario-lint", "scenario-render"}:
            p.add_argument(
                "--scenario", required=True, help="architecture-scenario/v1 file (JSON or YAML)"
            )
        if name == "scenario-render":
            p.add_argument(
                "--format",
                default="all",
                help="output formats, case-insensitive: all or a comma-separated list of "
                + ",".join(sorted(EXTENSIONS)),
            )
        if name == "explore":
            p.add_argument(
                "--scenario",
                action="append",
                default=[],
                help="scenario file to include; repeat for several",
            )
            p.add_argument("--diff", help="architecture-diff.json from the diff command")
        if name == "diff":
            p.add_argument("--before", required=True, help="model before the change")
            p.add_argument("--after", required=True, help="model after the change")
            p.add_argument(
                "--identities", help="JSON mapping of old element ids to new ids"
            )
        if name == "check":
            p.add_argument("--rules", required=True, help="architecture-rules/v1 file")
            p.add_argument(
                "--baseline", help="baseline.json from a previous check (accepted findings)"
            )
            p.add_argument(
                "--fail-on",
                choices=("none", "error"),
                default="none",
                help="exit 1 when there are new findings of this severity",
            )
        if name != "scenario-lint":
            p.add_argument("--output", required=True, help="dedicated output folder")
            p.add_argument(
                "--dry-run", action="store_true", help="show what would be written; write nothing"
            )
            p.add_argument(
                "--confirm-write", action="store_true", help="authorize writing (required to write)"
            )
            p.add_argument(
                "--confirm-overwrite",
                action="store_true",
                help="allow writing into a folder that already has files",
            )
        p.set_defaults(func=cmd_extension)
