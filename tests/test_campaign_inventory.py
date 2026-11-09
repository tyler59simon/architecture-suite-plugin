"""Inventory and plan-draft regressions: redaction after parsing, parse gaps, Kotlin names."""

import json

from architecture_suite.analyzer import analyze_repository, draft_plan
from architecture_suite.inventory import dependency_inventory
from architecture_suite.safety import scan_repository

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
