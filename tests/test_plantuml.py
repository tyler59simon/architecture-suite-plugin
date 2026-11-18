"""C4-PlantUML text output for diagrams and scenarios."""

import json
import re
from copy import deepcopy

import pytest

from architecture_suite import renderers
from architecture_suite.cli import main
from architecture_suite.plan import compile_plan
from architecture_suite.scenarios import scenario_plantuml


def _view(model, kind):
    return next(v for v in model["views"] if v["type"] == kind)


def test_container_view_uses_c4_macros_and_is_deterministic(model):
    view = _view(model, "container")
    text = renderers.render_plantuml(model, view)
    assert text == renderers.render_plantuml(model, view)  # byte-identical across runs
    lines = text.splitlines()
    assert lines[0] == "@startuml" and lines[-1] == "@enduml"
    assert "!include <C4/C4_Container>" in lines and "SHOW_LEGEND()" in lines
    assert re.search(r"^Person\(n\d+, ", text, re.M)
    assert re.search(r"^System_Boundary\(n\d+, .*\) \{$", text, re.M)
    assert re.search(r"^  Container(Db|Queue)?\(n\d+, ", text, re.M)
    assert re.search(r"^Rel\(n\d+, n\d+, ", text, re.M)
    assert "AddElementTag" not in text  # no claims, no claim tag


def test_each_view_type_includes_the_matching_library(model):
    includes = {
        "context": "C4_Container",
        "component": "C4_Component",
        "code": "C4_Component",
    }
    for kind, library in includes.items():
        assert f"!include <C4/{library}>" in renderers.render_plantuml(model, _view(model, kind))
    overview = renderers.render_plantuml(model, {"type": "overview", "style": "small-multiples"})
    assert "!include <C4/C4_Component>" in overview
    assert re.search(r'^rectangle ".+" as panel_\d+ \{$', overview, re.M)  # panels
    deployment = renderers.render_plantuml(model, {"type": "deployment"})
    assert "!include <C4/C4_Deployment>" in deployment
    assert re.search(r"^Deployment_Node\(n\d+, ", deployment, re.M)


@pytest.mark.browser
def test_external_systems_direction_and_escaping(model):
    model = deepcopy(model)
    view = _view(model, "context")
    system = next(e for e in model["elements"] if e["id"] in view["element_ids"]
                  and e["type"] == "software_system")
    system["external"] = True
    system["name"] = 'Say "hi" <b>now</b> C:\\path'
    system["description"] = "first\nsecond %date() $var"
    text = renderers.render_plantuml(model, view)
    # The preprocessor would otherwise run %date() and expand $var.
    assert "%date()" not in text and "$var" not in text
    assert "<U+0025>date() <U+0024>var" in text
    assert "LAYOUT_LEFT_RIGHT()" in text
    assert (
        'System_Ext(n' in text
        and '"Say <U+0022>hi<U+0022> <U+003C>b<U+003E>now<U+003C>/b<U+003E> C:<U+005C>path"'
        in text
    )
    assert '"first\\nsecond <U+0025>date() <U+0024>var"' in text
    view["direction"] = "down"
    assert "LAYOUT_TOP_DOWN()" in renderers.render_plantuml(model, view)


@pytest.mark.browser
def test_plantuml_redacts_like_every_other_format(model):
    """Names, descriptions and members pass through safe_text, as in Mermaid, SVG and Draw.io."""
    model = deepcopy(model)
    view = _view(model, "container")
    container = next(e for e in model["elements"] if e["id"] in view["element_ids"]
                     and e["type"] == "container")
    container["description"] = "postgres://app:hunter2@db/orders and token=abcd1234\x0b\x08"
    text = renderers.render_plantuml(model, view)
    assert "hunter2" not in text and "abcd1234" not in text and "[REDACTED]" in text
    assert "\x0b" not in text and "\x08" not in text


