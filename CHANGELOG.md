# Changelog

## 1.0.0 - first public release

Nine Claude Code skills (`c4-diagrams`, `reverse-engineer-c4`, `c4-system`, `c4-container`, `c4-component`, `c4-code`, `c4-overview`, `c4-aws`, `c4-gcp`) sharing one offline runtime that produces editable Draw.io, Mermaid, PNG and SVG C4 diagrams, deployment diagrams, scenarios, diffs, rule checks and an HTML explorer.

Changes since the internal 2.1.0 builds:

- **Install:** Claude Code users install from the slim `release` branch marketplace. Host archives for Codex, Copilot and Factory are attached to GitHub releases.
- **Python 3.11-3.14.** Dropped end-of-life 3.10. Updated PyYAML to 6.0.3 and Pillow to 13.0.0, which fixes 39 Pillow advisories. The runtime lock is hash-pinned, and CI proves it installs from wheels on Windows, Linux and macOS.
- **Bootstrap** installs only dependencies into `~/.architecture-suite/runtime`. The skills always run their own code through `scripts/architecture-suite.py`, so plugin updates take effect without a reinstall. Bootstrap picks a supported Python automatically, supports `--no-browser` and `--target`, and reports failures clearly. `doctor` flags a dependency lock that changed since setup (`runtime_deps`).
- **Google Cloud icons** (modern and legacy official sets) are bundled and verified against `manifest-gcp.json`. `doctor` reports `gcp_icons`. `ARCHITECTURE_SUITE_GCP_ICONS` can point at another icon folder; missing icons render without one.
- **Windows:** `.gitattributes` keeps checksummed assets byte-exact. Previously a clone with `core.autocrlf=true` failed the integrity check for 1,964 of 2,131 assets.
- **`plan-draft` / `analyze` accuracy:** a `setup.py` counts as a manifest only when it uses setuptools or distutils. Source files outside any manifest root are grouped by top-level directory instead of being dropped. Test directories are recorded as a gap.
- **Package size:** rendered samples moved to `examples/`, which is not shipped. Host archives are about 4 MB instead of about 62 MB.
- **Licensing:** Apache-2.0, with a NOTICE for bundled third-party assets (ELK, Roboto, AWS and Google Cloud icons).
- **Hardening:** the HTML explorer's Content-Security-Policy allows only its own script, by SHA-256 hash, instead of `'unsafe-inline'`. Infrastructure-import evidence records input paths relative to the working directory, so shared artifacts no longer expose home-directory paths.
- **Marketplace:** renamed to `architecture-suite` (install with `architecture-suite@architecture-suite`) to keep Windows cache paths under the 260-character limit.
- **Quality:** ruff, a coverage gate, pip-audit, npm audit, a wheel-availability check and a bootstrap smoke test in CI. Added a `claude plugin eval` suite covering skill triggering, negative prompts, prompt injection and an end-to-end render. Added SECURITY.md and CONTRIBUTING.md.
