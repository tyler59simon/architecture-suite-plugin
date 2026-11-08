from copy import deepcopy
import pytest
from architecture_suite import model as models
from architecture_suite.plan import (
    Finding,
    PlanError,
    advisories,
    errors,
    compile_plan,
    lint_plan,
    parse_plan_document,
    parse_yaml,
)
from architecture_suite.draft import render_plan


def test_model_roundtrip_profiles(model, inputs):
    assert models.load_model(inputs[0]) == model
    assert not models.validate_model(model)
    assert models.normalized_model(model) == models.normalized_model(
        models.normalized_model(model)
    )
    for profile in models.VALIDATION_PROFILES:
        projection = models.project_model(model, profile)
        assert not models.validate_model(projection, profile)
        assert all(
            models.ELEMENT_TYPE_DEPTH[e["type"]] <= models.VIEW_TYPE_DEPTH[profile]
            for e in projection["elements"]
        )
    assert models.slugify(" A/B : _C ") == "a-b-c"
    assert models.slugify("☃", "fallback") == "fallback"
    assert models.view_id_for("code", "scope") == "code-scope"
    assert models.normalize_validation_profile() == "code"
    with pytest.raises(ValueError):
        models.normalize_validation_profile("dynamic")
    inputs[0].write_text("[]")
    with pytest.raises(ValueError):
        models.load_model(inputs[0])


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m.update(schema_version="1.0"),
        lambda m: m.update(system=None),
        lambda m: m["system"].update(scope=""),
        lambda m: m.update(elements=None),
        lambda m: m["elements"].append(None),
        lambda m: m["elements"][0].update(id="../escape"),
        lambda m: m["elements"].append(deepcopy(m["elements"][0])),
        lambda m: m["elements"][0].update(type="dynamic"),
        lambda m: m["elements"][1].update(name=""),
        lambda m: m["elements"][3].update(parent_id="absent"),
        lambda m: next(e for e in m["elements"] if e["type"] == "code").update(
            members=[]
        ),
        lambda m: m["elements"][0].update(evidence_ids=["absent"]),
        lambda m: m["elements"][0].update(confidence=1.5),
        lambda m: m["elements"][0].update(
            cloud={"provider": "aws", "service": "nonexistent"}
        ),
        lambda m: m["relationships"][0].update(destination_id="absent"),
        lambda m: m["relationships"][0].update(
            destination_id=m["relationships"][0]["source_id"]
        ),
        lambda m: m["relationships"][0].update(description=""),
        lambda m: m["relationships"][0].update(evidence_ids=["absent"]),
        lambda m: m["views"].pop(0),
        lambda m: m["views"].append(deepcopy(m["views"][2])),
        lambda m: m["views"][2].update(boundary_id="absent"),
        lambda m: m["views"][2].update(element_ids=["absent"]),
        lambda m: m["views"][2].update(relationship_ids=["absent"]),
        lambda m: m["views"][0].update(element_ids=[]),
        lambda m: m["views"][0].update(direction="diagonal"),
        lambda m: m["views"][0].update(id="renamed-context"),
        lambda m: m.update(deployment=[]),
        lambda m: m["deployment"]["nodes"].append(
            deepcopy(m["deployment"]["nodes"][0])
        ),
        lambda m: m["deployment"]["nodes"][0].update(type="unknown"),
        lambda m: m["deployment"]["nodes"][0].update(parent_id="absent"),
        lambda m: m["deployment"]["nodes"][0].update(
            parent_id=m["deployment"]["nodes"][-1]["id"]
        ),
        lambda m: m["deployment"]["placements"][0].update(element_id="customer"),
        lambda m: m["deployment"]["placements"].append(
            deepcopy(m["deployment"]["placements"][0])
        ),
        lambda m: m["gaps"].append("AKIA" + "A" * 16),
        lambda m: m["views"][0].update(element_ids=[{}, 2]),
    ],
)
def test_invalid_models(model, mutate):
    mutate(model)
    assert models.validate_model(model)


def test_repeated_scopes_and_cross_boundary(model):
    components = [v for v in model["views"] if v["type"] == "component"]
    codes = [v for v in model["views"] if v["type"] == "code"]
    assert {v["boundary_id"] for v in components} == {"api", "worker"}
    assert len(codes) == 3
    api = next(v for v in components if v["boundary_id"] == "api")
    assert "payment-provider" in api["element_ids"]
    assert "fulfillment" not in api["element_ids"]
    assert "order-queue" in api["element_ids"]
    assert models.validate_model(model, "context")
    m = models.project_model(model, "container")
    assert models.validate_model(
        m
    )  # full prefix cannot invent missing lower-level evidence
    assert models.validate_model([])


