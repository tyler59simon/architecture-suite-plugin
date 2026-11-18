import json
import zipfile
from copy import deepcopy
import pytest
from architecture_suite.cli import main
from architecture_suite.changes import diff_models, check_rules, markdown_report
from architecture_suite.infrastructure import import_infrastructure, topology_plan
from architecture_suite.inventory import dependency_inventory
from architecture_suite.scenarios import (
    validate_scenario,
    scenario_mermaid,
    scenario_scene,
)
from architecture_suite.distribution import install_host, HOSTS
from host_packaging import package_hosts
from architecture_suite.renderers import browser_page, validate_png
from architecture_suite.plan import compile_plan, lint_plan
from architecture_suite.emit import render_scene_svg, render_scene_drawio


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


@pytest.mark.browser
@pytest.mark.slow
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
        page.locator("#search").fill("parent_id")  # a JSON key, not text in any element
        assert page.locator("#elements summary, #elements button").count() == 0
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
        stale = base / HOSTS[host] / "architecture-suite-runtime/scripts/removed.py"
        stale.write_text("dropped in the new version")
        install_host(skills, host, "project", project=base, overwrite=True)
        assert not stale.exists()  # an upgrade does not keep files the new version lacks
        assert install_host(skills, host, "user", home=tmp_path / "home").is_dir()
    for args in [("unknown", "user", None), ("codex", "project", None)]:
        with pytest.raises(ValueError):
            install_host(skills, args[0], args[1], args[2])


def test_dry_runs_list_files_without_building_diagrams(
    inputs, tmp_path, scenario, monkeypatch, capsys
):
    from architecture_suite import extensions, renderers, scene

    scenario_file = tmp_path / "scenario.json"
    scenario_file.write_text(json.dumps(scenario))
    scenario_args = [
        "scenario-render",
        "--model",
        str(inputs[0]),
        "--scenario",
        str(scenario_file),
        "--format",
        "mermaid,plantuml,svg,drawio",
    ]
    explore_args = ["explore", "--model", str(inputs[0]), "--scenario", str(scenario_file)]
    real = {}
    for name, command in (("scenario", scenario_args), ("explore", explore_args)):
        out = tmp_path / ("real-" + name)
        assert main(command + ["--output", str(out), "--confirm-write"]) == 0
        real[name] = sorted(
            p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()
        )
        capsys.readouterr()

    def unavailable(*args, **kwargs):
        raise AssertionError("a dry run must not build diagrams")

    for owner, names in (
        (extensions, ("scenario_scene", "explorer_html", "render_scene_svg", "scene_vsdx")),
        (scene, ("layout_graph",)),
        (renderers, ("browser_page",)),
    ):
        for name in names:
            monkeypatch.setattr(owner, name, unavailable)
    for name, command in (("scenario", scenario_args), ("explore", explore_args)):
        out = tmp_path / ("dry-" + name)
        assert main(command + ["--output", str(out), "--dry-run"]) == 0
        listed = json.loads(capsys.readouterr().out)["files"]
        assert not out.exists()
        assert sorted(f for f in listed if not f.startswith(".")) == [
            f for f in real[name] if not f.startswith(".")
        ]


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


def test_terraform_configuration_references_and_no_false_id_edges(tmp_path):
    """Plan `configuration` references give edges; shared IDs and tag values do not."""
    def resource(address, kind, values):
        return {"address": address, "type": kind, "values": values}

    doc = {
        "planned_values": {
            "root_module": {
                "resources": [
                    resource("aws_s3_bucket.logs", "aws_s3_bucket", {"id": "logs", "bucket": "logs"}),
                    resource("aws_s3_bucket_versioning.logs", "aws_s3_bucket_versioning",
                             {"id": "logs", "bucket": "logs"}),
                    resource("aws_iam_role.app", "aws_iam_role", {"id": "app"}),
                    resource("aws_ecs_service.api", "aws_ecs_service",
                             {"id": "svc-1", "tags": {"Team": "app"}}),
                ]
            }
        },
        "configuration": {
            "root_module": {
                "resources": [
                    {"address": "aws_s3_bucket_versioning.logs",
                     "expressions": {"bucket": {"references": ["aws_s3_bucket.logs.id", "aws_s3_bucket.logs"]}}},
                    {"address": "aws_ecs_service.api",
                     "expressions": {"tags": {"constant_value": {"Team": "app"}}}},
                ]
            }
        },
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(doc))
    edges = {
        (e["source_id"], e["destination_id"], e["kind"])
        for e in import_infrastructure([path])["relationships"]
    }
    assert edges == {
        ("input-0-aws-s3-bucket-versioning-logs", "input-0-aws-s3-bucket-logs", "explicit-reference")
    }


