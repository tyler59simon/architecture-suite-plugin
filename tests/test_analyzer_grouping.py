"""plan-draft container candidates on repositories without (or with partial) packaging manifests.

The fixture mirrors a layout that used to go wrong: no top-level manifest, a core package,
hook scripts, integration installers that happen to be named setup.py, root entry points and
a tests folder. Previously the two setup.py installers became the only containers and core/,
hooks/ and the entry points were dropped.
"""

import json
import time

import pytest
from architecture_suite.analyzer import _is_manifest, analyze_repository, draft_plan
from architecture_suite.inventory import dependency_inventory
from architecture_suite.model import validate_model
from architecture_suite.plan import errors, lint_plan
from architecture_suite.safety import redact, scan_repository

INSTALLER = (
    '"""Adapter setup."""\nimport argparse\nfrom core.repository import read\n'
    "def main():\n    return read()\n"
)


def build_repo(root):
    files = {
        "notes.py": "from core.cli import main\nmain()\n",
        "install.py": "import integrations.setup\n",
        "core/__init__.py": "",
        "core/cli.py": "from core.repository import read\ndef main():\n    return read()\n",
        "core/repository.py": "def read():\n    return {}\n",
        "hooks/claude_hooks.py": "from core.cli import main\ndef run():\n    return main()\n",
        "hooks/codex_hooks.py": "def run():\n    return 1\n",
        "integrations/setup.py": INSTALLER,
        "integrations/copilot/setup.py": INSTALLER,
        "tests/test_core.py": "def test_read():\n    assert True\n",
        "README.md": "# Notes service\n",
    }
    for path, text in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def containers(plan):
    return {c["name"].rsplit(" ", 1)[-1]: c for c in plan["containers"]}


def test_setup_py_is_a_manifest_only_with_setuptools():
    assert _is_manifest("pyproject.toml", "")
    assert _is_manifest("setup.py", "from setuptools import setup\nsetup()\n")
    assert _is_manifest("setup.py", "import distutils.core\n")
    assert not _is_manifest("setup.py", INSTALLER)


def test_manifestless_repo_groups_by_top_level_folder(tmp_path):
    repo = build_repo(tmp_path / "notes-service")
    plan = draft_plan(repo, scan_repository(repo), "Internal")
    found = containers(plan)
    assert set(found) == {"Application", "core", "hooks", "integrations"}
    components = {c["evidence"].split(":")[0] for c in found["Application"]["components"]}
    assert components == {"install.py", "notes.py"}
    assert {c["evidence"].split(":")[0] for c in found["integrations"]["components"]} == {
        "integrations/setup.py",
        "integrations/copilot/setup.py",
    }
    assert "no packaging manifest" in found["core"]["description"]
    assert any("No recognized manifest" in g for g in plan["gaps"])
    assert any("tests/" in g for g in plan["gaps"])
    assert not any("test_core" in c["name"] for f in found.values() for c in f["components"])
    assert any(f["description"] == "Imports source module" for f in plan["flows"])


def test_uncovered_source_beside_a_manifest_is_kept(tmp_path):
    repo = build_repo(tmp_path / "repo")
    (repo / "core/pyproject.toml").write_text("[project]\nname = 'core'\n")
    plan = draft_plan(repo, scan_repository(repo), "Internal")
    found = containers(plan)
    assert found["core"]["description"].startswith("Candidate Python application from core/")
    assert {"Application", "hooks", "integrations"} <= set(found)
    gap = next(g for g in plan["gaps"] if "grouped by top-level folder" in g)
    assert "hooks/" in gap and "repository root" in gap
    model, _ = analyze_repository(repo, profile="container")
    assert len([e for e in model["elements"] if e["type"] == "container"]) == 4


def test_tests_under_a_manifest_root_are_not_components(tmp_path):
    repo = tmp_path / "shop"
    for path, text in {
        "pyproject.toml": "[project]\nname = 'shop'\n",
        "app/main.py": "def main():\n    return 1\n",
        "tests/test_app.py": "def test_app():\n    assert True\n",
        "app/tests/test_unit.py": "def test_unit():\n    assert True\n",
    }.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text, encoding="utf-8")
    plan = draft_plan(repo, scan_repository(repo), "Internal")
    evidence = {
        component["evidence"].split(":")[0]
        for container in plan["containers"]
        for component in container["components"]
    }
    assert evidence == {"app/main.py"}
    # Drafted boundaries are interpretations; declarations were read from source.
    assert {c["status"] for c in plan["containers"]} == {"inferred"}
    components = [x for c in plan["containers"] for x in c["components"]]
    assert {x["status"] for x in components} == {"inferred"}
    assert {d["status"] for x in components for d in x["code"]} == {"observed"}
    assert "Test code under app/tests/, tests/ is not modeled as containers." in plan["gaps"]


