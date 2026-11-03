# CLI features (fictional order platform)

Inputs and outputs of the extended `architecture-suite` commands, all for the starter order platform.

| Feature | Command | Input | Output |
| --- | --- | --- | --- |
| Request scenario (sequence diagram) | `scenario-render` | [scenario.json](scenario.json) | [scenario/](scenario) |
| Architecture diff between two versions | `diff` | [model.json](model.json) → [model-after.json](model-after.json) (one technology changed, one dependency removed) | [diff/](diff) |
| Rule check (passes cleanly) | `check` | [model.json](model.json), [rules.json](rules.json) | [checks/](checks), including a `baseline.json` for later runs |
| Infrastructure import (Docker Compose) | `import-infra` | [compose.json](compose.json) | [infrastructure/](infrastructure): `topology.json` and an editable plan |
| Offline HTML explorer | `explore` | model, scenario and diff above | [explorer/explorer.html](explorer/explorer.html) (download and open locally) |

Regenerate with `python tools/generate_extensions.py`. See the
[extensions reference](../../skills/architecture-suite-runtime/references/extensions.md) for every option.