@pytest.mark.parametrize(
    "view_type,element",
    [
        ("context", "api"),
        ("container", "requesthandler"),
        ("component", "fulfillment"),
        ("code", "fulfillmentjob"),
    ],
)
def test_mixed_scope_details_rejected(model, view_type, element):
    view = next(v for v in model["views"] if v["type"] == view_type)
    view["element_ids"].append(element)
    assert any(f["code"] == "view-scope" for f in models.validate_model(model))


def test_plan_roundtrip_and_fidelity(plan):
    assert parse_plan_document(render_plan(plan)) == plan
    assert not errors(lint_plan(plan))
    model, fidelity = compile_plan(plan)
    assert not models.validate_model(model)
    assert fidelity.lossless
    assert fidelity.declared["elements"] == len(model["elements"])
    assert fidelity.as_dict()["lossless"]
    assert "Plan fidelity" in fidelity.render()
    assert errors([Finding("x", "y")])[0].blocking
    assert (
        advisories([Finding("x", "y", "where", "advisory")])[0]
        .render()
        .endswith("[where]")
    )
    plan["flows"].append({**plan["flows"][0], "description": "A second purpose"})
    _, fidelity = compile_plan(plan)
    assert fidelity.merged and fidelity.lossless
    # Container-to-own-component flow collapses at every separated C4 level.
    plan["flows"].append(
        {"from": "API", "to": "Request Controller", "description": "contains"}
    )
    _, fidelity = compile_plan(plan)
    assert not fidelity.lossless and fidelity.dropped
    plan["containers"][0]["components"][0]["code"][0].pop("description")
    assert compile_plan(plan)[0]


@pytest.mark.parametrize(
    "source",
    [
        "plain prose",
        "```yaml\na: b",
        "```yaml\n- entry\n```",
        "```yaml\nx: 1\nx: 2\n```",
        "```yaml\nx: &a []\ny: *a\n```",
        "```yaml\nx: !!python/object:builtins.object {}\n```",
        "```yaml\nx: [\n```",
        "```yaml\na: 1\n```\n```yaml\na: 2\n```",
        "```yaml\n[]: x\n```",
    ],
)
def test_plan_parse_failures(source):
    with pytest.raises(PlanError):
        parse_plan_document(source)


def test_plan_merging_and_limits():
    assert parse_plan_document(
        "```yml\na: []\n```\n```yaml\na: [1]\n```\n```yaml\na: [2]\n```\n```yaml\n\n```"
    ) == {"a": [1, 2]}
    for parser in (parse_yaml, parse_plan_document):
        with pytest.raises(PlanError):
            parser("x" * 2_000_001)
    assert parse_yaml("text: |\n  first\n  second\n")["text"] == "first\nsecond\n"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(unknown=[]),
        lambda p: p.update(schema_version="1"),
        lambda p: p.update(system=[]),
        lambda p: p["system"].update(name=""),
        lambda p: p.update(people={}),
        lambda p: p.pop("flows"),
        lambda p: p["people"].append("bad"),
        lambda p: p["people"][0].update(typo=True),
        lambda p: p["people"][0].update(name=3),
        lambda p: p["containers"].append(deepcopy(p["containers"][0])),
        lambda p: p["people"][0].update(description=""),
        lambda p: p["people"][0].update(evidence=2),
        lambda p: p["containers"][0].update(aws_service="made up service"),
        lambda p: p["containers"][0].update(components={}),
        lambda p: p["containers"][0].update(status="maybe"),
        lambda p: p["flows"][0].update(status="maybe"),
        lambda p: p["containers"][0].update(tags="pci"),
        lambda p: p["containers"][0].update(tags=[""]),
        lambda p: p["containers"][0]["components"][0]["code"][0].update(kind="enum"),
        lambda p: p["containers"][0]["components"][0]["code"][0].update(members=[]),
        lambda p: p["flows"].append(2),
        lambda p: p["flows"][0].update(typo=1),
        lambda p: p["flows"][0].update(to="typo"),
        lambda p: p["flows"][0].update(to=p["flows"][0]["from"]),
        lambda p: p["flows"][0].update(description=""),
        lambda p: p["flows"][0].update(order=0),
        lambda p: p.update(assumptions=[2]),
        lambda p: p.update(layout=[]),
        lambda p: p.update(layout={"views": {"missing": "right"}}),
        lambda p: p.update(layout={"views": {"containers": "diagonal"}}),
        lambda p: p.update(deployment={"nodes": [{}]}),
        lambda p: p["deployment"]["placements"][0].update(node="missing"),
        lambda p: p["gaps"].append("password=verysecretvalue"),
    ],
)
def test_lint_rejects_lossy_inputs(plan, mutate):
    mutate(plan)
    assert errors(lint_plan(plan))
    with pytest.raises(PlanError):
        compile_plan(plan)