def test_terraform_references_stay_inside_their_module_instance(tmp_path):
    """for_each/count module instances: each subnet links to its own instance's VPC."""
    def resource(address, kind):
        return {"address": address, "type": kind, "values": {}}

    doc = {
        "planned_values": {
            "root_module": {
                "child_modules": [
                    {"resources": [
                        resource(f'module.network["{env}"].aws_vpc.main', "aws_vpc"),
                        resource(f'module.network["{env}"].aws_subnet.private[0]', "aws_subnet"),
                    ]}
                    for env in ("prod", "dev")
                ]
            }
        },
        "configuration": {
            "root_module": {
                "module_calls": {
                    "network": {"module": {"resources": [
                        {"address": "aws_subnet.private",
                         "expressions": {"vpc_id": {"references": ["aws_vpc.main.id", "aws_vpc.main"]}}},
                    ]}}
                }
            }
        },
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(doc))
    edges = {
        (e["source_id"], e["destination_id"])
        for e in import_infrastructure([path])["relationships"]
    }
    assert len(edges) == 2
    for source, destination in edges:
        env = "prod" if "prod" in source else "dev"
        assert "subnet" in source and "vpc" in destination and env in destination


def _counted_subnets(tmp_path, references, subnets=("aws_subnet.app[0]", "aws_subnet.app[1]")):
    """Two instances of aws_subnet.app and an instance that references them."""
    doc = {
        "planned_values": {
            "root_module": {
                "resources": [
                    {"address": address, "type": address.split(".")[0], "values": {}}
                    for address in (*subnets, "aws_instance.web")
                ]
            }
        },
        "configuration": {
            "root_module": {
                "resources": [
                    {"address": "aws_instance.web",
                     "expressions": {"subnet_id": {"references": references}}},
                ]
            }
        },
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(doc))
    return import_infrastructure([path])


def test_terraform_indexed_reference_links_only_that_instance(tmp_path):
    # Terraform lists the attribute, the instance and the whole resource.
    topology = _counted_subnets(
        tmp_path, ["aws_subnet.app[0].id", "aws_subnet.app[0]", "aws_subnet.app"]
    )
    edges = {(e["source_id"], e["destination_id"]) for e in topology["relationships"]}
    assert edges == {("input-0-aws-instance-web", "input-0-aws-subnet-app-0")}
    assert not any("aws_subnet.app" in f["message"] for f in topology["findings"])


def test_terraform_unindexed_reference_to_counted_resource_is_a_finding(tmp_path):
    topology = _counted_subnets(tmp_path, ["aws_subnet.app"])
    assert not topology["relationships"]
    finding = next(f for f in topology["findings"] if "aws_subnet.app" in f["message"])
    assert finding["resource"] == "input-0-aws-instance-web"
    assert finding["message"] in topology_plan(topology)["gaps"]


@pytest.mark.parametrize(
    "references",
    [
        # `[aws_subnet.app[var.index].id, aws_subnet.app[0].id]`, in either order: a
        # dynamic index gives only `aws_subnet.app`, a literal one the full chain.
        ["aws_subnet.app", "var.index", "aws_subnet.app[0].id", "aws_subnet.app[0]", "aws_subnet.app"],
        ["aws_subnet.app[0].id", "aws_subnet.app[0]", "aws_subnet.app", "aws_subnet.app", "var.index"],
    ],
)
def test_terraform_dynamic_and_literal_index_in_one_expression(tmp_path, references):
    topology = _counted_subnets(tmp_path, references)
    edges = {(e["source_id"], e["destination_id"]) for e in topology["relationships"]}
    assert edges == {("input-0-aws-instance-web", "input-0-aws-subnet-app-0")}
    assert any(
        f["resource"] == "input-0-aws-instance-web" and "aws_subnet.app fits 2" in f["message"]
        for f in topology["findings"]
    )


def test_terraform_escaped_for_each_key_links_its_own_instance(tmp_path):
    # for_each = jsonencode(["a", "b"]): the key holds escaped quotes and a "]".
    key = 'aws_subnet.app["[\\"a\\",\\"b\\"]"]'
    topology = _counted_subnets(
        tmp_path, [key + ".id", key, "aws_subnet.app"], (key, 'aws_subnet.app["c"]')
    )
    subnets = [r["id"] for r in topology["resources"] if "subnet" in r["id"]]
    escaped = next(i for i in subnets if not i.endswith("app-c"))
    edges = {(e["source_id"], e["destination_id"]) for e in topology["relationships"]}
    assert edges == {("input-0-aws-instance-web", escaped)}
    assert not any("aws_subnet.app" in f["message"] for f in topology["findings"])


def test_terraform_malformed_reference_is_not_an_instance(tmp_path):
    """A malformed entry is parsed once and is no instance, so the bare `aws_subnet.app`
    after it is a reference of its own (and a finding), not an alias."""
    for malformed in ("aws_subnet[0].app", "aws_subnet.app" + "[" * 20000):
        topology = _counted_subnets(tmp_path, [malformed, "aws_subnet.app"])
        assert not topology["relationships"]
        assert any("aws_subnet.app fits 2" in f["message"] for f in topology["findings"])


def test_terraform_malformed_index_links_nothing(tmp_path):
    """`app[bogus]` is not a valid key, so it stays unresolved instead of falling back
    to the bare resource and linking its only instance."""
    topology = _counted_subnets(
        tmp_path, ["aws_subnet.app[bogus].id"], subnets=("aws_subnet.app[0]",)
    )
    assert not topology["relationships"]


