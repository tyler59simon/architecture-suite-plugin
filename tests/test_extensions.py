import json
import zipfile
from copy import deepcopy
import pytest
from architecture_suite.cli import main
from architecture_suite.changes import diff_models, check_rules
from architecture_suite.infrastructure import import_infrastructure, topology_plan
from architecture_suite.inventory import dependency_inventory
from architecture_suite.scenarios import (
    validate_scenario,
    scenario_mermaid,
    scenario_scene,
)
from architecture_suite.distribution import package_hosts, install_host, HOSTS
from architecture_suite.renderers import browser_page, validate_png
from architecture_suite.plan import compile_plan


@pytest.fixture
def scenario():
    message = {"from": "customer", "to": "api", "description": "Send request"}
    return {
        "schema_version": "architecture-scenario/v1",
        "name": "Submit",
        "participants": ["customer", "api"],
        "steps": [
            message,
            {
                "type": "alt",
                "condition": "accepted",
                "steps": [
                    {**message, "type": "response", "from": "api", "to": "customer"}
                ],
                "branches": [{"condition": "rejected", "steps": [message]}],
            },
            {
                "type": "loop",
                "condition": "retry",
                "steps": [{**message, "to": "customer"}],
            },
            {
                "type": "par",
                "condition": "concurrent",
                "steps": [message],
                "branches": [{"condition": "other", "steps": [message]}],
            },
            {"type": "opt", "condition": "optional", "steps": [message]},
        ],
    }


def test_changes_and_baselines(model):
    assert not diff_models(model, deepcopy(model))["changed"]
    after = deepcopy(model)
    after["elements"][0]["description"] = "changed"
    assert diff_models(model, after)["changes"][0]["kind"] == "changed"
    after["elements"].pop()
    assert diff_models(model, after)["changed"]
    with pytest.raises(ValueError):
        diff_models(model, model, {"a": "b", "c": "b"})
    rules = {
        "rules": [
            {
                "id": "no-external",
                "effect": "deny",
                "source": {},
                "destination": {"ids": ["payment-provider"]},
            }
        ]
    }
    result = check_rules(model, rules)
    assert result["new_errors"] > 0
    assert (
        check_rules(model, rules, {"fingerprints": result["fingerprints"]})[
            "new_errors"
        ]
        == 0
    )
    assert check_rules(
        model,
        {
            "rules": [
                {
                    "id": "only-people",
                    "effect": "allow",
                    "destination": {"types": ["person"]},
                }
            ]
        },
    )["findings"]
    for rule in (
        {"rules": [{"id": "x", "effect": "exec"}]},
        {"rules": [{"id": "x", "effect": "deny", "source": {"unknown": []}}]},
        {"rules": [{"id": "x", "effect": "deny", "source": {"ids": "bad"}}]},
        [],
    ):
        with pytest.raises(ValueError):
            check_rules(model, rule)


@pytest.mark.parametrize(
    "doc",
    [
        {
            "planned_values": {
                "root_module": {
                    "resources": [
                        {
                            "address": "aws_vpc.main",
                            "type": "aws_vpc",
                            "values": {"id": "vpc-123"},
                        }
                    ],
                    "child_modules": [
                        {
                            "resources": [
                                {
                                    "address": "aws_subnet.main",
                                    "type": "aws_subnet",
                                    "values": {"vpc_id": "vpc-123"},
                                }
                            ]
                        }
                    ],
                }
            },
            "resource_changes": [{}],
        },
        {
            "Resources": {
                "VPC": {"Type": "AWS::EC2::VPC"},
                "Subnet": {
                    "Type": "AWS::EC2::Subnet",
                    "Properties": {"VpcId": {"Ref": "VPC"}},
                },
            }
        },
        {
            "apiVersion": "v1",
            "kind": "List",
            "items": [
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {"name": "api"},
                    "spec": {"selector": {"app": "api"}},
                },
                {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "metadata": {"name": "api"},
                    "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
                },
            ],
        },
        {
            "services": {
                "api": {
                    "depends_on": ["db"],
                    "environment": {"PASSWORD": "${PASSWORD}"},
                },
                "db": {},
            }
        },
    ],
)
def test_infra_formats(tmp_path, doc):
    path = tmp_path / "infra.json"
    path.write_text(json.dumps(doc))
    topology = import_infrastructure([path])
    assert topology["resources"] and topology["relationships"]
    plan = topology_plan(topology)
    assert {c["status"] for c in plan["containers"]} == {"inferred"}
    assert {f["status"] for f in plan["flows"]} == {"inferred"}
    assert compile_plan(plan)[0]["elements"]
    with pytest.raises(ValueError):
        import_infrastructure([path], {"missing": "api"})
    path.write_text("unknown: true")
    with pytest.raises(ValueError):
        import_infrastructure([path])
    path.write_text("[]")
    with pytest.raises(ValueError):
        import_infrastructure([path])


