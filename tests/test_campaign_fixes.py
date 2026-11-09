"""Regressions found by rendering a campaign of fictional systems (plans, IaC, scenarios)."""

import io
import json
from copy import deepcopy

from PIL import ImageFont

from architecture_suite import cli
from architecture_suite.emit import render_scene_svg
from architecture_suite.infrastructure import import_infrastructure
from architecture_suite.model import SLUG_MAX, slugify, validate_model
from architecture_suite.overview_layout import build_overview_scene
from architecture_suite.plan import compile_plan, lint_plan
from architecture_suite.renderers import _quoted, _scene, render_mermaid
from architecture_suite.report import render_architecture_report
from architecture_suite.scenarios import scenario_mermaid
from architecture_suite.style import _font


def _codes(findings):
    return {f.code for f in findings}


def test_text_measurement_uses_one_layout_engine_on_every_host():
    # Raqm (picked automatically where libraqm is installed, e.g. Linux) wraps differently.
    assert _font(13).layout_engine == ImageFont.Layout.BASIC


def test_mermaid_escapes_hash_and_scenario_semicolons(model):
    # User text that looks like an entity code stays literal.
    assert _quoted("C# #10; done") == '"C#35; #35;10; done"'
    api = next(e for e in model["elements"] if e["type"] == "container")
    person = next(e for e in model["elements"] if e["type"] == "person")
    scenario = {
        "schema_version": "architecture-scenario/v1",
        "name": "Semicolons",
        "participants": [person["id"], api["id"]],
        "steps": [
            {"from": person["id"], "to": api["id"], "description": "a; b & <c>"},
            {
                "type": "opt",
                "condition": "x; y",
                "steps": [{"from": api["id"], "to": person["id"], "description": "ok"}],
            },
        ],
    }
    source = scenario_mermaid(scenario, model)
    assert ": a#59; b #38; #60;c#62;" in source
    assert "opt x#59; y" in source
    # No bare semicolon may end a statement early; entity codes keep their own.
    for line in source.splitlines()[1:]:
        assert ";" not in line.replace("#59;", "").replace("#38;", "").replace(
            "#60;", ""
        ).replace("#62;", "")


def test_json_output_survives_a_non_utf8_console(monkeypatch):
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    monkeypatch.setattr("sys.stdout", stream)
    cli._json_print({"name": "東京 Gateway"})
    stream.flush()
    assert json.loads(raw.getvalue().decode("cp1252")) == {"name": "東京 Gateway"}


def test_cloudformation_yaml_short_tags_and_documents(tmp_path):
    template = """# rendered by a tool
---
Resources:
  Topic:
    Type: AWS::SNS::Topic
  Queue:
    Type: AWS::SQS::Queue
    Properties:
      Tags: [!Ref Topic]   # flow sequence with a comment
      Body: !Base64 hello
      Script: !Sub |
        echo ${AWS::Region}
      Same: !Equals [a, b]
  Alarm:
    Type: AWS::CloudWatch::Alarm
    Properties:
      AlarmActions:
        - !Ref Topic
--- # trailing empty document
"""
    path = tmp_path / "stack.yaml"
    path.write_text(template, encoding="utf-8")
    topology = import_infrastructure([path])
    edges = {(e["source_id"], e["destination_id"]) for e in topology["relationships"]}
    assert edges == {
        ("input-0-queue", "input-0-topic"),
        ("input-0-alarm", "input-0-topic"),
    }
    path.write_text("a: &x 1\nb: *x\n", encoding="utf-8")
    try:
        import_infrastructure([path])
    except ValueError:
        pass
    else:
        raise AssertionError("aliases must stay unsupported")


def test_terraform_placeholders_are_not_identities(tmp_path):
    def resource(address, kind, values, sensitive=None):
        item = {"address": address, "type": kind, "values": values}
        if sensitive:
            item["sensitive_values"] = sensitive
        return item

    doc = {
        "planned_values": {
            "root_module": {
                "resources": [
                    resource("aws_s3_bucket.a", "aws_s3_bucket", {"bucket": "a"}),
                    resource("aws_sqs_queue.b", "aws_sqs_queue", {"name": "b"}),
                    resource(
                        "aws_db_instance.c",
                        "aws_db_instance",
                        {"password": "AUDIT-SYNTHETIC", "name": "c"},
                        {"password": True},
                    ),
                ]
            }
        },
        "resource_changes": [
            {"address": a, "change": {"after_unknown": {"id": True, "arn": True}}}
            for a in ("aws_s3_bucket.a", "aws_sqs_queue.b", "aws_db_instance.c")
        ],
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(doc))
    topology = import_infrastructure([path])
    assert topology["relationships"] == []
    messages = [f["message"] for f in topology["findings"]]
    assert "Sensitive values masked: password" in messages
    assert "AUDIT-SYNTHETIC" not in json.dumps(topology)