def test_terraform_reference_matching_is_linear_in_plan_size(tmp_path, monkeypatch):
    """Each instance reference is looked up, not matched against every planned address
    or every other reference in its expression."""
    from architecture_suite import infrastructure

    count = 200
    doc = {
        "planned_values": {
            "root_module": {
                "resources": [
                    {"address": f"aws_subnet.app[{i}]", "type": "aws_subnet", "values": {}}
                    for i in range(count)
                ]
                + [
                    {"address": f"aws_instance.web{i}", "type": "aws_instance", "values": {}}
                    for i in range(count)
                ]
                + [{"address": "aws_lb.web", "type": "aws_lb", "values": {}}]
            }
        },
        "configuration": {
            "root_module": {
                "resources": [
                    {"address": f"aws_instance.web{i}",
                     "expressions": {"subnet_id": {"references": [
                         f"aws_subnet.app[{i}].id", f"aws_subnet.app[{i}]", "aws_subnet.app"
                     ]}}}
                    for i in range(count)
                ]
                + [
                    {"address": "aws_lb.web",
                     "expressions": {"subnets": {"references": [
                         ref
                         for i in range(count)
                         for ref in (f"aws_subnet.app[{i}].id", f"aws_subnet.app[{i}]", "aws_subnet.app")
                     ]}}}
                ]
            }
        },
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(doc))
    calls = []
    original = infrastructure._config_address
    monkeypatch.setattr(
        infrastructure, "_config_address", lambda address: calls.append(1) or original(address)
    )
    topology = import_infrastructure([path])
    assert len(topology["relationships"]) == 2 * count
    assert len(calls) < 10 * count


def test_cloudformation_getatt_and_sub_references(tmp_path):
    template = (
        "Resources:\n"
        "  Bucket:\n    Type: AWS::S3::Bucket\n"
        "  Role:\n    Type: AWS::IAM::Role\n"
        "  Queue:\n    Type: AWS::SQS::Queue\n"
        "  Fn:\n    Type: AWS::Lambda::Function\n    Properties:\n"
        "      Role: !GetAtt Role.Arn\n"
        "      Environment:\n        Variables:\n"
        "          BUCKET: !Sub 'arn:aws:s3:::${Bucket}/*'\n"
        "          REGION: !Sub '${AWS::Region}'\n"
        "  Fn2:\n    Type: AWS::Lambda::Function\n    Properties:\n"
        "      Role: {'Fn::GetAtt': [Role, Arn]}\n"
        "      Queue: {'Fn::Sub': ['${Q.Arn}', {Q: x}]}\n"
        "      Target: {'Fn::Sub': '${Queue.Arn}'}\n"
    )
    path = tmp_path / "template.yaml"
    path.write_text(template)
    edges = {
        (e["source_id"], e["destination_id"])
        for e in import_infrastructure([path])["relationships"]
        if e["kind"] == "explicit-reference"
    }
    assert edges == {
        ("input-0-fn", "input-0-role"),
        ("input-0-fn", "input-0-bucket"),
        ("input-0-fn2", "input-0-role"),
        ("input-0-fn2", "input-0-queue"),
    }


def test_unknown_participant_names_it_and_lists_valid_ids(scenario, model):
    bad = deepcopy(scenario)
    bad["participants"] = ["ghost"]
    with pytest.raises(ValueError) as caught:
        validate_scenario(bad, model)
    text = str(caught.value)
    assert "'ghost'" in text and "valid element ids:" in text
    assert model["elements"][0]["id"] in text
    assert text.count(",") <= 22  # the id list is capped


def test_scenario_render_format_is_case_insensitive(inputs, tmp_path, scenario):
    scenario_file = tmp_path / "scenario.json"
    scenario_file.write_text(json.dumps(scenario))
    out = tmp_path / "out"
    argv = ["scenario-render", "--model", str(inputs[0]), "--scenario", str(scenario_file),
            "--output", str(out), "--format", "Mermaid,SVG"]
    assert main(argv + ["--confirm-write"]) == 0
    assert (out / "scenario.mmd").is_file() and (out / "scenario.svg").is_file()


def test_extension_missing_file_names_the_flag(inputs, tmp_path, capsys):
    missing = tmp_path / "gone.json"
    assert main(["diff", "--before", str(missing), "--after", str(inputs[0]),
                 "--output", str(tmp_path / "d"), "--dry-run"]) == 2
    assert f"--before: no such file: {missing.resolve()}" in capsys.readouterr().err


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


def test_scenario_frame_ids_stay_out_of_the_element_id_namespace(model, nested):
    """A participant whose ID matches a synthetic frame ID keeps a box of its own."""
    model["elements"].append({"id": "group-4", "name": "Group 4", "type": "container"})
    nested["participants"].append("group-4")
    scene = scenario_scene(nested, model)
    ids = [b.id for b in scene.boxes]
    assert len(ids) == len(set(ids))
    assert next(b for b in scene.boxes if b.id == "group-4").role == "card"
    frames = [b for b in scene.boxes if b.role == "frame"]
    assert len(frames) == 4 and all(f.parent_id != "group-4" for f in frames)


