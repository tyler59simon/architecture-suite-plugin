# Runtime and contracts

## Setup and invocation

Python 3.11-3.14 is required. Run the portable setup once (needs network):

```text
python <skill-directory>/scripts/bootstrap.py [--target DIR] [--no-browser]
```

It creates `~/.architecture-suite/runtime`, a virtual environment holding only the hash-pinned dependencies from `scripts/requirements-runtime.lock` (`pip install --require-hashes --only-binary=:all:`), installs the pinned Chromium unless `--no-browser` is given, records which lock it was built from, and runs `doctor`. If the interpreter running bootstrap is outside 3.11-3.14, bootstrap finds a supported one (Windows `py -3.X`, otherwise `python3.X` on PATH) and uses it.

Skill code is never installed into that environment. Run the CLI through the skill's own launcher, so a plugin update takes effect immediately:

```text
~/.architecture-suite/runtime/Scripts/python.exe <skill-directory>/scripts/architecture-suite.py <command>   # Windows
~/.architecture-suite/runtime/bin/python <skill-directory>/scripts/architecture-suite.py <command>           # macOS/Linux
```

In a development checkout, `pip install -e .` provides the `architecture-suite` console command and `python -m architecture_suite`. ELK prefers a local Node.js and falls back to local Chromium. `ARCHITECTURE_SUITE_LAYOUT_HOST=node|browser` pins the host; `ARCHITECTURE_SUITE_NODE` selects a Node executable.

Only setup accesses the network. AWS and Google Cloud icon sets are bundled. Provenance, licenses and SHA-256 values are in `scripts/architecture_suite/assets/{provenance.json,manifest.json,licenses/}`. Generation never downloads dependencies, contacts AWS or Google Cloud, or executes repository code.

## Commands

Use the path-based launcher if the console command is not on PATH.

```text
architecture-suite doctor
architecture-suite plan-draft --repo <repo> --output <plan.md> --dry-run
architecture-suite plan-draft --repo <repo> --output <plan.md> --confirm-write
architecture-suite plan-lint --plan <plan.md> [--strict]
architecture-suite plan-render --plan <plan.md> --output <out> --overview-style progressive --dry-run
architecture-suite plan-render --plan <plan.md> --output <out> --overview-style progressive --confirm-write
architecture-suite analyze --repo <repo> --output <out> --cloud-profile aws --level container --confirm-write
architecture-suite render --model <model.json> --output <out> --format mermaid,drawio,png,svg --level code --confirm-write
architecture-suite verify --model <model.json> --overview-style all
architecture-suite examples --output <out> --overview-style all --confirm-write
```

`analyze`, `render`, `plan-render`, and `verify` accept `--level all|system|container|component|code|overview|deployment` (default all). Scoped requests validate the required contiguous prefix but publish only the selected level. `deployment` publishes only the `06-<provider>-deployment` diagram and needs evidence only down to containers (components when the plan has them); it fails when the plan has no deployment section. `--overview-style` is repeatable and comma-separated; allowed styles are executive, progressive, hierarchy, small-multiples, complete, or all. CLI default: progressive. Styles apply only to all/overview.

Without `--format`, publication writes mermaid,drawio,png; `--format all` adds SVG (as `scenario-render` does). Examples always publish default formats. `plan-render --emit-model` emits internal JSON; otherwise the editable plan is the source of truth. `--augmented` records architectural judgment. `--allow-layout-findings` records accepted defects in fidelity reports.

Scan defaults: 2,000 files, 1,000,000 bytes per file, 50,000,000 total bytes, 45 seconds. `plan-draft` uses 400,000 bytes per file. Override with `--max-files`, `--max-file-bytes`, `--max-total-bytes`, `--timeout`. Symlinks/reparse points, vendor/build directories, `.env` and unsupported files are excluded. Invalid UTF-8 and oversized files become gaps. Credential-like values are redacted before evidence is saved. Draft classification defaults to Internal; analyze uses Inherited from source repository.

