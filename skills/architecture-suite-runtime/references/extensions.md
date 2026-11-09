# Extended architecture workflows

The canonical C4 model remains schema 2.0. Opt-in companion documents use independent `/v1` versions. Generation is offline after setup; no MCP server or repository execution is introduced.

## Portable installation

Run `python <skills-dir>/architecture-suite-runtime/scripts/bootstrap.py` once to set up the dependency environment at `~/.architecture-suite/runtime`. It installs hash-pinned dependencies and Chromium, then runs doctor. Run commands with that environment's Python and the skill's launcher, `scripts/architecture-suite.py` (see [runtime.md](runtime.md)).

The nine skills (`c4-diagrams`, `reverse-engineer-c4`, `c4-system`, `c4-container`, `c4-component`, `c4-code`, `c4-overview`, `c4-aws`, `c4-gcp`) and the shared `architecture-suite-runtime` folder are installed as sibling folders. `python tools/package_hosts.py` produces deterministic ZIP archives in `dist/hosts`. Claude Code and Factory packages include a `plugin.json`; Codex and Copilot packages contain repository skill layouts. Extract project packages into the repository. Claude Code users normally install from the marketplace on the `latest` branch instead (see the README).

`python tools/install_skill.py --host codex|claude|copilot|factory|all --scope user|project [--project <directory>] [--confirm-overwrite]` installs all skills and the runtime without editing agent configuration. Project scope requires `--project`. Backups remain outside skill discovery folders. CLI dependencies are installed separately through bootstrap.

Claude Code behavior is covered by the `claude plugin eval` suite in `evals/`. Codex, Copilot and Factory packages are package-validated; their agent behavior is not separately evaluated.

## Source inventory

```text
architecture-suite inventory --repo <repository> --output <inventory-dir> --confirm-write
```

Python uses AST; C#, Java, Kotlin, Go, JavaScript, TypeScript and TSX use pinned Tree-sitter packages. The inventory records declarations, imports, explicit route annotations/calls, unresolved calls and configuration addresses with evidence and confidence. Single-candidate import matching is conservative and is not compiler-level symbol resolution. Foreign-language declarations also feed the existing analyzer's code views. No builds, language servers, application code or repository dependency installation runs. Framework/configuration matching is partial and remains reviewable.

## Infrastructure imports

```text
architecture-suite import-infra --input <artifact> [--input <artifact>] --output <topology-dir> --confirm-write
```

Inputs: Terraform plan JSON, CloudFormation/CDK templates, Kubernetes manifests/rendered Helm YAML, and Compose YAML. Outputs are `topology.json` and an editable `architecture-plan.md`. `architecture-topology/v1` contains resources, relationships, explicit bindings and unresolved findings. Terraform resolved resource IDs, CloudFormation Ref properties, Compose dependencies and Kubernetes Service selectors can establish edges. Unsupported expressions remain unresolved; this importer does not execute infrastructure code or evaluate all provider semantics.

Optional `--bindings <mapping.json> --model <model.json>` maps topology resource IDs to existing container IDs. Unknown resources/containers fail. Import order determines `input-N-` resource prefixes; preserve input ordering for repeatable imports. Bindings are recorded in the topology sidecar, not silently applied as AWS deployment placements.

## Structured scenarios

`scenario-lint --model <model.json> --scenario <scenario.json>` checks a scenario. `scenario-render` accepts the same inputs plus `--output` and `--format all|mermaid,svg,drawio,png,visio`.

`architecture-scenario/v1` requires name, a unique participants array of canonical element IDs, and steps. Message/response steps have `from`, `to`, `description`, and optional `type`. Groups have type alt/opt/loop/par, condition and steps. Alt/par groups may include branches, each with condition and steps. Nesting is limited to 12. SVG, PNG, editable Draw.io and Visio share sequence geometry; Mermaid uses sequenceDiagram. See the generated [scenario example](../samples/extensions/scenario.json).

## Differences and rules

```text
architecture-suite diff --before <model.json> --after <model.json> --output <diff-dir> --confirm-write
architecture-suite check --model <model.json> --rules <rules.json> --output <check-dir> --confirm-write
```

Differences match element IDs and relationship endpoints; generated relationship ordinals and evidence/confidence changes do not create structural drift. A changed claim `status` (for example proposed to observed) is reported as a change. `--identities <mapping.json>` supplies explicit old-to-new identity mappings. No fuzzy rename matching is performed.

Rules use `architecture-rules/v1` and a rules array. Each rule has unique id, effect allow/deny, optional source/destination selectors and severity error/warning. Selectors accept arrays of ids, types and tags (plans set `tags` on elements); selector fields combine with AND. An empty selector matches all elements. An allow rule constrains destinations for matching sources; a deny rule rejects matching pairs. No rule executes code.

Checks default to report-only. `--fail-on error` returns 1 for new error findings; `--baseline <previous-baseline.json>` accepts reviewed fingerprints from a prior check. Reports include JSON, Markdown and a candidate baseline; updating the reviewed baseline is an explicit author action. Malformed inputs fail regardless of report-only policy. CI uploads artifacts without comments, pushes or branch-protection changes.

## Read-only offline explorer

```text
architecture-suite explore --model <model.json> [--scenario <scenario.json>] [--diff <diff.json>] --output <explorer-dir> --confirm-write
```

Open `explorer.html` directly. It embeds diagrams/data/fonts/icons, supports search, type filters, keyboard-operable containment trees, view selection, element/evidence inspection, drill-down to repeated scopes, scenarios, gaps and diff inspection. It cannot edit or write plans. Evidence locations are displayed rather than fetched from local disk. Files can be shared offline; inspect evidence before sharing.

All writing extension commands accept dry-run and existing write/overwrite controls. Their output directories use transactional staging and path checks. Each command owns its own files in `.architecture-suite-manifest.json`, so a scenario rendered into a C4 output folder never removes the C4 diagrams (see runtime.md). Examples are under `samples/extensions`.
