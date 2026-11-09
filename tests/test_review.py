from copy import deepcopy
import json
import pytest
from architecture_suite.cli import main
from architecture_suite.draft import render_plan
from architecture_suite.review import render_review_markdown, review_exit_code, review_plan


def codes(review):
    return {f["code"] for f in review["findings"]}


def find(review, code):
    return [f for f in review["findings"] if f["code"] == code]


def test_complete_plan_is_ready_at_every_level(plan):
    review = review_plan(plan)
    assert review["ok"] and review["max_level"] == "code"
    assert review["ready_levels"] == ["system", "container", "component", "code", "deployment"]
    assert review["coverage"]["elements_with_evidence_percent"] == 100
    assert review["coverage"]["flows_with_evidence_percent"] == 100
    assert review["claim_status"]["unstated"] == review["coverage"]["elements"] + len(plan["flows"])
    assert not codes(review) & {
        "no-people",
        "isolated-element",
        "unplaced-container",
        "placeholder",
    }
    assert review_exit_code(review) == 0
    assert review_exit_code(review, strict=True) == (1 if review["findings"] else 0)


def test_lint_errors_block_every_level(plan):
    plan["flows"][0]["to"] = "Nowhere"
    review = review_plan(plan)
    assert not review["ok"] and review["max_level"] is None
    assert {v["status"] for v in review["levels"].values()} == {"blocked"}
    assert "unknown-endpoint" in codes(review) and review_exit_code(review) == 1
    assert "## Coverage" not in render_review_markdown(review)


def test_container_only_plan_reports_the_evidenced_prefix(plan):
    for container in plan["containers"]:
        container.pop("components", None)
    plan.pop("deployment")
    plan["flows"] = [
        f
        for f in plan["flows"]
        if {f["from"], f["to"]}
        <= {"Customer", "Payment Provider"} | {c["name"] for c in plan["containers"]}
    ]
    review = review_plan(plan)
    assert review["max_level"] == "container" and "deployment" not in review["levels"]
    assert review["levels"]["component"]["status"] == "blocked"
    assert review["levels"]["component"]["reasons"]


def mutate_people(p):
    p["people"] = []
    p["flows"] = [f for f in p["flows"] if "Customer" not in (f["from"], f["to"])]


def mutate_externals(p):
    p["external_systems"] = []
    p["flows"] = [f for f in p["flows"] if "Payment Provider" not in (f["from"], f["to"])]


def mutate_isolated(p):
    p["people"].append(
        {"name": "Auditor", "description": "Reviews monthly order reports", "evidence": "brief"}
    )


def mutate_technology(p):
    p["containers"][0].pop("technology")


def mutate_observed(p):
    p["containers"][0]["status"] = "observed"
    p["containers"][0].pop("evidence")


def mutate_observed_flow(p):
    p["flows"][0]["status"] = "observed"
    p["flows"][0].pop("evidence")


def mutate_thin(p):
    p["containers"][0]["description"] = p["containers"][0]["name"]


def mutate_placeholder(p):
    p["containers"][0]["technology"] = "Unspecified"
    p["system"]["scope"] = "Replace with the ownership boundary"


def mutate_unplaced(p):
    p["deployment"]["placements"] = [
        x for x in p["deployment"]["placements"] if x.get("element") != p["containers"][0]["name"]
    ]


def mutate_crowded(p):
    for i in range(36):
        p["people"].append(
            {"name": f"Person {i}", "description": "Uses the ordering system", "evidence": "brief"}
        )
        p["flows"].append(
            {
                "from": f"Person {i}",
                "to": p["containers"][0]["name"],
                "description": "Uses",
                "evidence": "brief",
            }
        )


