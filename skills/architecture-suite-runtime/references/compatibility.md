# Compatibility and limitations

Architecture Suite is a Python 3.11-3.14 CLI and a set of agent skills sharing one runtime. Python dependencies are pinned with hashes, and every supported Python on Windows, Linux and macOS (x64 and arm64) installs from wheels. ELK 0.9.3 runs through local Node.js or Chromium; PNG generation requires the pinned Playwright browser. Setup is separate from offline generation.

The CI matrix tests Windows, macOS and Linux on Python 3.11, 3.13 and 3.14, and smoke-tests the portable bootstrap on each OS. Claude Code agent behavior is checked with the `claude plugin eval` suite in `evals/`. Codex, GitHub Copilot and Factory/Droid packages use their documented skill layouts and are package-validated; their agent behavior is not separately evaluated.

Canonical model schema 2.0 contains context, container, component and code views. Overviews and deployment are companion outputs; structured scenarios use their own versioned documents. Existing model and plan workflows remain supported. Refer to [extensions.md](extensions.md) for inventories, infrastructure imports, scenario exports, diffs/rules and the offline explorer.

Static analysis produces reviewable application/module candidates and source dependencies. It does not prove independent deployability, ownership or runtime call graphs. Infrastructure imports do not execute code or evaluate arbitrary provider expressions; unresolved values remain findings. AWS detection rules cover seven service families, while the bundled SVG catalogue covers the complete pinned icon release. Two official Google Cloud icon sets (modern and legacy) are bundled.

SVG, PNG and Draw.io share measured scene geometry. Mermaid provides portable flowcharts or sequence diagrams with independent layout. Native Mermaid C4/class syntax is not emitted. Draw.io and non-Roboto scripts may use local font fallbacks, so glyph appearance can vary across systems. The HTML explorer is read-only and does not fetch source files from disk.

Third-party asset sources, licenses and checksums are retained under `scripts/architecture_suite/assets/`. Integrity failures stop normal publication; restore reviewed assets rather than accepting unknown checksums.
