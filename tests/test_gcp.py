"""Google Cloud profile: icon catalogue and styles, plan/model, detection, rendering, CLI."""

import re

import pytest
from architecture_suite import aws, renderers
from architecture_suite.analyzer import analyze_repository
from architecture_suite.cli import main
from architecture_suite.draft import render_plan
from architecture_suite.emit import render_scene_svg
from architecture_suite.examples_gcp import (
    DYNAMIC_SEQUENCE,
    ridepulse_model,
    ridepulse_plan,
)
from architecture_suite.gcp_analyzer import detect_gcp
from architecture_suite.model import validate_model
from architecture_suite.overview_layout import (
    build_cloud_scene,
    build_gcp_scene,
)
from architecture_suite.plan import (
    PlanError,
    compile_plan,
    errors,
    lint_plan,
    plan_provider,
)
from architecture_suite.safety import SafetyError
from architecture_suite.style import element_label


def codes(findings):
    return {f.code for f in findings}


def test_both_icon_styles_are_vendored_and_safe():
    entries = aws.catalog("gcp")
    modern = {k for k, v in entries.items() if v["style"] == "modern"}
    legacy = {k for k, v in entries.items() if v["style"] == "legacy"}
    assert len(modern) == 45 and len(legacy) == 216
    assert aws.verify_assets()
    for key in entries:
        data = aws.icon_bytes(key)  # provider inferred from the GCP- prefix
        aws.validate_svg(data)
        assert data == aws.icon_bytes(key, "gcp")
    with pytest.raises(ValueError):
        aws.catalog("azure")
    with pytest.raises(SafetyError):
        aws.icon_bytes("GCP-missing")


def test_resolution_aliases_and_styles():
    assert aws.resolve_service("GKE", "gcp") == "GCP-Google-Kubernetes-Engine"
    assert aws.resolve_service("Cloud Run", "gcp") == "GCP-Cloud-Run"
    assert aws.resolve_service("cloud run", "gcp", "legacy") == "GCP-Legacy-cloud_run"
    assert aws.resolve_service("Spanner", "gcp") == "GCP-Cloud-Spanner"
    # Pub/Sub only exists in the legacy set.
    assert aws.resolve_service("Pub/Sub", "gcp") == "GCP-Legacy-pubsub"
    assert aws.resolve_service("Pub/Sub", "gcp", "modern") is None
    # Exact catalogue keys resolve, but only in a compatible style.
    assert aws.resolve_service("gcp-cloud-run", "gcp") == "GCP-Cloud-Run"
    assert aws.resolve_service("GCP-Cloud-Run", "gcp", "legacy") is None
    assert aws.resolve_service("Compute Engine", "gcp", "modern") == "GCP-Compute-Engine"
    assert aws.resolve_service("nonsense", "gcp") is None
    assert aws.gcp_key("Google Cloud Storage") == "cloudstorage"
    assert aws.normalize_gcp_icon_style(None) == "auto"
    assert aws.normalize_gcp_icon_style("LEGACY") == "legacy"
    with pytest.raises(ValueError):
        aws.normalize_gcp_icon_style("neon")
    assert aws.normalize_cloud_profile("GCP") == "gcp"
    with pytest.raises(ValueError):
        aws.normalize_cloud_profile("azure")


def test_ridepulse_plan_compiles_and_validates():
    plan = ridepulse_plan()
    assert plan_provider(plan) == "gcp"
    assert not errors(lint_plan(plan))
    model = ridepulse_model()
    assert not validate_model(model)
    assert model["deployment"]["provider"] == "gcp"
    services = {
        e["name"]: e["cloud"]["service"] for e in model["elements"] if e.get("cloud")
    }
    assert services["Rider Gateway"] == "GCP-Google-Kubernetes-Engine"
    assert services["Event Bus"] == "GCP-Legacy-pubsub"
    assert "sequenceDiagram" in DYNAMIC_SEQUENCE
    # Legacy-only and modern-only styles pick different icon sets deterministically.
    assert all(
        v.startswith("GCP-Legacy-")
        for v in (
            e["cloud"]["service"]
            for e in ridepulse_model("legacy")["elements"]
            if e.get("cloud")
        )
    )
    modern = ridepulse_model("modern")
    # A modern style without artwork keeps the service and only drops the icon.
    clouds = [e for e in modern["elements"] if e.get("cloud")]
    assert {e["name"] for e in clouds} == set(services)
    for e in clouds:
        assert e["cloud"]["provider"] == "gcp"
        legacy = e["cloud"]["service"].startswith("GCP-Legacy-")
        assert e["cloud"].get("icon", True) is not legacy
    iconless = [e for e in clouds if e["cloud"].get("icon") is False]
    assert iconless and all(element_label(e).icon is None for e in iconless)
    assert not validate_model(modern)


