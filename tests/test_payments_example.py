"""The checked-in PayStream payments example stays valid on both clouds."""

import importlib.util
from pathlib import Path

import pytest

from architecture_suite.model import validate_model
from architecture_suite.plan import compile_plan, lint_plan, parse_plan_document

ROOT = Path(__file__).resolve().parents[1]
PLANS = ROOT / "examples/payments/plans"


def load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_payments_samples", ROOT / "tools/generate_payments_samples.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
def test_checked_in_plan_is_strictly_clean_and_matches_the_generator(cloud):
    text = (PLANS / f"{cloud}-architecture-plan.md").read_text(encoding="utf-8")
    plan = parse_plan_document(text)
    assert plan == load_generator().payments_plan(cloud)  # regenerate if this fails
    assert not lint_plan(plan)  # no errors and no advisories
    model = compile_plan(plan)[0]
    assert not validate_model(model)
    levels = {v["type"] for v in model["views"]}
    assert {"context", "container", "component", "code"} <= levels
    assert model["deployment"]["provider"] == cloud
    services = {e["cloud"]["provider"] for e in model["elements"] if e.get("cloud")}
    assert services == {cloud}


def test_both_clouds_share_one_logical_architecture():
    generator = load_generator()
    aws, gcp = generator.payments_plan("aws"), generator.payments_plan("gcp")
    for key in ("people", "external_systems", "flows"):
        assert aws[key] == gcp[key]
    strip = [
        {k: v for k, v in c.items() if not k.endswith("_service")} for c in aws["containers"]
    ]
    assert strip == [
        {k: v for k, v in c.items() if not k.endswith("_service")} for c in gcp["containers"]
    ]
    rendered = ROOT / "examples/payments"
    for cloud in ("aws", "gcp"):
        for folder in ("01-system-context", "02-containers", "03-components", "04-code",
                       "05-overview", f"06-{cloud}-deployment"):
            assert any((rendered / cloud / folder).glob("*.png")), (cloud, folder)