SECRET = "sk_live_abc123def456"
CATALOG = (
    "from fastapi import FastAPI\n"
    "app = FastAPI()\n"
    f'API_KEY = "{SECRET}"\n'
    '@app.get("/products")\n'
    "def list_products():\n"
    "    return []\n"
    'def connect(password="hunter2secret"):\n'
    "    return password\n"
)
KOTLIN = (
    "package shop.jobs\n"
    "interface Store { fun load(id: String): String }\n"
    "class ReconcileJob {\n"
    "    fun run(batch: Int): Int = batch\n"
    "}\n"
    "object Registry { fun ping() {} }\n"
)


def write(root, files):
    for path, text in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def code(plan):
    return {
        item["name"].rsplit(" ", 1)[-1]: item
        for container in plan["containers"]
        for component in container.get("components", [])
        for item in component["code"]
    }


def test_secret_line_does_not_break_parsing(tmp_path):
    repo = write(tmp_path / "repo", {"pyproject.toml": "", "catalog/main.py": CATALOG})
    scan = scan_repository(repo)
    assert SECRET not in scan.texts["catalog/main.py"]
    report = dependency_inventory(scan.texts)
    assert {"list_products", "connect"} <= {d["name"] for d in report["declarations"]}
    assert [r["path"] for r in report["routes"]] == ["/products"]
    assert not report["findings"]
    plan = draft_plan(repo, scan, "Internal")
    found = code(plan)
    assert found["list_products"]["evidence"] == "catalog/main.py:5"
    assert "REDACTED" in found["connect"]["members"][0]
    model, _ = analyze_repository(repo)
    for output in (report, plan, model):
        text = json.dumps(output)
        assert SECRET not in text and "hunter2secret" not in text


def test_credentialed_broker_urls_are_inventoried_with_the_password_masked(tmp_path):
    config = (
        'CACHE = "redis://:cachepass9@cache:6379/0"\n'
        'QUEUE = "amqp://guest:queuepass9@mq:5672/"\n'
    )
    repo = write(tmp_path / "repo", {"pyproject.toml": "", "app/settings.py": config})
    scan = scan_repository(repo)
    # Raw texts too: the recorded target is masked even when the caller did not scan.
    for texts in (scan.texts, {"app/settings.py": config}):
        report = dependency_inventory(texts)
        assert [(c["target"], c["line"]) for c in report["connections"]] == [
            ("redis://[REDACTED]@cache:6379/0", 1),
            ("amqp://[REDACTED]@mq:5672/", 2),
        ]
        text = json.dumps(report)
        assert "cachepass9" not in text and "queuepass9" not in text


def test_secret_assigned_and_odd_userinfo_urls_never_leak_through_the_inventory(tmp_path):
    config = (
        "PASSWORD=redis://u:assignpw1@host:6379\n"
        "token: amqp://u:colonpw12@mq:5672\n"
        "A=redis://u:apo'strophe1@cache:6379\n"
        "B=redis://u:at@sign9tail@cache:6379\n"
    )
    repo = write(tmp_path / "repo", {"pyproject.toml": "", "app/settings.txt": config})
    for texts in (scan_repository(repo).texts, {"app/settings.txt": config}):
        text = json.dumps(dependency_inventory(texts))
        for leaked in ("assignpw1", "colonpw12", "apo", "strophe1", "at@sign9", "sign9tail"):
            assert leaked not in text, leaked


def test_uri_redaction_is_linear_on_adversarial_input():
    cases = (
        "a:" * 50_000,
        "@" * 50_000,
        "http://" + "a:" * 25_000,
        "http://a:" + "@" * 50_000,
        "redis://" + "a:" * 25_000 + "x",
        "http://a:" * 6_000,
        "http://" * 8_000,
        "password" + " " * 50_000,
    )
    for case in cases:
        started = time.perf_counter()
        redact(case)
        assert time.perf_counter() - started < 0.5, case[:20]
    assert redact("redis://u:pw@cache:6379/0") == "redis://[REDACTED]@cache:6379/0"