def test_scenario_cards_clear_a_long_title_and_lifelines_start_at_the_card(model, scenario):
    model["elements"][1]["name"] = "A participant name long enough to wrap " * 4
    scenario["name"] = "A long scenario title that wraps over three lines " * 4
    scene = scenario_scene(scenario, model)
    assert len(scene.title_lines) >= 3
    cards = [b for b in scene.boxes if b.role == "card"]
    assert len({b.height for b in cards}) > 1 or cards[0].height > 80
    # The last title baseline sits at 65 + 33 * (lines - 1); cards start below its descent.
    title_bottom = 65 + 33 * (len(scene.title_lines) - 1) + 8
    assert all(b.y >= title_bottom and b.y >= scene.content_top for b in cards)
    for card in cards:
        lifeline = next(e for e in scene.edges if e.id == "lifeline-" + card.id)
        assert lifeline.points[0][1] == card.y + card.height
    short = scenario_scene({**scenario, "name": "Submit"}, model)
    assert min(b.y for b in short.boxes if b.role == "card") == 120


def test_scenario_branch_ids_stay_out_of_the_element_id_namespace(model, nested):
    """A participant whose ID matches a synthetic branch ID keeps a box of its own."""
    probe = scenario_scene(nested, model)
    # One more participant shifts every later box count by one.
    first = next(b.id for b in probe.boxes if b.role == "panel-title")
    branch = "branch-" + str(int(first.split("-")[1]) + 1)
    model["elements"].append({"id": branch, "name": "Branch", "type": "container"})
    nested["participants"].append(branch)
    scene = scenario_scene(nested, model)
    ids = [b.id for b in scene.boxes]
    assert len(ids) == len(set(ids))
    assert next(b for b in scene.boxes if b.id == branch).role == "card"
    assert len([b for b in scene.boxes if b.role == "panel-title"]) == 2


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


@pytest.mark.slow
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


def test_scenario_key_describes_messages(model, nested):
    from architecture_suite.emit import _key

    lines = _key(scenario_scene(nested, model))
    assert any(line.startswith("Arrow = message") for line in lines)
    assert not any("directed dependency" in line for line in lines)


def test_check_reports_each_flow_once_per_rule(model):
    rules = {"rules": [{"id": "no-store", "effect": "deny", "destination": {"ids": ["order-store"]}}]}
    findings = check_rules(model, rules)["findings"]
    # One flow, projected into container, component and code views, is one finding at
    # its most specific level.
    assert [(f["source"], f["destination"]) for f in findings] == [("fulfillmentjob", "order-store")]
    flows = {f for r in model["relationships"] for f in r["flow_ids"]}
    assert len(check_rules(model, {"rules": [{"id": "all", "effect": "deny"}]})["findings"]) == len(flows)


def test_check_tag_selectors_need_every_listed_tag(model):
    tagged = deepcopy(model)
    next(e for e in tagged["elements"] if e["id"] == "api")["tags"] = ["pci"]

    def found(tags):
        rule = {"id": "pci", "effect": "deny", "source": {"tags": tags}}
        return check_rules(tagged, {"rules": [rule]})["findings"]

    assert found(["pci"]) and not found(["pci", "public"])


def test_markdown_reports_are_readable_tables(model):
    after = deepcopy(model)
    next(e for e in after["elements"] if e["id"] == "api")["technology"] = "Go | HTTPS"
    diff = markdown_report(diff_models(model, after))
    assert "```" not in diff and diff.startswith("# Architecture diff\n")
    assert "| elements | api | changed | technology: Python HTTPS -> Go \\| HTTPS |" in diff
    assert "No architecture changes." in markdown_report(diff_models(model, model))
    rules = {"rules": [{"id": "no-store", "effect": "deny", "destination": {"ids": ["order-store"]}}]}
    check = markdown_report(check_rules(model, rules))
    assert "```" not in check and check.startswith("# Architecture check\n")
    assert "| no-store | fulfillmentjob | order-store | error | new |" in check
    assert "No rule findings." in markdown_report(check_rules(model, {"rules": []}))


def test_lint_flags_flows_hidden_in_a_decomposed_scope(plan):
    hidden = deepcopy(plan)
    hidden["flows"].append(
        {"from": "API", "to": "Payment Provider", "description": "Refunds", "evidence": "brief"}
    )
    found = [f for f in lint_plan(hidden) if f.code == "hidden-flow"]
    assert [f.where for f in found] == [str(len(hidden["flows"]) - 1)]
    assert "API" in found[0].message and found[0].severity == "advisory"
    assert not [f for f in lint_plan(plan) if f.code == "hidden-flow"]


def _kubernetes(tmp_path, docs):
    path = tmp_path / "k8s.yaml"
    path.write_text("\n---\n".join(json.dumps(d) for d in docs), encoding="utf-8")
    return import_infrastructure([path])


def test_kubernetes_and_compose_environment_secrets_are_redacted(tmp_path):
    env = [{"name": "DB_PASSWORD", "value": "hunter2"}, {"name": "MODE", "value": "prod"}]
    topology = _kubernetes(
        tmp_path,
        [
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "api"},
                "spec": {"template": {"spec": {"containers": [{"name": "api", "env": env}]}}},
            }
        ],
    )
    payload = json.dumps(topology) + json.dumps(topology_plan(topology))
    assert "hunter2" not in payload and "prod" in payload
    # Compose list form: values under 4 characters slip past redact().
    path = tmp_path / "compose.yaml"
    path.write_text(
        json.dumps(
            {"services": {"api": {"environment": ["API_TOKEN=pw1", "auth.token=xyz", "MODE=dev"]}}}
        ),
        encoding="utf-8",
    )
    topology = import_infrastructure([path])
    payload = json.dumps(topology) + json.dumps(topology_plan(topology))
    assert "pw1" not in payload and "API_TOKEN=[REDACTED]" in payload and "MODE=dev" in payload
    assert "xyz" not in payload and "auth.token=[REDACTED]" in payload


