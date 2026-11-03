"""Write the repository-root plugin manifests from the single version source (distribution.VERSION)."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/architecture-suite-runtime/scripts"))
from architecture_suite.distribution import marketplace_manifest, plugin_manifest  # noqa: E402

for directory, name, data in (
    (".claude-plugin", "plugin.json", plugin_manifest("claude")),
    (".claude-plugin", "marketplace.json", marketplace_manifest()),
    (".factory-plugin", "plugin.json", plugin_manifest("factory")),
):
    target = ROOT / directory
    target.mkdir(exist_ok=True)
    (target / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(target / name)