@pytest.mark.browser
def test_claims_get_a_dashed_tag(plan):
    claimed = deepcopy(plan)
    claimed["containers"][2]["status"] = "proposed"
    target = claimed["containers"][2]["name"]
    index = next(i for i, f in enumerate(claimed["flows"]) if target in (f["from"], f["to"]))
    claimed["flows"][index]["status"] = "inferred"
    model, _ = compile_plan(claimed)
    text = renderers.render_plantuml(model, _view(model, "container"))
    assert 'AddElementTag("claim", $borderStyle=DashedLine()' in text
    assert 'AddRelTag("claim", $lineStyle=DashedLine()' in text
    assert re.search(r'^  Container\w*\(n\d+, ".*«proposed»", \$tags="claim"\)$', text, re.M)
    assert re.search(r'^Rel\(n\d+, n\d+, ".*", \$tags="claim"\)$', text, re.M)


def test_cli_publishes_plantuml_on_request(inputs, tmp_path, capsys):
    output = tmp_path / "out"
    argv = ["render", "--model", str(inputs[0]), "--output", str(output)]
    argv += ["--format", "plantuml", "--level", "container", "--confirm-write"]
    assert main(argv) == 0
    capsys.readouterr()
    diagrams = sorted(p.name for p in output.glob("0*/*") if p.is_file())
    assert diagrams == ["containers.puml"]
    assert (output / "02-containers/containers.puml").read_text(encoding="utf-8").startswith(
        "@startuml"
    )
    default = ["render", "--model", str(inputs[0]), "--output", str(tmp_path / "default")]
    assert main(default + ["--level", "container", "--dry-run"]) == 0
    files = json.loads(capsys.readouterr().out)["files"]
    assert not any(f.endswith(".puml") for f in files)


def test_scenario_render_plantuml(model, inputs, tmp_path, capsys):
    scenario = {
        "schema_version": "architecture-scenario/v1",
        "name": "Order submission",
        "participants": ["customer", "api"],
        "steps": [
            {"from": "customer", "to": "api", "description": 'Submit "order"'},
            {
                "type": "alt",
                "condition": "valid",
                "steps": [{"from": "api", "to": "customer", "type": "response",
                           "description": "Accepted"}],
                "branches": [{"condition": "invalid", "steps": [
                    {"from": "api", "to": "customer", "type": "response",
                     "description": "Rejected"}]}],
            },
            {
                "type": "par",
                "condition": "notify",
                "steps": [{"from": "api", "to": "customer", "description": "Email"}],
                "branches": [{"condition": "also", "steps": [
                    {"from": "api", "to": "customer", "description": "Text"}]}],
            },
        ],
    }
    text = scenario_plantuml(scenario, model)
    assert text.splitlines() == [
        "@startuml",
        f'participant "{next(e["name"] for e in model["elements"] if e["id"] == "customer")}" as p0',
        f'participant "{next(e["name"] for e in model["elements"] if e["id"] == "api")}" as p1',
        "p0 -> p1: Submit <U+0022>order<U+0022>",
        "alt valid",
        "  p1 --> p0: Accepted",
        "else invalid",
        "  p1 --> p0: Rejected",
        "end",
        "par notify",
        "  p1 -> p0: Email",
        "else also",
        "  p1 -> p0: Text",
        "end",
        "@enduml",
    ]
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(scenario), encoding="utf-8")
    output = tmp_path / "scenario"
    argv = ["scenario-render", "--model", str(inputs[0]), "--scenario", str(path)]
    assert main(argv + ["--output", str(output), "--format", "plantuml", "--confirm-write"]) == 0
    assert json.loads(capsys.readouterr().out)["files"] == [
        ".architecture-suite-manifest.json",
        "scenario.puml",
    ]
    assert (output / "scenario.puml").read_text(encoding="utf-8") == text
    # A space after the comma is accepted, as in the C4 commands.
    spaced = tmp_path / "spaced"
    assert main(argv + ["--output", str(spaced), "--format", "plantuml, mermaid", "--dry-run"]) == 0
    assert "scenario.mmd" in json.loads(capsys.readouterr().out)["files"]
