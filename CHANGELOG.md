# Changelog

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
