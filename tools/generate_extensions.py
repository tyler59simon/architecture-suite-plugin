"""Build the CLI feature examples in examples/cli-features/ and the fixtures the plugin ships."""

import copy
import json
from pathlib import Path
from architecture_suite.cli import main
from architecture_suite.examples import example_model

root = Path(__file__).resolve().parents[1]
out = root / "examples/cli-features"
out.mkdir(parents=True, exist_ok=True)
model = example_model()
# A later version of the same model for the diff example: one technology changes and one
# code-level dependency is removed.
after = copy.deepcopy(model)
next(e for e in after["elements"] if e["id"] == "api")["technology"] = "Go HTTPS"
removed = after["relationships"][-1]["id"]
after["relationships"] = [r for r in after["relationships"] if r["id"] != removed]
for view in after["views"]:
    view["relationship_ids"] = [r for r in view.get("relationship_ids", []) if r != removed]
scenario = {
    "schema_version": "architecture-scenario/v1",
    "name": "Order submission",
    "participants": ["customer", "api", "order-queue"],
    "steps": [
        {"from": "customer", "to": "api", "description": "Submit order"},
        {
            "type": "alt",
            "condition": "valid order",
            "steps": [
                {"from": "api", "to": "order-queue", "description": "Queue work"}
            ],
            "branches": [
                {
                    "condition": "invalid",
                    "steps": [
                        {
                            "type": "response",
                            "from": "api",
                            "to": "customer",
                            "description": "Validation error",
                        }
                    ],
                }
            ],
        },
    ],
}
for name, value in {
    "model.json": model,
    "scenario.json": scenario,
    "rules.json": {
        "schema_version": "architecture-rules/v1",
        "rules": [
            {
                "id": "no-direct-payments-from-worker",
                "effect": "deny",
                "source": {"ids": ["worker"]},
                "destination": {"ids": ["payment-provider"]},
            }
        ],
    },
    "model-after.json": after,
    "compose.json": {
        "services": {
            "api": {"depends_on": ["database"]},
            "database": {"image": "postgres:16"},
        }
    },
}.items():
    (out / name).write_text(json.dumps(value, indent=2), encoding="utf-8")
commands = [
    [
        "scenario-render",
        "--model",
        str(out / "model.json"),
        "--scenario",
        str(out / "scenario.json"),
        "--output",
        str(out / "scenario"),
    ],
    [
        "import-infra",
        "--input",
        str(out / "compose.json"),
        "--output",
        str(out / "infrastructure"),
    ],
    [
        "check",
        "--model",
        str(out / "model.json"),
        "--rules",
        str(out / "rules.json"),
        "--output",
        str(out / "checks"),
    ],
    [
        "diff",
        "--before",
        str(out / "model.json"),
        "--after",
        str(out / "model-after.json"),
        "--output",
        str(out / "diff"),
    ],
    [
        "explore",
        "--model",
        str(out / "model.json"),
        "--scenario",
        str(out / "scenario.json"),
        "--diff",
        str(out / "diff/architecture-diff.json"),
        "--output",
        str(out / "explorer"),
    ],
]
for command in commands:
    if main(command + ["--confirm-write", "--confirm-overwrite"]):
        raise RuntimeError(command)

# The plugin ships only the small input fixtures that references/extensions.md and
# .github/examples/architecture-check.yml use; everything else stays in examples/.
import shutil  # noqa: E402

fixtures = root / "skills/architecture-suite-runtime/samples/extensions"
for name in ("model.json", "rules.json", "scenario.json", "compose.json", "checks/baseline.json"):
    (fixtures / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out / name, fixtures / name)