def test_url_query_token_is_not_an_assignment_key(tmp_path):
    """`?token=` inside a URL is not a Compose `KEY=value`; the URL password is redacted."""
    url = "redis://app:pw9secret@cache/0?token=x"
    path = tmp_path / "compose.yaml"
    path.write_text(
        json.dumps({"services": {"api": {"environment": {"CACHE_URL": url}}}}), encoding="utf-8"
    )
    compose = import_infrastructure([path])
    env = [{"name": "CACHE_URL", "value": url}]
    pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "api"},
           "spec": {"containers": [{"name": "api", "env": env}]}}
    for topology in (compose, _kubernetes(tmp_path, [pod])):
        payload = json.dumps(topology) + json.dumps(topology_plan(topology))
        assert "pw9secret" not in payload and "cache/0" in payload


def test_env_value_rule_keeps_cloudformation_references(tmp_path):
    """A `name`/`value` pair whose value is an expression is recursed into, not redacted."""
    doc = {
        "Resources": {
            "SharedSetting": {"Type": "AWS::SSM::Parameter"},
            "Provider": {
                "Type": "Custom::Provider",
                "Properties": {"name": "tokenProvider", "value": {"Ref": "SharedSetting"}},
            },
        }
    }
    path = tmp_path / "stack.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    topology = import_infrastructure([path])
    edges = {(e["source_id"], e["destination_id"]) for e in topology["relationships"]}
    assert edges == {("input-0-provider", "input-0-sharedsetting")}
    assert {
        "resource": "input-0-provider",
        "message": "Contains unresolved expression; no values or placement guessed",
    } in topology["findings"]


@pytest.mark.parametrize(
    "value",
    [
        {"Fn::Join": ["", ["s3cr3tpart-", {"Ref": "SharedSetting"}]]},
        {
            "intrinsic": "Join",
            "expression": ["", ["s3cr3tpart-", {"intrinsic": "Ref", "expression": "SharedSetting"}]],
        },
        {"Fn::Sub": "s3cr3tpart-${SharedSetting}"},
        {"Fn::Sub": ["s3cr3tpart-${Other}", {"Other": {"Ref": "SharedSetting"}}]},
        {"intrinsic": "Sub", "expression": "s3cr3tpart-${SharedSetting}"},
        {"Fn::Join": ["", ["s3cr3tpart-", {"Fn::GetAtt": ["SharedSetting", "Value"]}]]},
    ],
)
def test_env_value_expression_under_a_secret_name_hides_literals(tmp_path, value):
    """Literal operands are redacted; reference targets stay, so the edge and finding survive."""
    doc = {
        "Resources": {
            "SharedSetting": {"Type": "AWS::SSM::Parameter"},
            "Provider": {
                "Type": "Custom::Provider",
                "Properties": {"name": "clientSecret", "value": value},
            },
        }
    }
    path = tmp_path / "stack.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    topology = import_infrastructure([path])
    payload = json.dumps(topology) + json.dumps(topology_plan(topology))
    assert "s3cr3tpart" not in payload
    edges = {(e["source_id"], e["destination_id"]) for e in topology["relationships"]}
    assert edges == {("input-0-provider", "input-0-sharedsetting")}
    assert any(f.get("resource") == "input-0-provider" for f in topology["findings"])


def test_kubernetes_pods_ingress_and_service_findings(tmp_path):
    topology = _kubernetes(
        tmp_path,
        [
            {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "web", "labels": {"app": "web"}}, "spec": {}},
            {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "web-svc"}, "spec": {"selector": {"app": "web"}}},
            {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "lonely"}, "spec": {"selector": {"app": "none"}}},
            {
                "apiVersion": "networking.k8s.io/v1",
                "kind": "Ingress",
                "metadata": {"name": "front"},
                "spec": {
                    "defaultBackend": {"service": {"name": "web-svc", "port": {"number": 80}}},
                    "rules": [{"http": {"paths": [{"path": "/", "backend": {"service": {"name": "lonely"}}}]}}],
                },
            },
        ],
    )
    edges = sorted(
        (e["source_id"][16:], e["destination_id"][16:], e["kind"]) for e in topology["relationships"]
    )
    assert edges == [
        ("ingress-front", "service-lonely", "ingress-backend"),
        ("ingress-front", "service-web-svc", "ingress-backend"),
        ("service-web-svc", "pod-web", "selector"),
    ]
    messages = {f["message"] for f in topology["findings"]}
    assert "Service selector app=web matched: input-0-default-pod-web" in messages
    assert "Service selector app=none matched no workload in namespace default" in messages
    assert not any("requires workload label resolution" in m for m in messages)


