"""plan-draft container candidates on repositories without (or with partial) packaging manifests.

The fixture mirrors a layout that used to go wrong: no top-level manifest, a core package,
hook scripts, integration installers that happen to be named setup.py, root entry points and
a tests folder. Previously the two setup.py installers became the only containers and core/,
hooks/ and the entry points were dropped.
"""

from architecture_suite.analyzer import _is_manifest, analyze_repository, draft_plan
from architecture_suite.safety import scan_repository

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