def test_url_assigned_to_a_secret_name_stays_out_of_the_inventory(tmp_path):
    """The scanner redacts the whole `WEBHOOK_SECRET = "<url>"`; the URL must not return."""
    url = "https://hooks.example.com/services/T000/B000/abc123secret"
    config = f'WEBHOOK_SECRET = "{url}"\n'
    repo = write(tmp_path / "repo", {"pyproject.toml": "", "app/settings.py": config})
    text = json.dumps(dependency_inventory(scan_repository(repo).texts))
    assert "abc123secret" not in text and "hooks.example.com" not in text


def test_connection_lines_survive_a_redaction_that_spans_a_newline(tmp_path):
    config = (
        '{\n  "password":\n    "hunter2",\n  "name": "app",\n'
        '  "api": "https://api.example.com/v1"\n}\n'
    )
    repo = write(tmp_path / "repo", {"pyproject.toml": "", "config.json": config})
    scan = scan_repository(repo)
    assert scan.texts["config.json"].count("\n") == config.count("\n")
    report = dependency_inventory(scan.texts)
    assert [(c["target"], c["line"]) for c in report["connections"]] == [
        ("https://api.example.com/v1", 5)
    ]
    assert "hunter2" not in json.dumps(report)


def test_python_syntax_error_is_a_plan_gap(tmp_path):
    repo = write(tmp_path / "repo", {"pyproject.toml": "", "broken.py": "x = 1\ndef f(:\n"})
    scan = scan_repository(repo)
    assert dependency_inventory(scan.texts)["findings"]
    plan = draft_plan(repo, scan, "Internal")
    assert "broken.py:2: Python syntax error; declarations not inventoried." in plan["gaps"]


def test_kotlin_declarations_have_names_scope_and_parameters(tmp_path):
    report = dependency_inventory({"Job.kt": KOTLIN})
    assert {(d["name"], d["kind"]) for d in report["declarations"]} == {
        ("Store", "class_declaration"),
        ("load", "function_declaration"),
        ("ReconcileJob", "class_declaration"),
        ("run", "function_declaration"),
        ("Registry", "object_declaration"),
        ("ping", "function_declaration"),
    }
    repo = write(tmp_path / "repo", {"build.gradle.kts": "", "src/Job.kt": KOTLIN})
    found = code(draft_plan(repo, scan_repository(repo), "Internal"))
    assert found["ReconcileJob.run"]["members"] == ["+run(batch: Int)"]
    assert found["Store.load"]["members"] == ["+load(id: String)"]
    assert found["Registry.ping"]["members"] == ["+ping()"]


OVERLOADS = {
    "pom.xml": (
        "App.java",
        "public class App {\n"
        "    public void process(int x) {}\n"
        "    public void process(String s) {}\n"
        "    public void other() {}\n"
        "}\n",
    ),
    "app.csproj": (
        "App.cs",
        "public class App {\n"
        "    public void Process(int x) {}\n"
        "    public void Process(string s) {}\n"
        "}\n",
    ),
}


@pytest.mark.parametrize("manifest", sorted(OVERLOADS))
def test_overloaded_methods_become_one_code_element(tmp_path, manifest):
    source, text = OVERLOADS[manifest]
    repo = write(tmp_path / "repo", {manifest: "", source: text})
    plan = draft_plan(repo, scan_repository(repo), "Internal")
    assert not errors(lint_plan(plan))
    name = "App.process" if source.endswith(".java") else "App.Process"
    element = code(plan)[name]
    assert len(element["members"]) == 2
    assert element["evidence"] == [f"{source}:2", f"{source}:3"]
    model, _ = analyze_repository(repo)
    assert not validate_model(model)


def test_inventory_keeps_the_host_of_a_compact_json_url_and_lists_tls_schemes():
    config = (
        '{"cache":"redis://u:pw9@cache:6379","owner":"ops@example.com"}\n'
        "DB = postgresql://app:s3cret9@db:5432/orders\n"
        "TLS_CACHE = rediss://u:pw9@tls-cache:6380\n"
        "TLS_QUEUE = amqps://u:pw9@mq:5671\n"
    )
    targets = [c["target"] for c in dependency_inventory({"app.cfg": config})["connections"]]
    assert targets == [
        "redis://[REDACTED]@cache:6379",
        "postgresql://[REDACTED]@db:5432/orders",
        "rediss://[REDACTED]@tls-cache:6380",
        "amqps://[REDACTED]@mq:5671",
    ]
    assert "pw9" not in json.dumps(targets) and "s3cret9" not in json.dumps(targets)