def test_kubernetes_null_fields_are_not_attribute_errors(tmp_path):
    topology = _kubernetes(
        tmp_path,
        [
            {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "api"}, "spec": {"template": None}},
            {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "jobs"},
             "spec": {"template": {"metadata": {"labels": None}}}},
            {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "api", "labels": None}, "spec": {"selector": {"app": "api"}}},
            {"apiVersion": "v1", "kind": "Pod", "metadata": None, "spec": None},
            {"apiVersion": "v1", "kind": "List", "items": [None]},
            {"apiVersion": "networking.k8s.io/v1", "kind": "Ingress", "metadata": {"name": "bare"},
             "spec": {"rules": [{"host": "a.example"}, {"http": {"paths": None}}, None]}},
        ],
    )
    assert not [e for e in topology["relationships"] if e["kind"] == "selector"]
    assert any(f["message"].endswith("matched no workload in namespace default") for f in topology["findings"])


def test_inventory_route_methods_and_registrations():
    report = dependency_inventory(
        {
            "Users.java": '@RequestMapping("/api/users")\nclass Users {\n @GetMapping("/{id}")\n'
            ' User get() {}\n @DeleteMapping("/{id}")\n void remove() {}\n @PutMapping("/{id}")\n void put() {}\n}',
            "app.py": '@app.route("/health")\ndef health(): pass\n@router.post("/items")\ndef create(): pass\n',
            "Orders.cs": '[Route("api/orders")]\npublic class Orders {\n [HttpPatch("{id}")]\n public void Patch() {}\n}',
            "main.go": 'package main\nfunc main(){\n http.Handle("/static/", fs)\n mux.HandleFunc("/mux", h)\n'
            ' mux.HandleFunc("POST /orders", h)\n http.HandleFunc("example.com/health", h)\n'
            ' http.HandleFunc("HEAD /ping", h)\n}',
            "App.kt": "import com.example.Worker\nfun run() { Worker() }",
            "Worker.kt": "class Worker",
        }
    )
    routes = sorted((r["reference"], r["path"], r["method"] or "") for r in report["routes"])
    assert routes == [
        ("Orders.cs", "api/orders", ""),
        ("Orders.cs", "{id}", "PATCH"),
        ("Users.java", "/api/users", ""),
        ("Users.java", "/{id}", "DELETE"),
        ("Users.java", "/{id}", "GET"),
        ("Users.java", "/{id}", "PUT"),
        ("app.py", "/health", ""),
        ("app.py", "/items", "POST"),
        ("main.go", "/mux", ""),
        ("main.go", "/orders", "POST"),
        ("main.go", "/ping", "HEAD"),
        ("main.go", "/static/", ""),
        ("main.go", "example.com/health", ""),
    ]
    kotlin = [r for r in report["references"] if r["kind"] == "import" and r["reference"] == "App.kt"]
    assert kotlin and kotlin[0].get("resolved_file") == "Worker.kt"


@pytest.mark.parametrize(
    "value",
    [
        {"intrinsic": "Ref", "expression": "SharedSetting", "password": "s3cr3tpart"},
        {"intrinsic": {"nested": "s3cr3tpart"}, "expression": "SharedSetting"},
        {"intrinsic": ["s3cr3tpart"], "data": "s3cr3tpart"},
        {"Ref": {"password": "s3cr3tpart"}},
        {"intrinsic": "Ref", "expression": {"password": "s3cr3tpart"}},
    ],
)
def test_reference_shaped_data_under_a_secret_name_is_masked(tmp_path, value):
    """Only exact short forms and plain reference operands are kept; other data is masked."""
    doc = {
        "Resources": {
            "SharedSetting": {"Type": "AWS::SSM::Parameter"},
            "Provider": {
                "Type": "Custom::Provider",
                "Properties": {"name": "clientSecret", "value": value},
            },
        }
    }
    path = tmp_path / "stack.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    topology = import_infrastructure([path])
    assert "s3cr3tpart" not in json.dumps(topology) + json.dumps(topology_plan(topology))


def test_diff_ignores_reordered_parallel_relationships(model):
    base = model["relationships"][0]
    reads = {**base, "id": "rel-reads", "description": "reads orders"}
    writes = {**base, "id": "rel-writes", "description": "writes orders"}
    before = deepcopy(model)
    before["relationships"] = [reads, writes]
    swapped = deepcopy(before)
    swapped["relationships"] = [writes, reads]
    assert not diff_models(before, swapped)["changed"]
    edited = deepcopy(before)
    edited["relationships"][1] = {**writes, "description": "updates orders"}
    changes = diff_models(before, edited)["changes"]
    assert [(c["section"], c["kind"]) for c in changes] == [("relationships", "changed")]
    assert changes[0]["before"]["description"] == "writes orders"
    assert changes[0]["after"]["description"] == "updates orders"


