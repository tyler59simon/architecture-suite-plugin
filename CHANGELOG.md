# Changelog

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
