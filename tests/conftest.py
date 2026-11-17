import sys
from pathlib import Path
import json
import pytest
from architecture_suite.examples import example_model, example_plan
from architecture_suite.plan import render_plan


@pytest.fixture
def model():
    return example_model()


@pytest.fixture
def plan():
    return example_plan()


@pytest.fixture
def inputs(tmp_path, model, plan):
    m = tmp_path / "model.json"
    p = tmp_path / "plan.md"
    m.write_text(json.dumps(model), encoding="utf-8")
    p.write_text(render_plan(plan), encoding="utf-8")
    return m, p


# Maintainer tools (tools/host_packaging.py) are importable from the tests.
sys.path.append(str(Path(__file__).resolve().parents[1] / "tools"))