@pytest.mark.parametrize(
    "value",
    [
        {"Fn::GetAtt": ["Database", {"Ref": "AttrName"}]},
        {"Fn::GetAtt": ["Database", {"Fn::Join": ["", ["s3cr3t", {"Ref": "AttrName"}]]}]},
        {"intrinsic": "GetAtt", "expression": ["Database", {"Ref": "AttrName"}]},
    ],
)
def test_getatt_with_a_dynamic_attribute_keeps_its_resource_under_a_secret_name(tmp_path, value):
    """The resource name of a GetAtt stays an edge; only the attribute expression is masked."""
    doc = {
        "Parameters": {"AttrName": {"Type": "String"}},
        "Resources": {
            "Database": {"Type": "AWS::RDS::DBInstance"},
            "Service": {
                "Type": "Custom::Service",
                "Properties": {"env": [{"name": "DB_PASSWORD", "value": value}]},
            },
        },
    }
    path = tmp_path / "stack.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    topology = import_infrastructure([path])
    edges = {(e["source_id"], e["destination_id"]) for e in topology["relationships"]}
    assert ("input-0-service", "input-0-database") in edges
    assert "s3cr3t" not in json.dumps(topology) + json.dumps(topology_plan(topology))


def test_terraform_malformed_index_is_a_finding_for_its_resource(tmp_path):
    """A rejected instance key gives no edge but one finding, so the plan has a gap."""
    reference = "aws_subnet.app[bogus].id"
    topology = _counted_subnets(tmp_path, [reference], subnets=("aws_subnet.app[0]",))
    assert not topology["relationships"]
    found = [f for f in topology["findings"] if reference in f["message"]]
    assert len(found) == 1 and found[0]["resource"] == "input-0-aws-instance-web"
    assert found[0]["message"] in topology_plan(topology)["gaps"]
    # Non-resource roots such as `var.x[bogus]` are not resource references.
    topology = _counted_subnets(tmp_path, ["var.names[bogus]"])
    assert not any("var.names" in f["message"] for f in topology["findings"])


def _resolved_id_plan(tmp_path, count):
    """`count` subnets (every seventh shares an ID with its neighbour) and `count`
    instances that name the subnet ID `(i * 7) % count`, plus one in a tag."""
    subnet_id = lambda i: f"subnet-{i // 2 * 2:06d}" if i % 7 == 0 else f"subnet-{i:06d}"  # noqa: E731
    resources = [
        {"address": f"aws_subnet.s{i}", "type": "aws_subnet", "values": {"id": subnet_id(i)}}
        for i in range(count)
    ] + [
        {
            "address": f"aws_instance.w{i}",
            "type": "aws_instance",
            "values": {
                "id": f"i-{i:06d}",
                "subnet_id": subnet_id((i * 7) % count),
                "tags": {"note": subnet_id(i)},
            },
        }
        for i in range(count)
    ]
    path = tmp_path / f"plan-{count}.json"
    path.write_text(json.dumps({"planned_values": {"root_module": {"resources": resources}}}))
    return path, subnet_id


def test_resolved_id_edges_match_a_brute_force_search(tmp_path):
    count = 120
    path, subnet_id = _resolved_id_plan(tmp_path, count)
    edges = import_infrastructure([path])["relationships"]
    ids = [subnet_id(i) for i in range(count)]
    expected = [
        (f"input-0-aws-instance-w{i}", f"input-0-aws-subnet-s{j}")
        for i in range(count)
        for j in range(count)
        if ids[j] == subnet_id((i * 7) % count) and ids.count(ids[j]) == 1
    ]
    assert [(e["source_id"], e["destination_id"]) for e in edges] == expected
    assert expected and {e["kind"] for e in edges} == {"resolved-resource-id"}