def test_claim_status_lint_compile_and_conservative_merge(plan):
    # A second customer flow projects onto the same container-level arrow as flow 1.
    plan["flows"].append(
        {"from": "Customer", "to": "RequestValidator", "description": "Validates", "evidence": "x"}
    )
    model, _ = compile_plan(plan)
    assert not any("status" in item for item in model["elements"] + model["relationships"])
    merged = next(r for r in model["relationships"] if len(r["flow_ids"]) > 1)
    first, second = (int(f.split("-")[1]) - 1 for f in merged["flow_ids"][:2])
    plan["flows"][first]["status"] = "observed"
    plan["flows"][second]["status"] = "proposed"
    plan["containers"][0]["status"] = "inferred"
    assert not errors(lint_plan(plan))
    model, _ = compile_plan(plan)
    assert not models.validate_model(model)
    by_flows = {tuple(r["flow_ids"]): r for r in model["relationships"]}
    assert by_flows[tuple(merged["flow_ids"])]["status"] == "proposed"  # weakest wins
    element = next(e for e in model["elements"] if e["name"] == plan["containers"][0]["name"])
    assert element["status"] == "inferred"
    projected = models.project_model(model, "container")
    assert any(r.get("status") == "proposed" for r in projected["relationships"])
    broken = deepcopy(model)
    broken["elements"][0]["status"] = "maybe"
    assert models.validate_model(broken)


def test_plan_tags_reach_rule_selectors(plan):
    from architecture_suite.changes import check_rules

    plan["containers"][0]["tags"] = ["pci"]
    assert not errors(lint_plan(plan))
    model, _ = compile_plan(plan)
    tagged = [e for e in model["elements"] if e.get("tags")]
    assert [e["tags"] for e in tagged] == [["pci"]]
    assert not models.validate_model(model)
    rules = {
        "rules": [{"id": "no-pci-calls", "effect": "deny", "source": {"tags": ["pci"]}}]
    }
    assert check_rules(model, rules)["new_errors"] >= 1


def test_advisories_groups_and_explicit_deployment(plan):
    plan["people"][0].pop("evidence")
    plan["people"][0]["group"] = "Customers"
    plan["flows"][0].pop("evidence")
    findings = lint_plan(plan)
    assert not errors(findings)
    assert {f.code for f in advisories(findings)} >= {
        "unevidenced-element",
        "unevidenced-flow",
        "single-member-group",
    }
    plan["deployment"]["nodes"] = [
        {
            "id": "cloud",
            "name": "AWS Cloud",
            "type": "cloud",
            "nodes": [
                {
                    "id": "acct",
                    "name": "Account",
                    "type": "account",
                    "nodes": [
                        {"id": "r1", "name": "Region", "type": "region"},
                        {"id": "r2", "name": "Region", "type": "region"},
                    ],
                }
            ],
        }
    ]
    plan["deployment"]["placements"] = [{"element_id": "api", "node_id": "r1"}]
    assert not errors(lint_plan(plan))
    assert compile_plan(plan)[0]["deployment"]["placements"] == [
        {"element_id": "api", "node_id": "r1"}
    ]
    assert lint_plan([])[0].blocking


def test_labels_wrap_at_word_boundaries_not_mid_word():
    from architecture_suite.style import text_width, wrap_to_width

    text = "Per-harness lifecycle hooks that inject protocol and retrieved context at session start"
    lines = wrap_to_width(text, 240, 11)
    assert len(lines) > 1 and all(text_width(ln, 11) <= 240 for ln in lines)
    words = set(text.replace("-", " ").split())
    for line in lines:
        for word in line.replace("-", " ").split():
            assert word in words, line
    # An unbreakable token wider than the line still wraps by character, losing nothing.
    long = "x" * 80
    pieces = wrap_to_width(long, 120, 11)
    assert len(pieces) > 1 and "".join(pieces) == long


def test_devices_and_off_cloud_nodes_sit_outside_the_cloud_root(plan):
    plan = deepcopy(plan)
    plan["deployment"]["nodes"].append(
        {"id": "browser", "name": "Shopper browser", "type": "device",
         "children": [{"id": "runtime", "name": "Web browser", "type": "execution-environment"}]}
    )
    plan["deployment"]["nodes"].append({"id": "dc", "name": "Head office", "type": "off-cloud"})
    model = compile_plan(plan)[0]
    nodes = {n["id"]: n for n in model["deployment"]["nodes"]}
    assert "parent_id" not in nodes["browser"] and "parent_id" not in nodes["dc"]
    assert nodes["runtime"]["parent_id"] == "browser"
    cloud = next(n for n in nodes.values() if n["type"] == "cloud")
    assert any(n.get("parent_id") == cloud["id"] for n in nodes.values())
    assert not models.validate_model(model)
