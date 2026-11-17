# Changelog

## 1.3.0 - review fixes, smaller output and faster checks

Fixes from a full code review, an installed-browser option for PNG, shorter skills, smaller SVG files and examples, and a faster development loop.

### Added

- **Installed Chrome or Edge for PNG:** `architecture-suite --browser auto|playwright|chrome|chrome-cli` (or `ARCHITECTURE_SUITE_BROWSER`) picks the browser for PNG export and Visio icons. `chrome` drives an installed Google Chrome or Microsoft Edge through Playwright; `chrome-cli` uses that browser's own headless mode and needs no Playwright. `auto` (the default) uses Playwright's Chromium when installed, then the installed browser. `ARCHITECTURE_SUITE_CHROME` names a browser executable, and `doctor` reports `browser_engine` and `browser_path`. With an installed browser, `bootstrap.py --no-browser` skips the Chromium download. Known limit: `chrome` times out taking the screenshot on CI runners (Linux and Windows), though it works on a desktop; if it times out, use `chrome-cli` or `playwright`.
- **Skill rules file and sample plan:** `references/skill-rules.md` holds the full runtime and C4 rules text that every skill used to repeat. `samples/plan-example.md` is a complete small fictional plan (containers, components, code, flows with evidence, deployment placements) that a test keeps lint-clean under `--strict`.
- **Fast test loop:** tests of about 3 seconds or more are marked `slow`, and tests that launch Playwright, Chrome or Node are marked `browser`. `python -m pytest -m "not slow" -n auto` finishes in well under a minute (`pytest-xdist` is in the dev lock), and CI runs the full suite with `-n auto`.
- **Drift checks:** `tools/generate_skills.py`, `tools/sync_manifests.py` and `tools/build_manifest.py` accept `--check`. They compare the generated output with the files, list the paths that differ, exit 1 and write nothing. The CI lint job runs all three.
- **Version bump and local checks:** `tools/bump_version.py X.Y.Z` rewrites every version location and regenerates the manifests (`--dry-run` lists the files). `tools/check.py` runs ruff, the drift checks and the fast tests; `--full` runs the coverage run and `record_validation.py`.

### Changed