def test_terraform_sensitivity_and_unknown_masks(tmp_path):
    marker = "AUDIT-SYNTHETIC-PRIVATE-VALUE"
    doc = {
        "planned_values": {
            "root_module": {
                "resources": [
                    {
                        "address": "random_password.db",
                        "type": "random_password",
                        "values": {
                            "result": marker,
                            "length": 24,
                            "nested": {"note": marker, "keep": "visible"},
                            "items": [marker, "plain"],
                        },
                        "sensitive_values": {
                            "result": True,
                            "nested": {"note": True},
                            "items": [True, False],
                        },
                    }
                ]
            }
        },
        "resource_changes": [
            {
                "address": "random_password.db",
                "change": {"after_unknown": {"id": True}, "after_sensitive": {}},
            }
        ],
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(doc))
    topology = import_infrastructure([path])
    payload = json.dumps(topology) + json.dumps(topology_plan(topology))
    assert marker not in payload
    props = topology["resources"][0]["properties"]
    assert props["result"] == "[SENSITIVE]" and props["length"] == 24
    assert props["nested"] == {"note": "[SENSITIVE]", "keep": "visible"}
    assert props["items"] == ["[SENSITIVE]", "plain"]
    assert props["id"] == "[UNKNOWN AFTER APPLY]"
    messages = [f["message"] for f in topology["findings"]]
    assert "Sensitive values masked: items[0], nested.note, result" in messages
    assert "Values unknown until apply: id" in messages


def test_infrastructure_references_are_exact(tmp_path):
    def resource(address, kind, values):
        return {"address": address, "type": kind, "values": values}

    doc = {
        "planned_values": {
            "root_module": {
                "resources": [
                    resource("aws_vpc.a", "aws_vpc", {"id": "vpc-1"}),
                    resource("aws_vpc.b", "aws_vpc", {"id": "vpc-123", "note": "not vpc-1"}),
                    resource("aws_subnet.s", "aws_subnet", {"id": "subnet-9", "vpc_id": "vpc-123"}),
                ]
            }
        }
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(doc))
    topology = import_infrastructure([path])
    edges = {(e["source_id"], e["destination_id"]) for e in topology["relationships"]}
    assert edges == {("input-0-aws-subnet-s", "input-0-aws-vpc-b")}
    subnet = next(r for r in topology["resources"] if r["type"] == "aws_subnet")
    assert subnet["parent_id"] == "input-0-aws-vpc-b"
    template = {
        "Resources": {
            "Bucket": {"Type": "AWS::S3::Bucket", "Properties": {}},
            "Fn": {"Type": "AWS::Lambda::Function", "DependsOn": "Bucket", "Properties": {}},
            "Fn2": {"Type": "AWS::Lambda::Function", "DependsOn": ["Bucket", "Missing"]},
        }
    }
    path.write_text(json.dumps(template))
    relations = import_infrastructure([path])["relationships"]
    assert sorted((e["source_id"], e["kind"]) for e in relations) == [
        ("input-0-fn", "depends-on"),
        ("input-0-fn2", "depends-on"),
    ]