@pytest.mark.parametrize(
    "mutate, code, level",
    [
        (mutate_people, "no-people", "system"),
        (mutate_externals, "no-external-systems", "system"),
        (mutate_isolated, "isolated-element", "system"),
        (mutate_technology, "missing-technology", "container"),
        (mutate_observed, "observed-without-evidence", "container"),
        (mutate_observed_flow, "observed-without-evidence", "plan"),
        (mutate_thin, "thin-description", "container"),
        (mutate_placeholder, "placeholder", "system"),  # system scope, then API technology
        (mutate_unplaced, "unplaced-container", "deployment"),
        (mutate_crowded, "crowded-view", "system"),
    ],
)
def test_review_findings_carry_level_and_question(plan, mutate, code, level):
    changed = deepcopy(plan)
    mutate(changed)
    review = review_plan(changed)
    assert review["ok"], [f for f in review["findings"] if f["severity"] == "error"]
    baseline = {(f["code"], f["where"]) for f in review_plan(plan)["findings"]}
    hits = [f for f in find(review, code) if (code, f["where"]) not in baseline]
    assert hits and hits[0]["level"] == level and hits[0]["severity"] == "advisory"
    if code != "crowded-view":
        assert hits[0]["question"].endswith("?")


def test_lint_advisories_get_questions(plan):
    plan["containers"][0].pop("evidence")
    plan["flows"][0].pop("evidence")
    review = review_plan(plan)
    element = find(review, "unevidenced-element")[0]
    assert element["level"] == "container" and plan["containers"][0]["name"] in element["question"]
    flow = find(review, "unevidenced-flow")[0]
    assert plan["flows"][0]["from"] in flow["question"]


def test_flow_that_collapses_everywhere_is_reported(plan):
    container = plan["containers"][0]
    plan["flows"].append(
        {
            "from": container["name"],
            "to": container["components"][0]["name"],
            "description": "Calls its own part",
            "evidence": "brief",
        }
    )
    review = review_plan(plan)
    assert find(review, "dropped-flow")


def test_markdown_lists_readiness_findings_and_gaps(plan):
    plan["containers"][0].pop("technology")
    plan["gaps"] = ["Retry policy is unknown"]
    plan["assumptions"] = ["Single region"]
    text = render_review_markdown(review_plan(plan))
    assert "| container | ready |" in text and "Deepest ready C4 level: code" in text
    assert "missing-technology" in text and "  - Ask: What is" in text
    assert "## Open gaps" in text and "Retry policy is unknown" in text and "Single region" in text


def test_markdown_without_findings():
    review = {
        "levels": {},
        "max_level": None,
        "coverage": {},
        "findings": [],
        "gaps": [],
        "assumptions": [],
    }
    assert "None." in render_review_markdown(review)


def test_plan_review_cli(inputs, tmp_path, capsys):
    plan_path = inputs[1]
    assert main(["plan-review", "--plan", str(plan_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["operation"] == "plan-review" and result["max_level"] == "code"
    strict = main(["plan-review", "--plan", str(plan_path), "--strict"])
    assert strict == (1 if json.loads(capsys.readouterr().out)["findings"] else 0)
    report = tmp_path / "out" / "plan-review.md"
    argv = ["plan-review", "--plan", str(plan_path), "--output", str(report)]
    assert main(argv + ["--dry-run"]) == 0 and not report.exists()
    assert json.loads(capsys.readouterr().out)["output"] == str(report)
    assert main(argv) == 3 and not report.exists()  # writing needs --confirm-write
    capsys.readouterr()
    assert main(argv + ["--confirm-write"]) == 0
    assert report.read_text(encoding="utf-8").startswith("# Plan review")
    assert main(argv + ["--confirm-write"]) == 3  # existing file needs --confirm-overwrite
    assert main(argv + ["--confirm-write", "--confirm-overwrite"]) == 0
    capsys.readouterr()
    assert (
        main(["plan-review", "--plan", str(plan_path), "--output", str(plan_path), "--dry-run"])
        == 3
    )
    assert main(["plan-review", "--plan", str(plan_path), "--output", str(tmp_path)]) == 3


def test_plan_review_cli_blocked_plan(plan, tmp_path, capsys):
    plan["flows"][0]["from"] = "Ghost"
    path = tmp_path / "plan.md"
    path.write_text(render_plan(plan), encoding="utf-8")
    assert main(["plan-review", "--plan", str(path)]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False
