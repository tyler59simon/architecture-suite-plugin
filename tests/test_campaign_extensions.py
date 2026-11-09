import json
from copy import deepcopy
import pytest
from architecture_suite.cli import main
from architecture_suite.changes import diff_models, check_rules
from architecture_suite.scenarios import scenario_scene
from architecture_suite.emit import render_scene_svg, render_scene_drawio

RULES = {
    "schema_version": "architecture-rules/v1",
    "rules": [
        {"id": "no-payments", "effect": "deny", "destination": {"ids": ["payment-provider"]}}
    ],
}


def message(source, target, text="Send request", kind="message"):
    return {"type": kind, "from": source, "to": target, "description": text}


@pytest.fixture
def nested():
    long = "A long message description that wraps over several lines " * 3
    return {
        "schema_version": "architecture-scenario/v1",
        "name": "Nested",
        "participants": ["customer", "api", "order-queue"],
        "steps": [
            message("customer", "api"),
            {
                "type": "alt",
                "condition": "accepted",
                "steps": [
                    message("api", "order-queue"),
                    {
                        "type": "loop",
                        "condition": "retry",
                        "steps": [
                            {
                                "type": "opt",
                                "condition": "slow",
                                "steps": [message("api", "api", "Self call")],
                            }
                        ],
                    },
                ],
                "branches": [
                    {"condition": "rejected", "steps": [message("api", "customer", long, "response")]}
                ],
            },
            {
                "type": "par",
                "condition": "fan out",
                "steps": [message("api", "order-queue")],
                "branches": [{"condition": "audit", "steps": [message("api", "customer", long)]}],
            },
            message("api", "customer", "Done", "response"),
        ],
    }


def _span(box):
    return box.y, box.y + box.height


def test_scenario_frames_have_clear_geometry(model, nested):
    scene = scenario_scene(nested, model)
    frames = {b.id: b for b in scene.boxes if b.role == "frame"}
    branches = [b for b in scene.boxes if b.role == "panel-title"]
    dividers = [e for e in scene.edges if e.id.startswith("divider-")]
    messages = [e for e in scene.edges if e.label]
    assert len(frames) == 4 and len(branches) == len(dividers) == 2
    borders = [y for f in frames.values() for y in _span(f)] + [
        e.points[0][1] for e in dividers
    ]
    for edge in messages:
        top, bottom = _span(edge.label)
        for y in borders:
            # No frame border or divider touches a message arrow or crosses its label.
            assert all(abs(y - py) >= 10 for _, py in edge.points)
            assert not top - 10 <= y <= bottom + 10
        for branch in branches:
            assert bottom < branch.y or top > branch.y + branch.height
    for divider in dividers:
        frame = frames[divider.source_id]
        assert frame.y < divider.points[0][1] < frame.y + frame.height
        assert divider.points == [(frame.x, divider.points[0][1]), (frame.x + frame.width, divider.points[0][1])]
    # Nested frames are inset on every side; sibling frames never share a border.
    for frame in frames.values():
        parent = frames.get(frame.parent_id)
        if parent:
            assert parent.x < frame.x and frame.x + frame.width < parent.x + parent.width
            assert parent.y < frame.y and frame.y + frame.height < parent.y + parent.height
    alt, par = (b for b in frames.values() if b.parent_id is None)
    assert par.y - (alt.y + alt.height) >= 20
    last = messages[-1]
    assert last.label.y - (par.y + par.height) >= 20
    assert scene.key_y > max(y for e in scene.edges for _, y in e.points)
    again = scenario_scene(nested, model)
    assert again.as_dict() == scene.as_dict()
    assert render_scene_svg(again) == render_scene_svg(scene)
    assert render_scene_drawio(again) == render_scene_drawio(scene)