def test_tree_inventory():
    files = {
        "main.py": 'from worker import work\n@app.get("/items")\ndef main():\n return work()',
        "worker.py": "def work(): pass",
        "broken.py": "invalid !!!",
        "main.ts": 'import { work } from "./worker"; export function main(){return work();}',
        "main.cs": "class A { public void Run(){Work();} }",
        "main.java": "class A { public void run(){work();} }",
        "main.kt": "fun run() { work() }",
        "main.go": "package main\nfunc Run(){ Work() }",
        "ignore.txt": "none",
    }
    report = dependency_inventory(files)
    assert len(report["declarations"]) >= 7
    assert [r["path"] for r in report["routes"]] == ["/items"]
    client = dependency_inventory(
        {"c.py": 'client.get("https://example.com/health")\nsettings.get("key")\n'}
    )
    assert not client["routes"]
    assert [c["target"] for c in client["connections"]] == ["https://example.com/health"]
    assert report["findings"]
    assert any(r.get("resolved_file") == "worker.py" for r in report["references"])


def test_scenario_exports(model, scenario):
    assert validate_scenario(scenario, model)
    source = scenario_mermaid(scenario, model)
    assert "alt accepted" in source and "par concurrent" in source and "-->>" in source
    scene = scenario_scene(scenario, model)
    assert len(scene.edges) > len(scenario["participants"])
    for mutation in ("unknown", "duplicate", "steps", "type", "condition", "branch"):
        bad = deepcopy(scenario)
        if mutation == "unknown":
            bad["participants"] = ["missing"]
        elif mutation == "duplicate":
            bad["participants"] *= 2
        elif mutation == "steps":
            bad["steps"] = []
        elif mutation == "type":
            bad["steps"][0]["type"] = "exec"
        elif mutation == "condition":
            bad["steps"][1]["condition"] = ""
        else:
            bad["steps"][1]["branches"] = [{}]
        with pytest.raises(ValueError):
            validate_scenario(bad, model)


def test_new_cli(inputs, tmp_path, scenario, model):
    scenario_file = tmp_path / "scenario.json"
    scenario_file.write_text(json.dumps(scenario))
    rules = tmp_path / "rules.json"
    rules.write_text(
        json.dumps(
            {
                "schema_version": "architecture-rules/v1",
                "rules": [{"id": "deny", "effect": "deny"}],
            }
        )
    )
    infra = tmp_path / "compose.yaml"
    infra.write_text("services:\n  api: {}\n")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("def main():\n    return 1\n")
    inside = ["inventory", "--repo", str(repo), "--output", str(repo / "inventory")]
    assert main(inside + ["--dry-run"]) == 3  # never inside the analyzed repository
    commands = [
        ["inventory", "--repo", str(repo)],
        ["import-infra", "--input", str(infra)],
        ["diff", "--before", str(inputs[0]), "--after", str(inputs[0])],
        ["check", "--model", str(inputs[0]), "--rules", str(rules)],
        [
            "scenario-render",
            "--model",
            str(inputs[0]),
            "--scenario",
            str(scenario_file),
        ],
        ["explore", "--model", str(inputs[0]), "--scenario", str(scenario_file)],
    ]
    assert (
        main(
            [
                "scenario-lint",
                "--model",
                str(inputs[0]),
                "--scenario",
                str(scenario_file),
            ]
        )
        == 0
    )
    for i, command in enumerate(commands):
        out = tmp_path / f"out-{i}"
        assert main(command + ["--output", str(out), "--dry-run"]) == 0
        assert not out.exists()
        assert main(command + ["--output", str(out), "--confirm-write"]) == 0
    assert validate_png(tmp_path / "out-4/scenario.png")
    # A scenario rendered into a C4 output folder never retires the C4 files.
    shared = tmp_path / "shared"
    c4 = ["render", "--model", str(inputs[0]), "--output", str(shared), "--format", "mermaid"]
    assert main(c4 + ["--level", "system", "--confirm-write"]) == 0
    assert (
        main(commands[4] + ["--output", str(shared), "--format", "mermaid", "--confirm-write",
                            "--confirm-overwrite"])
        == 0
    )
    assert (shared / "01-system-context/system-context.mmd").is_file()
    owners = json.loads((shared / ".architecture-suite-manifest.json").read_text())["owners"]
    assert set(owners) == {"c4", "scenario-render"}
    assert (
        main(
            commands[3]
            + [
                "--output",
                str(tmp_path / "checkfail"),
                "--fail-on",
                "error",
                "--confirm-write",
            ]
        )
        == 1
    )
    with browser_page() as page:
        errors = []
        requests = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda r: requests.append(r.url))
        page.context.unroute("**/*")
        page.context.route("http://**/*", lambda route: route.abort())
        page.context.route("https://**/*", lambda route: route.abort())
        html = (tmp_path / "out-5/explorer.html").read_text(encoding="utf-8")
        assert "script-src 'sha256-" in html and "script-src 'unsafe-inline'" not in html
        page.goto((tmp_path / "out-5/explorer.html").as_uri())
        assert page.locator("#elements summary").count() > 0
        page.locator("#search").fill("API")
        page.locator("#elements button").first.click()
        assert page.locator("#details").inner_text()
        assert not errors and not [r for r in requests if r.startswith("http")]
        script = (
            __import__("pathlib").Path(__file__).resolve().parents[1]
            / "node_modules/mermaid/dist/mermaid.min.js"
        )
        page.goto("about:blank")  # fresh document: the explorer CSP must not carry over
        page.add_script_tag(path=str(script))
        page.evaluate("mermaid.initialize({startOnLoad:false})")
        assert page.evaluate(
            "async s=>!!(await mermaid.parse(s))", scenario_mermaid(scenario, model)
        )