- **CI:** Playwright browsers are cached by the locked Playwright version, host archives are built from one matrix entry, and the ruff, pip-audit and Playwright versions come from `requirements-lock.txt`. The release publish job no longer installs dependencies. `docs/development.md` lists every tool, and the unused `requirements-dev.txt` is removed.
- **Shorter skills, safer defaults:** each `SKILL.md` keeps a short Runtime and Rules block and links to `skill-rules.md`. `c4-diagrams` and `reverse-engineer-c4` use `--overview-style executive`, because `progressive` and `complete` can exceed PNG limits on large plans. Level skills run `plan-review` before `plan-lint`, `c4-aws`, `c4-gcp` and `c4-overview` dry-run before `--confirm-write`, and `c4-overview` covers `--emit-model`, scenarios, `diff` and `check`.
- **Help text:** every subcommand and flag has a help line, defaults are shown, and `--format` lists its values and ignores case (`PNG` works). `doctor` prints `checking runtime...` to stderr first.
- **Clearer errors:** a missing or oversized input exits 2 and reads `--model: no such file: <path>` (links still exit 3). A model that is not JSON names the file. Unknown scenario participants list the valid ids, invalid models print one finding per line, plan YAML errors give the line in the plan file, and the PNG size error suggests next steps.
- **Output summaries:** `plan-render`, `render`, `analyze` and `examples` add `ok`, `dry_run` and, after a write, `written` and `write_confirmation_required: false`. `overview_styles` appears only for `--level all` and `overview`. No key was removed.
- **Docs:** `runtime.md` no longer calls `architecture-model.json` a normal report (it needs `--emit-model`), `planning.md` links to the right section, and the launcher error text names the actual runtime path.
- **Smaller SVG files:** SVG diagrams embed `assets/font-embed.woff`, an unhinted Roboto subset (Latin, Latin-1, Latin Extended-A, punctuation, arrows and the guillemets), instead of the whole TTF. The font in each SVG drops from about 687 KB to about 38 KB. `font.ttf` stays for text measurement, so layout does not move. Characters outside the subset fall back to Arial, as CJK text already does. `tools/setup_assets.py` builds the subset (`--font-only` works offline) and needs `fonttools`, which is now in the dev lock. A test checks that every non-ASCII character in the runtime's string literals is in the subset.
- **Less dead code:** the one-line `render_overview_*`, `render_aws_deployment_*` and `render_gcp_deployment_*` wrappers, `render_drawio`, `render_vsdx`, `verify_model_layout`, `measure_model_layout`, `model_as_json`, `error_findings`, `all_example_models` and `contains_likely_secret` are removed because only tests called them. `aws_analyzer.py` and `gcp_analyzer.py` are now `cloud_signals.py`, `draft.py` is merged into `plan.py`, and `c4_layout.py` into `scene.py`. The RidePulse example plan (`examples_gcp.py`) and the host packaging code (`tools/host_packaging.py`) moved to `tools/`, so the shipped runtime no longer carries them.
- **Smaller examples:** `examples/` drops from 107 MB to about 23 MB. Every SVG embeds the font subset, and the generators keep only files that differ from a reference render (`tools/sample_dedupe.py`): the Google Cloud payments package omits files identical to AWS, the legacy-icon ride-dispatch views are the deployment only, and the second and third starter systems omit component and code views identical to the order platform. A test fails if two files under `examples/` are byte-identical, and the order-platform outputs are refreshed.
- **Packaging checks:** `tools/package_hosts.py` fails when a file under `skills/` is untracked and not ignored (git checkouts only), and importing it no longer writes `dist/`. `reports/coverage.json` and `reports/public-coverage.json` are no longer tracked; `record_validation.py` writes the coverage files under `test-results/`, which CI uploads.
- **Exit code 4 for internal errors:** an unexpected exception now exits 4 with `internal error: <type>: <message>` instead of a traceback with exit 1, which automation could not tell apart from lint findings.
- **`plan-lint --strict` catches template placeholders:** `placeholder` (leftover `Replace with ...`, `TBD` or `Unspecified` text) is now a lint advisory, so an unedited template fails `--strict`; `plan-review` reports it with the same question as before.

### Fixed

- **Plan lint never crashes on wrong types:** list or number values for a code `kind`, `layout.direction`, `layout.views`, an element `name` or `description`, and the top-level `evidence` section now give findings. Top-level `evidence` is linted (a string was split into one evidence entry per character, and a number crashed rendering).
- **Fewer false credential matches:** `password: str` in a signature and prose such as "session token: Redis-backed cache" are no longer redacted or reported. The plan `credential` finding names the field (for example `containers.0.description`).
- **No invented cloud:** a deployment whose nodes are all `off-cloud` or `device` no longer gets an "AWS Cloud" (or "Google Cloud") box, and execution environments may sit under an `off-cloud` node.
- **Clearer lint for nameless deployment nodes:** `deployment-node-name` names the node instead of a generic `deployment-shape` finding.
- **`scenario-render --format` accepts spaces** after commas, like the C4 commands.
- **PlantUML output is redacted like every other format:** names, descriptions and members pass through the same credential redaction and control-character filter, so a connection string redacted in Mermaid, SVG and Draw.io no longer appears in `.puml`.
- **Import flows follow real imports:** `plan-draft` and `analyze` read Python imports with `ast` (words like "from" and "import" in comments and docstrings no longer create flows, and standard-library imports such as `import logging` no longer link to a local `logging.py`), resolve relative imports against the importing file, and resolve JavaScript and TypeScript imports with an explicit extension (`./view.js`), multi-line imports and `index` files.
- **One cloud resource per declaration:** `--cloud-profile aws|gcp` counts only Terraform `resource` declarations and CloudFormation `Type:` lines, not references such as `aws_s3_bucket.logs.id` or attachment types (bucket policies, Lambda permissions, IAM members).
- **Infrastructure import edges:** Terraform plan `configuration` references now give edges; a resolved ID shared by several resources (a bucket and its versioning) and tag values no longer give false edges. CloudFormation `!GetAtt`, `Fn::GetAtt`, `!Sub` and `Fn::Sub` references give edges.
- **Overviews keep relationships with `flow_ids: []`:** an empty list no longer drops every relationship from the executive overview.
- **Scenario key:** sequence diagrams say "Arrow = message, in time order from top to bottom" instead of "directed dependency".
- **Read-only files no longer fail a publish:** on Windows, a read-only file in an existing output folder made a successful `--confirm-overwrite` publish exit 2 and leave a `.architecture-stage-*-backup` folder behind. Temporary folders are now removed including read-only files; if one still cannot be removed, the publish reports a warning instead of failing.
- **Edited files that a render replaces are reported:** dry runs and writes list `overwrites_edited`, the generated files edited since the last run that this run writes again.
- **Upgrades drop removed files:** installing a new version over an old one (`tools/install_skill.py`) no longer keeps files that the new version removed.
- **`bootstrap.py --no-browser` checks the rest of `doctor`:** it ignored every doctor failure; now only a missing browser is tolerated.
- **UTF-8 byte-order mark accepted:** plans, models, scenarios and infrastructure files saved with a BOM (Windows PowerShell 5.1 `Out-File`) are read normally.
- **LF line endings on every OS:** generated text files (`.mmd`, `.puml`, reports, JSON) no longer get CRLF on Windows.
- **`--browser auto` tries the installed browser:** when Playwright's Chromium is present but fails to start, `auto` now tries an installed Chrome or Edge before failing.
- **GitHub Copilot:** SKILL.md descriptions are now quoted YAML. Four descriptions contained ": ", which strict YAML parsers such as Copilot's reject, so those skills failed to load.