def test_unknown_explicit_provider_is_rejected():
    plan = ridepulse_plan()
    plan["deployment"]["provider"] = "azure"
    assert "unknown-provider" in codes(errors(lint_plan(plan)))
    with pytest.raises(PlanError):
        compile_plan(plan)


def test_provider_inference_and_aws_default():
    plan = ridepulse_plan()
    del plan["deployment"]["provider"]
    assert plan_provider(plan) == "gcp"
    plan["containers"][0]["aws_service"] = "Amazon ECS"
    assert plan_provider(plan) == "aws"
    plan["deployment"]["provider"] = "gcp"
    assert plan_provider(plan) == "gcp"
    assert plan_provider({"system": {}, "containers": []}) == "aws"


def test_lint_findings_for_gcp_fields():
    plan = ridepulse_plan()
    plan["containers"][0]["gcp_service"] = "Made Up Service"
    assert "unknown-gcp-service" in codes(lint_plan(plan))
    with pytest.raises(PlanError):
        compile_plan(plan)
    plan = ridepulse_plan()
    findings = lint_plan(plan, "modern")
    assert "gcp-icon-unavailable" in codes(findings) and not errors(findings)
    plan["gcp_icon_style"] = "neon"
    assert "gcp-icon-style" in codes(lint_plan(plan))
    plan["gcp_icon_style"] = "legacy"
    assert not codes(lint_plan(plan)) & {"gcp-icon-style", "gcp-icon-unavailable"}
    # The explicit argument wins over the plan value.
    assert "gcp-icon-unavailable" in codes(lint_plan(plan, "modern"))


def test_gcp_deployment_hierarchy_and_service_validation():
    model = ridepulse_model()
    model["deployment"]["nodes"].append(
        {
            "id": "bad-zone",
            "type": "zone",
            "name": "Misplaced",
            "parent_id": "example-organization",
        }
    )
    assert "deployment-hierarchy" in {f["code"] for f in validate_model(model)}
    model = ridepulse_model()
    next(e for e in model["elements"] if e.get("cloud"))["cloud"]["service"] = "nope"
    assert "gcp-service" in {f["code"] for f in validate_model(model)}
    model = ridepulse_model()
    next(e for e in model["elements"] if e.get("cloud"))["cloud"]["provider"] = "azure"
    assert "aws-service" in {f["code"] for f in validate_model(model)}


def test_gcp_deployment_rendering():
    model = ridepulse_model()
    specs = dict(renderers.diagram_specs(model, ["executive"]))
    assert "06-gcp-deployment/gcp-deployment" in specs
    scene = build_gcp_scene(model)
    assert scene.title == "RidePulse — Google Cloud deployment"
    assert build_cloud_scene(model).as_dict() == scene.as_dict()
    assert any(b.element.get("type") == "project" for b in scene.boxes if b.element)
    svg = renderers.render_gcp_deployment_svg(model)
    assert svg == render_scene_svg(scene)
    assert svg.count("data:image/svg+xml;base64,") >= 8
    assert not re.search(r'href="(?!data:)', svg)
    drawio = renderers.render_gcp_deployment_drawio(model)
    assert "shape=image" in drawio and "Rider Gateway" in drawio
    assert "Rider Gateway" in renderers.render_gcp_deployment_mermaid(model)
    vsdx = renderers.render_gcp_deployment_vsdx(model)
    assert vsdx == renderers.scene_vsdx(scene)
    # AWS sample keeps its original folder name.
    from architecture_suite.examples import example_model

    assert (
        "06-aws-deployment/aws-deployment"
        in dict(renderers.diagram_specs(example_model(), ["executive"]))
    )