def test_resolved_id_edges_skip_placeholders_shared_ids_and_links(tmp_path):
    def resource(name, values):
        return {"address": name, "type": name.split(".")[0], "values": values}

    plan = {
        "planned_values": {
            "root_module": {
                "resources": [
                    resource("aws_vpc.main", {"id": "vpc-1"}),
                    resource("aws_subnet.a", {"id": "subnet-a", "vpc_id": "vpc-1"}),
                    resource("aws_subnet.b", {"id": "subnet-b", "vpc_id": "vpc-1"}),
                    resource("aws_bucket.one", {"id": "shared"}),
                    resource("aws_bucket.two", {"id": "shared"}),
                    resource("aws_instance.web", {"id": "i-1", "subnet": "subnet-a", "bucket": "shared"}),
                    resource("aws_instance.db", {"id": "[UNKNOWN AFTER APPLY]", "peer": "[UNKNOWN AFTER APPLY]"}),
                    resource("aws_instance.tagged", {"id": "i-2", "tags": {"vpc": "vpc-1"}, "self": "i-2"}),
                ]
            }
        },
        "configuration": {
            "root_module": {
                "resources": [
                    {"address": "aws_subnet.b", "expressions": {"vpc_id": {"references": ["aws_vpc.main.id", "aws_vpc.main"]}}}
                ]
            }
        },
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    edges = import_infrastructure([path])["relationships"]
    assert [(e["source_id"][8:], e["destination_id"][8:], e["kind"]) for e in edges] == [
        ("aws-subnet-b", "aws-vpc-main", "explicit-reference"),
        ("aws-subnet-a", "aws-vpc-main", "resolved-resource-id"),
        ("aws-instance-web", "aws-subnet-a", "resolved-resource-id"),
    ]


def test_duplicate_infrastructure_resource_is_still_rejected(tmp_path):
    path = tmp_path / "stack.yaml"
    path.write_text(chr(10).join(["services:", "  api: {}", "---", "services:", "  api: {}"]))
    with pytest.raises(ValueError, match="Duplicate infrastructure resource: input-0-api"):
        import_infrastructure([path])
    path.write_text(chr(10).join(["services:", "  api: {}", "  web: {}"]))
    assert [r["id"] for r in import_infrastructure([path])["resources"]] == ["input-0-api", "input-0-web"]


def _timed_import(path):
    import time

    start = time.perf_counter()
    topology = import_infrastructure([path])
    return topology, time.perf_counter() - start


def test_large_plan_import_is_not_quadratic(tmp_path):
    """400 resources with resolved-ID references import quickly (about 0.3 s)."""
    path, _ = _resolved_id_plan(tmp_path, 200)
    topology, seconds = _timed_import(path)
    assert len(topology["resources"]) == 400 and topology["relationships"]
    assert seconds < 5


@pytest.mark.slow
def test_plan_of_2500_resources_imports_in_seconds(tmp_path):
    """Matching resolved IDs and checking duplicates used to scan every resource for each
    reference: 6.25 times the resources took about 26 times as long (0.3 s to 8 s); now
    about 6 times. The ratio holds under coverage and parallel runs, a wall time does not."""
    small, _ = _resolved_id_plan(tmp_path, 200)
    path, _ = _resolved_id_plan(tmp_path, 1250)
    _, base = _timed_import(small)
    topology, seconds = _timed_import(path)
    assert len(topology["resources"]) == 2500 and len(topology["relationships"]) > 500
    assert seconds / base < 15


@pytest.mark.parametrize(
    "value",
    [
        {"Ref": "hunter2"},
        {"Fn::GetAtt": ["hunter2", "Arn"]},
        {"Fn::GetAtt": "hunter2.Arn"},
        {"intrinsic": "Ref", "expression": "hunter2"},
        {"intrinsic": "GetAtt", "expression": "hunter2.Arn"},
        {"DependsOn": ["hunter2"]},
        {"DependsOn": ["Db", "hunter2"]},
    ],
)
def test_reference_to_an_undeclared_name_under_a_secret_name_is_masked(tmp_path, value):
    doc = {
        "Resources": {
            "Db": {"Type": "AWS::RDS::DBInstance"},
            "Service": {
                "Type": "Custom::Service",
                "Properties": {"env": [{"name": "DB_PASSWORD", "value": value}]},
            },
        }
    }
    path = tmp_path / "stack.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    topology = import_infrastructure([path])
    assert "hunter2" not in json.dumps(topology) + json.dumps(topology_plan(topology))


def test_declared_references_under_a_secret_name_stay_readable(tmp_path):
    doc = {
        "Parameters": {"DbPassword": {"Type": "String"}},
        "Resources": {
            "Db": {"Type": "AWS::RDS::DBInstance"},
            "Service": {
                "Type": "Custom::Service",
                "Properties": {
                    "env": [
                        {"name": "DB_PASSWORD", "value": {"Ref": "DbPassword"}},
                        {"name": "DB_TOKEN", "value": {"Ref": "AWS::Region"}},
                        {"name": "DB_SECRET", "value": {"Ref": "Db"}},
                    ]
                },
            },
        },
    }
    path = tmp_path / "stack.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    topology = import_infrastructure([path])
    text = json.dumps(topology)
    assert '"Ref": "DbPassword"' in text and '"Ref": "AWS::Region"' in text
    assert [(e["source_id"][8:], e["destination_id"][8:]) for e in topology["relationships"]] == [
        ("service", "db")
    ]


def test_getatt_under_a_secret_name_masks_a_name_that_declares_nothing(tmp_path):
    """Only a declared resource name survives masking; other text in a sensitive value does not."""
    doc = {
        "Parameters": {"AttrName": {"Type": "String"}},
        "Resources": {
            "Service": {
                "Type": "Custom::Service",
                "Properties": {
                    "env": [
                        {
                            "name": "DB_PASSWORD",
                            "value": {"Fn::GetAtt": ["hunter2literal", {"Ref": "AttrName"}]},
                        }
                    ]
                },
            },
        },
    }
    path = tmp_path / "stack.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    topology = import_infrastructure([path])
    assert "hunter2literal" not in json.dumps(topology) + json.dumps(topology_plan(topology))


def test_terraform_object_ids_are_ignored_for_resolved_id_matching(tmp_path):
    """An object or list in `values.id` neither aborts the import nor identifies anything."""
    doc = {
        "planned_values": {
            "root_module": {
                "resources": [
                    {"address": "aws_thing.a", "type": "aws_thing", "values": {"id": {"x": 1}}},
                    {"address": "aws_thing.b", "type": "aws_thing", "values": {"id": ["y"]}},
                    {"address": "aws_subnet.s", "type": "aws_subnet", "values": {"id": "subnet-1"}},
                    {"address": "aws_instance.i", "type": "aws_instance", "values": {"subnet_id": "subnet-1"}},
                ]
            }
        }
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    topology = import_infrastructure([path])
    edges = {(e["source_id"], e["destination_id"]) for e in topology["relationships"]}
    assert ("input-0-aws-instance-i", "input-0-aws-subnet-s") in edges