Exit codes: 0 success; 1 lint/verification findings (including strict advisories); 2 malformed input/arguments; 3 safety, write-control, integrity, or dependency failure. Publication rejects an invalid selected model with code 3. Dry runs scan/compile/validate and list paths, but do not render or write. Writes stage a complete result and roll back failed promotion; unrelated existing files are preserved when overwrite is authorized. Each publication records the files it generated, with SHA-256 hashes, in `.architecture-suite-manifest.json` at the output root. The C4 commands (`render`, `analyze`, `plan-render`) share one owner, `examples` has its own, and each extension command has its own. On the next publication by the same owner, files it generated before but no longer produces (a renamed scope, a dropped level or format, `--emit-model` left out) are removed if unchanged. Files edited since then are kept and listed under `conflicts`, and files no manifest lists are never touched. Dry runs list `would_remove` and `conflicts`; writes report `removed`. A folder without a manifest is adopted without deleting anything. A malformed manifest stops publication with code 3.

Artifact folders: `01-system-context`, `02-containers`, `03-components`, `04-code`, `05-overview`, `06-aws-deployment` or `06-gcp-deployment`. Repeated scopes are `component-<container-id>` and `code-<component-id>`; overviews are `overview-<style>`. Reports: `architecture-report.md`, `architecture-model.json`, `plan-fidelity.md`, `plan-fidelity.json`. Examples use `index.md`.

## Plan and schema

A plan is Markdown with fenced YAML mappings. Lists concatenate across fences; scalar/mapping sections cannot repeat. Anchors, aliases, tags, duplicate keys, and plans over 2 MB are rejected. Names slugify to globally unique IDs. Flows name their original endpoints; misspellings block compilation.

Required: system (name, description, classification, scope), containers (possibly empty for context-only evidence), flows. Optional: people, external_systems, deployment, layout, evidence, assumptions, gaps. Nest components under containers and code under components. Code needs nonempty `members`; kind is class/interface/module/function; its description may be omitted. Other elements need descriptions. Element/flow evidence is a reference or list. Optional `tags` (strings) on elements feed rule selectors. Optional `status: observed|inferred|proposed|unknown` on elements and flows states how certain a claim is: inferred, proposed and unknown claims render with a dotted outline or arrow, a «status» tag and a notation-key line in every format, and `architecture-report.md` counts them. A merged arrow takes the weakest status of its flows. Without `status` (or with `observed`) output is unchanged. `plan-draft` and `import-infra` mark their candidates `inferred`.

Flows use `from`, `to`, `description`, optional technology/evidence/order/status. Compilation projects endpoints to visible ancestors, preserves crossing dependencies and accounts for merged/dropped flows. `layout.direction` accepts auto/down/right; `layout.views` overrides existing scope IDs. Group siblings with `group`.

Deployment nodes have name, type, optional id, and nested `children` (or `nodes`). Placements name `element` and `node`; explicit `element_id`/`node_id` are accepted. An absent AWS cloud root is supplied. Use explicit IDs for repeated region names. `aws_service` on containers/components resolves official names such as Amazon ECS. SDK detection alone records uncertainty, never a placement.

Schemas: [plan](../scripts/architecture_suite/assets/architecture-plan.schema.json), [model](../scripts/architecture_suite/assets/architecture-model.schema.json). Semantic checks additionally enforce hierarchy, complete scopes, endpoint visibility, unique IDs, placement references, cycles, and secrets. Schema 2.0 views are context/container/component/code; overview and deployment are companions; dynamic is separate.

## Failures

`doctor` must report `assets`, `layout_engine` and `browser` as ok, and `runtime_deps` as ok or unmanaged (no bootstrap stamp, as in a development checkout). If `runtime_deps` says dependencies changed, re-run bootstrap. `gcp_icons` reports the bundled Google Cloud icons (or the `ARCHITECTURE_SUITE_GCP_ICONS` override folder). Install pinned dependencies/Chromium if missing. Restore reviewed assets on checksum failure; do not change expected digests to accept unknown content. PNG limits: width 6,000, total 24,000,000 pixels. Use narrower scopes, small-multiples, or SVG/Draw.io for large models. Blank PNGs are rejected. Fix layout findings through scope, grouping or reading direction and reverify before publication.