def test_baseline_and_rules_are_validated(model, tmp_path):
    result = check_rules(model, RULES)
    baseline = {"schema_version": "architecture-baseline/v1", "fingerprints": result["fingerprints"]}
    assert check_rules(model, RULES, baseline)["new_errors"] == 0
    for bad in (
        {"schema_version": "architecture-baseline/v9", "fingerprints": "abc"},
        {"schema_version": "architecture-baseline/v1", "fingerprints": "abc"},
        {"schema_version": "architecture-baseline/v1", "fingerprints": [1]},
        {"schema_version": "architecture-baseline/v9", "fingerprints": []},
        [],
    ):
        with pytest.raises(ValueError):
            check_rules(model, RULES, bad)
    model_file, rules_file, baseline_file = (tmp_path / n for n in ("m.json", "r.json", "b.json"))
    model_file.write_text(json.dumps(model))
    command = ["check", "--model", str(model_file), "--rules", str(rules_file)]
    command += ["--output", str(tmp_path / "out"), "--dry-run"]
    rules_file.write_text(json.dumps(RULES))
    baseline_file.write_text(json.dumps(baseline))
    assert main(command) == 0
    assert main(command + ["--baseline", str(baseline_file)]) == 0
    baseline_file.write_text('{"schema_version":"architecture-baseline/v9","fingerprints":"abc"}')
    assert main(command + ["--baseline", str(baseline_file)]) == 2
    baseline_file.write_text(json.dumps({"fingerprints": []}))
    assert main(command + ["--baseline", str(baseline_file)]) == 2
    for rules in ({"rules": RULES["rules"]}, {**RULES, "rules": {}}, {**RULES, "schema_version": "x"}):
        rules_file.write_text(json.dumps(rules))
        assert main(command) == 2


def test_diff_identities_must_name_existing_ids(model, tmp_path):
    after = json.loads(json.dumps(model).replace('"order-store"', '"orders-db"'))
    assert diff_models(model, after)["changed"]
    assert not diff_models(model, after, {"order-store": "orders-db"})["changed"]
    for bad in ({"missing": "orders-db"}, {"order-store": "missing"}, {"order-store": 1}, []):
        with pytest.raises(ValueError):
            diff_models(model, after, bad)
    model_file, identities = tmp_path / "m.json", tmp_path / "ids.json"
    model_file.write_text(json.dumps(model))
    command = ["diff", "--before", str(model_file), "--after", str(model_file)]
    command += ["--identities", str(identities), "--output", str(tmp_path / "o"), "--dry-run"]
    for mapping, status in (({"api": "api"}, 0), ({"missing": "api"}, 2), ({"api": "missing"}, 2)):
        identities.write_text(json.dumps(mapping))
        assert main(command) == status


def test_diff_ids_are_readable(model):
    after = deepcopy(model)
    removed = after["relationships"].pop()
    after["deployment"]["placements"].pop(0)
    changes = {c["section"]: c["id"] for c in diff_models(model, after)["changes"]}
    assert changes["relationships"] == f"{removed['source_id']}->{removed['destination_id']}"
    assert changes["placements"] == "api->private-subnet"
    duplicate = deepcopy(model)
    duplicate["relationships"].append({**removed, "id": "extra", "description": "Other"})
    ids = [c["id"] for c in diff_models(model, duplicate)["changes"]]
    assert len(ids) == 1 and ids[0].startswith(f"{removed['source_id']}->{removed['destination_id']} {{")
    assert not any(i.startswith("(") for i in ids)


def test_explore_rejects_non_diff_documents(model, tmp_path):
    model_file, diff = tmp_path / "m.json", tmp_path / "diff.json"
    model_file.write_text(json.dumps(model))
    command = ["explore", "--model", str(model_file), "--diff", str(diff)]
    command += ["--output", str(tmp_path / "o"), "--dry-run"]
    diff.write_text(json.dumps(diff_models(model, model)))
    assert main(command) == 0
    for bad in (
        {"not": "a diff"},
        {"schema_version": "architecture-diff/v1", "changes": []},
        {"schema_version": "architecture-diff/v2", "changes": [], "changed": False},
        {"schema_version": "architecture-diff/v1", "changes": {}, "changed": False},
        [],
    ):
        diff.write_text(json.dumps(bad))
        assert main(command) == 2