## 1.2.0 - PlantUML export

Editable C4-PlantUML output for every diagram and scenario.

### Added

- **PlantUML output:** `--format plantuml` (also part of `--format all`) writes C4-PlantUML `.puml` text for every diagram and scenario. Diagrams use the C4 macros (`Person`, `System`, `Container`, `ContainerDb`, `Component`, boundaries and `Deployment_Node`) from the `<C4/...>` library bundled with PlantUML, so they render offline; PlantUML computes its own layout. Claims that are not observed carry a dashed `claim` tag. Scenarios become PlantUML sequence diagrams.

## 1.1.0 - planning workflow, Visio export and new default formats

A planning workflow that checks a plan before anything is drawn, editable Visio output, and Mermaid and PNG as the default formats.

### Added

- **Visio output:** `--format visio` (also part of `--format all`) writes editable `.vsdx` drawings for every diagram and scenario. Boxes keep their role shapes and colours, connectors are glued to the boxes they join, claim status stays dotted, and cloud icons are embedded as PNG.
- **`architecture-plan` skill:** a planning workflow that runs before any diagram is drawn. It covers scope and target levels, sources (brief, documents, `plan-draft` or `import-infra` drafts), a level-by-level interview, evidence and claim status, then a readiness review. The plugin now has ten skills. The question bank, evidence rules, common mistakes and a ready-to-render checklist are in `references/planning.md`.
- **`plan-review` command:** reports for each level (system, container, component, code, deployment) whether it would render, the deepest ready C4 level, evidence and technology coverage, the claim-status mix, and findings with a level and a question for the user. Review findings are `no-people`, `no-external-systems`, `isolated-element`, `missing-technology`, `observed-without-evidence`, `thin-description`, `placeholder`, `unplaced-container`, `crowded-view` and `dropped-flow`, plus the plan-lint findings. `--output` also writes `plan-review.md`, and `--strict` fails on any finding. `c4-diagrams` and `reverse-engineer-c4` now run it before `plan-lint`.
- **`examples --format`:** the starter systems can be written in any format, including `visio` and `all`.

### Changed

- **Default formats are now Mermaid and PNG.** Draw.io joins SVG and Visio as opt-in: pass `--format mermaid,png,drawio` (or `all`) to `render`, `analyze`, `plan-render` and `examples`. `scenario-render` still defaults to every format. Re-rendering with defaults into a folder from an earlier run lists its unedited `.drawio` files under `would_remove` and retires them; add `drawio` to `--format` to keep them.