def test_packages_and_install(tmp_path):
    skills = tmp_path / "skills"
    names = ["c4-diagrams", "c4-aws"]
    for name in names:
        (skills / name).mkdir(parents=True)
        (skills / name / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: test\n---\nRun scripts"
        )
    (skills / "architecture-suite-runtime/scripts").mkdir(parents=True)
    (skills / "architecture-suite-runtime/scripts/tool.py").write_text("x=1")
    # Legal files beside skills/ are packaged too; they must not leak into VALIDATION.json.
    (tmp_path / "LICENSE").write_text("license")
    (tmp_path / "NOTICE").write_text("notice")
    out = tmp_path / "packages"
    out.mkdir()
    package_hosts(skills, out)
    first = {p.name: p.read_bytes() for p in out.iterdir()}
    package_hosts(skills, out)
    assert first == {p.name: p.read_bytes() for p in out.iterdir()}
    for host in HOSTS:
        with zipfile.ZipFile(out / (host + ".zip")) as z:
            prefix = "skills" if host in {"claude", "factory"} else HOSTS[host]
            members = z.namelist()
            for name in names:
                assert f"{prefix}/{name}/SKILL.md" in members
            assert f"{prefix}/architecture-suite-runtime/scripts/tool.py" in members
            if host in {"claude", "factory"}:
                manifest = json.loads(
                    z.read(
                        (".claude-plugin" if host == "claude" else ".factory-plugin")
                        + "/plugin.json"
                    )
                )
                assert manifest["name"] == "architecture-suite"
            assert json.loads(z.read("VALIDATION.json"))["skills"] == sorted(names)
        base = tmp_path / "project"
        install_host(skills, host, "project", project=base)
        for name in names:
            assert (base / HOSTS[host] / name / "SKILL.md").is_file()
        assert (base / HOSTS[host] / "architecture-suite-runtime/scripts/tool.py").is_file()
        install_host(skills, host, "project", project=base, overwrite=True)
        assert install_host(skills, host, "user", home=tmp_path / "home").is_dir()
    for args in [("unknown", "user", None), ("codex", "project", None)]:
        with pytest.raises(ValueError):
            install_host(skills, args[0], args[1], args[2])