def test_detect_gcp_and_reverse_engineering(tmp_path):
    files = {
        "infra/main.tf": 'resource "google_pubsub_topic" "t" {}\nresource "google_storage_bucket" "b" {}\n',
        "app/main.py": "from google.cloud import bigquery\nbigquery.Client()\n",
        "other.txt": "nothing",
    }
    signals = detect_gcp(files)
    assert {s["service"] for s in signals} == {
        "GCP-Legacy-pubsub",
        "GCP-Cloud-Storage",
        "GCP-BigQuery",
    }
    assert {s["kind"] for s in signals} == {"infrastructure", "sdk"}
    (tmp_path / "infra").mkdir()
    (tmp_path / "infra/main.tf").write_text(files["infra/main.tf"])
    (tmp_path / "app").mkdir()
    (tmp_path / "app/main.py").write_text(files["app/main.py"])
    (tmp_path / "app/pyproject.toml").write_text('[project]\nname="app"\n')
    model, _ = analyze_repository(tmp_path, cloud_profile="gcp", profile="container")
    assert any(
        e.get("cloud", {}).get("provider") == "gcp" for e in model["elements"]
    )
    assert any("GCP project, region" in g for g in model["gaps"])
    assert any("SDK usage" in g for g in model["gaps"])
    assert "deployment" not in model


def test_cli_cloud_profile_and_icon_style(tmp_path, capsys):
    plan_path = tmp_path / "plan.md"
    plan_path.write_text(render_plan(ridepulse_plan()), encoding="utf-8")
    assert main(["plan-lint", "--plan", str(plan_path), "--strict"]) == 0
    assert (
        main(["plan-lint", "--plan", str(plan_path), "--gcp-icon-style", "modern"])
        == 0
    )
    assert (
        main(
            ["plan-lint", "--plan", str(plan_path), "--gcp-icon-style", "modern", "--strict"]
        )
        == 1
    )
    capsys.readouterr()
    out = tmp_path / "out"
    assert (
        main(
            [
                "plan-render", "--plan", str(plan_path), "--output", str(out),
                "--level", "all", "--overview-style", "executive",
                "--format", "mermaid,svg", "--gcp-icon-style", "legacy",
                "--confirm-write",
            ]
        )
        == 0
    )
    svg = (out / "06-gcp-deployment/gcp-deployment.svg").read_text(encoding="utf-8")
    assert "Google Cloud" in svg and "data:image/svg+xml;base64," in svg
    assert (out / "06-gcp-deployment/gcp-deployment.mmd").exists()


def test_role_shapes_across_exporters():
    from architecture_suite.examples import example_model
    from architecture_suite.style import Label, box_style, element_visual

    model = ridepulse_model()
    kinds = {
        e["name"]: element_visual(e).kind
        for e in model["elements"]
        if element_visual(e)
    }
    assert kinds["Trip Store"] == "database" and kinds["Location Archive"] == "storage"
    assert kinds["Event Bus"] == "messaging" and kinds["ETA Model"] == "ml"
    assert "Dispatch Service" not in kinds  # compute keeps the C4 rectangle
    assert element_visual({"type": "code", "cloud": {"service": "x"}}) is None
    assert element_visual({"type": "container", "name": "Plain"}) is None
    scene = build_gcp_scene(model)
    svg = render_scene_svg(scene)
    assert svg.count("<ellipse") == 5  # Trip Store, Location Cache, Fleet Time Series, Telemetry Lake, Location Archive
    assert 'rx="28"' in svg  # messaging pill
    mermaid = renderers.render_gcp_deployment_mermaid(model)
    assert "[(" in mermaid and "([" in mermaid and "style n" in mermaid
    drawio = renderers.render_gcp_deployment_drawio(model)
    assert "shape=cylinder3" in drawio and "arcSize=25" in drawio
    # Cylinder labels reserve room for the cap, and frames get boundary colours.
    cylinder = next(b for b in scene.boxes if box_style(b)[0] == "cylinder")
    assert cylinder.label.top_pad > 0 and isinstance(cylinder.label, Label)
    project = next(
        b for b in scene.boxes if b.element and b.element.get("type") == "project"
    )
    assert box_style(project)[1] == "#4285f4"
    # AWS models use the same role shapes (DynamoDB -> cylinder, SQS -> pill).
    aws_svg = renderers.render_aws_deployment_svg(example_model())
    assert "<ellipse" in aws_svg and 'rx="28"' in aws_svg