## 1.0.1 - audit fixes

Fixes from an external audit of 1.0.0, plus two additions.

### Added

- **Claim status:** plan elements and flows accept `status: observed|inferred|proposed|unknown`. Inferred, proposed and unknown claims are drawn dotted with a «status» tag and a notation-key line in SVG, PNG, Draw.io and Mermaid, so a forwarded diagram keeps the distinction; `architecture-report.md` counts claims by status. `plan-draft` and `import-infra` mark their candidates inferred. Plans without `status` render exactly as before.
- **Stale-file cleanup:** each publication records what it generated in `.architecture-suite-manifest.json`. Re-rendering removes earlier generated files that are no longer produced (renamed scopes, dropped levels or formats) if unchanged, keeps edited ones as reported conflicts, and never touches files it did not generate. Dry runs list `would_remove` and `conflicts`.
- **`--level deployment`** publishes only the AWS or Google Cloud deployment diagram and needs evidence only down to containers; the `c4-aws` and `c4-gcp` skills use it.
- Plans accept `tags` on elements, so rule selectors on tags work from plans.

### Fixed

- Terraform `sensitive_values` / `after_sensitive` masks are applied before anything is written (`[SENSITIVE]`), unknown-after-apply values are marked, and findings name the masked attribute paths.
- Infrastructure references need an exact value (`vpc-1` no longer matches `vpc-123`), and CloudFormation resource-level `DependsOn` becomes a `depends-on` relationship.
- An unsupported `deployment.provider` (such as `azure`) is a lint error instead of silently becoming AWS or GCP.
- A forced Google Cloud icon style without artwork keeps the element's service and only omits the icon.
- `plan-draft` and `inventory` refuse output inside the analyzed repository, as SECURITY.md states.
- `plan-draft` no longer models test folders inside a packaging root as components; inventory no longer reports HTTP client calls or `dict.get("key")` as routes.
- `--format all` includes SVG.
- `VALIDATION.json` in host packages lists the skills again instead of NOTICE/LICENSE paths.
- Overview diagrams no longer change between runs (frame order depended on Python hash seeds).
- Text is measured the same way on every host, so Linux no longer wraps labels differently (Pillow picked Raqm when libraqm was installed).
- Infrastructure import:
  - CloudFormation YAML short tags (`!Ref`, `!Sub |`, `!Base64`, `!Equals`, tags in flow sequences, trailing comments) are parsed as data, and `!Ref` creates a reference like the JSON `Ref`.
  - Empty and comment-only YAML documents (a Helm template that renders nothing, `--- # note`) are skipped.
  - Terraform IDs that are unknown until apply or masked no longer match each other as false relationships.
  - Sensitive masks on secret-named attributes are reported again.
  - Relationship order no longer depends on hash seeds.
  - Compose `depends_on` gives one relationship; undeclared services and networks are reported.
  - Distinct Kubernetes names that share a slug get numbered IDs.
- Names in non-Latin scripts or emoji, and names longer than 80 characters, get a short stable hash in their ID, so they no longer collide or produce file names too long to write. Latin names keep their IDs.
- Mermaid escapes `#`, and scenario Mermaid escapes `;`, so user text can no longer break or change the source.
- JSON output falls back to ASCII escapes on a console that cannot encode the text instead of failing.
- Scenario sequence diagrams:
  - Messages after a group no longer sit on its border, and consecutive groups no longer share a border.
  - Nested groups are inset.
  - `else` and `and` branches get divider lines.
- Frame titles in SVG and PNG are drawn over the edges that enter the frame.
- small-multiples packs panels into rows by their own widths, so moderate models fit PNG limits; the PNG size error names the diagram and the limits.
- Source inventory:
  - Files are parsed before secrets are redacted (redaction could break the syntax and lose every declaration); recorded names, routes and members are still redacted.
  - Python syntax errors become plan gaps.
  - Kotlin classes, objects, interfaces and functions get names, class scope and parameters.