def test_compose_and_kubernetes_import_details(tmp_path):
    path = tmp_path / "compose.yaml"
    path.write_text(
        "services:\n"
        "  api:\n    depends_on: [db, ghost]\n    networks: [private, nowhere]\n"
        "  web:\n    depends_on:\n      api:\n        condition: service_started\n"
        "  db: {}\n"
        "networks:\n  private: {}\n",
        encoding="utf-8",
    )
    topology = import_infrastructure([path])
    edges = sorted(
        (e["source_id"][8:], e["destination_id"][8:], e["kind"])
        for e in topology["relationships"]
    )
    assert edges == [
        ("api", "db", "depends-on"),
        ("api", "networks-private", "network-membership"),
        ("web", "api", "depends-on"),
    ]
    assert any(
        f["message"] == "Refers to undeclared services or networks: ghost, networks/nowhere"
        for f in topology["findings"]
    )
    path = tmp_path / "k8s.yaml"
    config = "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: {}\n"
    path.write_text(
        config.format("app.config") + "---\n" + config.format("app-config"),
        encoding="utf-8",
    )
    ids = [r["id"] for r in import_infrastructure([path])["resources"]]
    assert ids == ["input-0-default-configmap-app-config", "input-0-default-configmap-app-config-2"]
    path.write_text(config.format("same") + "---\n" + config.format("same"), encoding="utf-8")
    try:
        import_infrastructure([path])
    except ValueError as exc:
        assert "Duplicate infrastructure resource" in str(exc)
    else:
        raise AssertionError("a repeated declaration must stay an error")


def test_slugify_keeps_non_latin_and_long_names_distinct():
    assert slugify("Zürich Ops") == "z-rich-ops"  # Latin text maps exactly as before
    tokyo, osaka = slugify("東京 Gateway"), slugify("大阪 Gateway")
    assert tokyo != osaka and tokyo.startswith("gateway-")
    assert slugify("東京") != slugify("大阪") and slugify("🚀") != slugify("🛰")
    long = slugify("Very long component name " * 12)
    assert len(long) <= SLUG_MAX + 9 and long != slugify("Very long component name " * 13)


def test_lint_names_offending_keys_and_endpoints(plan):
    bad = deepcopy(plan)
    bad["extra"] = {}
    bad["flows"][0]["weight"] = 3
    bad["flows"][0]["to"] = "RequestHandlr"
    messages = {f.code: f.message for f in lint_plan(bad)}
    assert messages["unknown-section"] == "Unknown plan section: extra"
    assert messages["unknown-field"] == "Unknown flow field: weight"
    assert messages["unknown-endpoint"] == (
        "Unknown flow to: 'RequestHandlr' (did you mean 'RequestHandler'?)"
    )


def test_deployment_node_types_follow_the_provider(plan):
    gcp_nodes = deepcopy(plan)
    gcp_nodes["deployment"]["provider"] = "aws"
    gcp_nodes["deployment"]["nodes"][0]["children"].append(
        {"name": "Shop Project", "type": "project"}
    )
    findings = lint_plan(gcp_nodes)
    assert any(
        f.code == "deployment-node" and "project nodes are not part of a aws" in f.message
        for f in findings
    )
    mixed = deepcopy(plan)
    mixed["deployment"]["provider"] = "aws"
    mixed["containers"][0]["gcp_service"] = "Cloud Run"
    assert "provider-service" in _codes(lint_plan(mixed))
    duplicated = deepcopy(plan)
    duplicated["deployment"]["placements"].append({"element": "API", "node": "us-east-1"})
    duplicated["deployment"]["placements"].append({"element": "Customer", "node": "us-east-1"})
    where = {f.where for f in lint_plan(duplicated) if f.code == "deployment-placement"}
    assert where == {"api", "customer -> us-east-1"}
    model = compile_plan(plan)[0]
    model["deployment"]["nodes"].append(dict(model["deployment"]["nodes"][1]))
    assert any(
        f["code"] == "deployment-id" and f["path"] == model["deployment"]["nodes"][1]["id"]
        for f in validate_model(model)
    )


def test_flow_order_numbers_the_arrow(plan):
    ordered = deepcopy(plan)
    ordered["flows"][0]["order"] = 2
    model = compile_plan(ordered)[0]
    assert any(r["description"].startswith("2. Submits request") for r in model["relationships"])


def test_frame_titles_draw_over_edges_and_mermaid_keeps_direction(model):
    view = next(v for v in model["views"] if v["type"] == "container")
    scene = _scene(model, view)
    svg = render_scene_svg(scene)
    frame = next(b for b in scene.boxes if b.role == "frame")
    title = svg.index(f">{frame.label.lines[0].text}</text>")
    assert svg.rindex("<polyline") < title
    assert 'paint-order="stroke"' in svg
    assert "flowchart LR" in render_mermaid(model, view)
    down = deepcopy(model)
    for v in down["views"]:
        v["direction"] = "down"
    assert "flowchart TB" in render_mermaid(down, next(v for v in down["views"] if v["type"] == "container"))


def test_small_multiples_pack_panels_into_rows(model):
    scene = build_overview_scene(model, "small-multiples")
    panels = [b for b in scene.boxes if b.role == "panel-title"]
    assert len({b.y for b in panels}) < len(panels)  # several panels share a row
    assert scene.width <= max(5600, max(b.x + b.width + 96 for b in panels))


def test_report_evidence_lines_omit_empty_parts(model):
    report = render_architecture_report(
        {**model, "evidence": [{"id": "ev-1", "reference": "brief"}]}
    )
    assert "- ev-1: brief\n" in report + "\n"