def test_failure_controls_and_bindings(inputs, tmp_path, scenario):
    path = tmp_path / "infra.yaml"
    path.write_text(
        "services:\n  api:\n    environment:\n      password: veryprivatevalue\n    networks: [private]\n  db: {}\nnetworks:\n  private: {}\nvolumes:\n  data: {}\n"
    )
    report = import_infrastructure([path])
    assert "veryprivatevalue" not in json.dumps(report)
    assert any(e["kind"] == "network-membership" for e in report["relationships"])
    binding = tmp_path / "binding.json"
    binding.write_text(json.dumps({report["resources"][0]["id"]: "api"}))
    args = [
        "import-infra",
        "--input",
        str(path),
        "--bindings",
        str(binding),
        "--model",
        str(inputs[0]),
        "--output",
        str(tmp_path / "import"),
    ]
    assert main(args + ["--confirm-write"]) == 0
    assert main(args) == 3
    binding.write_text(json.dumps({report["resources"][0]["id"]: "missing"}))
    assert main(args + ["--dry-run"]) == 2
    assert (
        main(
            [
                "import-infra",
                "--input",
                str(path),
                "--bindings",
                str(binding),
                "--output",
                str(tmp_path / "other"),
                "--dry-run",
            ]
        )
        == 2
    )
    path.write_text(
        "Resources:\n  Thing:\n    Type: AWS::S3::Bucket\n    Properties:\n      BucketName: !Sub bucket-${Region}\n"
    )
    assert import_infrastructure([path])["findings"]
    path.write_text("Resources: [")
    assert (
        main(
            [
                "import-infra",
                "--input",
                str(path),
                "--output",
                str(tmp_path / "bad"),
                "--dry-run",
            ]
        )
        == 2
    )
    path.write_text("planned_values: null")
    assert (
        main(
            [
                "import-infra",
                "--input",
                str(path),
                "--output",
                str(tmp_path / "bad"),
                "--dry-run",
            ]
        )
        == 2
    )
    scenario_file = tmp_path / "scenario.json"
    scenario_file.write_text(json.dumps(scenario))
    assert (
        main(
            [
                "scenario-render",
                "--scenario",
                str(scenario_file),
                "--model",
                str(inputs[0]),
                "--format",
                "pdf",
                "--output",
                str(tmp_path / "bad"),
                "--dry-run",
            ]
        )
        == 2
    )
    bad_model = tmp_path / "bad.json"
    bad_model.write_text('{"elements":[]}')
    assert (
        main(
            [
                "scenario-lint",
                "--scenario",
                str(scenario_file),
                "--model",
                str(bad_model),
            ]
        )
        == 2
    )
    bad = deepcopy(scenario)
    bad["steps"][0]["from"] = "missing"
    with pytest.raises(ValueError):
        validate_scenario(bad, json.loads(inputs[0].read_text()))
    bad = deepcopy(scenario)
    bad["steps"][2]["branches"] = [{"condition": "bad", "steps": scenario["steps"][:1]}]
    with pytest.raises(ValueError):
        validate_scenario(bad, json.loads(inputs[0].read_text()))
    broken = dependency_inventory(
        {
            "broken.ts": "export function {",
            "x.py": "class A:\n pass",
            "routes.go": 'package main\nfunc Main(){http.HandleFunc("/x", x)}',
            "config.txt": "http://service/api",
        }
    )
    assert broken["findings"] and broken["connections"]


def test_infrastructure_evidence_does_not_leak_home_paths(tmp_path, monkeypatch):
    from architecture_suite.infrastructure import evidence_reference

    inside = tmp_path / "infra" / "compose.json"
    monkeypatch.chdir(tmp_path)
    assert evidence_reference(inside) == "infra/compose.json"
    outside = tmp_path.parent / "elsewhere.json"
    assert evidence_reference(outside) == str(outside)