- Diff, check and explore inputs:
  - `check` rejects rules and baselines without the right `schema_version` or types.
  - `diff --identities` rejects ids missing from either model.
  - `explore --diff` rejects documents that are not diffs.
  - Diff relationship ids read `source->destination` instead of a Python tuple.
- Plan lint:
  - Messages name the unknown section or flow field and the unknown endpoint, with a close match.
  - Placement and duplicate-ID errors say where they are.
  - Deployment node types of the other provider (for example `project` in an AWS deployment) are errors.
  - A service field of the other provider is an advisory.
- Flow `order` numbers the arrow label (`1. Requests trips`); it was validated and then discarded.
- An explicit `layout` direction of `down` carries over to Mermaid (`flowchart TB`).
- `--overview-style` with a level other than all or overview exits 2 (malformed arguments), as documented.
- AWS service acronyms MSK, KMS, IAM, SES, ECR, ELB and VPC resolve.
- Report evidence lines omit an empty line number or excerpt, and relationship status counts say they are per view.

## 1.0.0 - first public release

Architecture Suite generates enterprise-grade C4 architecture diagrams that you can modify and version control. Every package comes from a plain-text architecture plan and is published as editable Draw.io and Mermaid alongside PNG and SVG, so diagrams live in your repository, are reviewed in pull requests and evolve with the system. It is a versatile plugin with an option for everyone: an executive one-page overview, a cloud deployment view for platform teams, code-level views for developers, or rule checks in CI. Start from a conversation, a requirements document, an existing repository or your infrastructure code. Everything runs offline.

### Features

- **Built for change and version control:** architecture plans are Markdown and models are JSON, so they diff cleanly and fit code review. `diff` shows what changed between two versions, and every diagram can be edited in Draw.io or Mermaid instead of being regenerated from scratch.
- **Nine Claude Code skills, one shared runtime:** `c4-diagrams` (a full L1-L4 package plus overview from requirements, documents or chat), `reverse-engineer-c4` (draft, verify and render C4 from an existing repository), the single-level skills `c4-system`, `c4-container`, `c4-component` and `c4-code`, `c4-overview`, `c4-aws` and `c4-gcp`.
- **Editable architecture plans:** `plan-draft` drafts a Markdown plan from a repository, `plan-lint` checks it and `plan-render` publishes every C4 level or a single one, with fidelity reports.
- **An option for every audience:** five overview styles (executive, progressive, hierarchy, small-multiples and complete), the full C4 depth from system context to code, and output in Draw.io, Mermaid, PNG and SVG.
- **AWS and Google Cloud deployment diagrams** with the official icon sets (Google Cloud modern and legacy) bundled and checksum-verified.
- **Source inventory** for Python, C#, Java, Kotlin, Go, JavaScript, TypeScript and TSX, recording declarations, imports, routes and configuration with evidence and confidence.
- **Infrastructure import** from Terraform plan JSON, CloudFormation/CDK, Kubernetes/Helm and Compose into a topology and an editable plan.
- **Request scenarios** rendered as sequence diagrams (alt/opt/loop/par groups).
- **Architecture diffs and rule checks:** compare two models, and enforce allow/deny dependency rules with baselines and a CI-friendly `--fail-on error`.
- **Read-only offline HTML explorer** with search, filters, drill-down, evidence inspection, scenarios and diffs, in one shareable file.
- **Safe by default:** no code is executed from analyzed repositories. Scans are bounded, credential-like values are redacted, every write needs `--confirm-write` (dry runs available), and output is staged with rollback.

### Install and platforms

- **Claude Code:** install from the `latest` branch for automatic updates, or pin a version with its `architecture-suite-<version>` branch. Codex, GitHub Copilot and Factory archives are attached to each GitHub release.
- **Python 3.11-3.14 on Windows, macOS and Linux.** A one-time bootstrap installs hash-pinned dependencies into `~/.architecture-suite/runtime` (Chromium optional, for PNG). After that everything runs offline, and `doctor` checks the installation.
- **Apache-2.0**, with a NOTICE for bundled third-party assets (ELK, Roboto, AWS and Google Cloud icons).
