"""Build reproducible extension fixtures and usable offline artifacts."""

import json
from pathlib import Path
from architecture_suite.cli import main
from architecture_suite.examples import example_model

root = Path(__file__).resolve().parents[1]
out = root / "examples/extensions"
out.mkdir(parents=True, exist_ok=True)
model = example_model()
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
        str(out / "model.json"),
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
