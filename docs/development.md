# Development

The Python distribution points to `skills/architecture-suite-runtime/scripts/architecture_suite`. The runtime folder also has its own `pyproject.toml` and `requirements-runtime.lock` so the skills can be set up without this repository. A test keeps both pyproject files in agreement (version, Python range, dependencies).

## Environment

Python 3.11-3.14. Development uses 3.13:

```text
py -3.13 -m venv .venv                                   # macOS/Linux: python3.13 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-lock.txt
.venv/Scripts/python.exe -m pip install --no-deps -e .
.venv/Scripts/python.exe -m playwright install chromium
npm ci --ignore-scripts                                   # ELK and Mermaid for setup and syntax checks
```

## Inner loop

```text
python tools/check.py                      # ruff, the three --check drift checks, then the fast tests
python -m pytest -m "not slow" -n auto     # fast tests only (about 20 seconds)
python tools/check.py --full               # the CI commands below, including coverage and the gate
```

Tests that take about 3 seconds or more are marked `slow`. Tests that launch Playwright or an installed Chrome are marked `browser` (`-m "not browser"` skips them). Every layout test runs ELK in Node, so `npm ci` is required either way; without Node, layout falls back to Playwright. Tests must write only under `tmp_path` so `-n auto` is safe.

## Checks (what CI runs)

```text
ruff check .
python tools/generate_skills.py --check && python tools/sync_manifests.py --check && python tools/build_manifest.py --check
python -m pytest -n auto --cov=architecture_suite --cov-branch --cov-report=json:test-results/coverage.json --junitxml=test-results/junit.xml
python tools/record_validation.py      # gate: >=90% lines, >=85% branches, every public callable executed
pip-audit --require-hashes -r skills/architecture-suite-runtime/scripts/requirements-runtime.lock
python tools/check_wheels.py           # the runtime lock installs from wheels on 3.11-3.14 x Windows/Linux/macOS
npm audit --audit-level=moderate
```

`record_validation.py` writes `reports/`; commit refreshed reports only from a full local run. Temporary test artifacts go to the ignored `test-results/`.

## Tools

| File | Purpose |
| --- | --- |
| `tools/check.py` | Local check runner: ruff, drift checks, fast tests; `--full` runs coverage and `record_validation.py`. |
| `tools/bump_version.py` | Rewrites the version in every file that records it, then runs `sync_manifests.py`. `--dry-run` lists the files. |
| `tools/generate_skills.py` | Writes the ten `SKILL.md` files and the template copies. `--check` compares without writing. |
| `tools/sync_manifests.py` | Writes the plugin and marketplace manifests. `--check` compares without writing. |
| `tools/build_manifest.py` | Rebuilds `assets/manifest.json` (asset checksums). `--check` compares without writing. |
| `tools/lock_python.py` | Writes `requirements-lock.txt` and the hashed runtime lock (network). |
| `tools/check_wheels.py` | Proves the runtime lock installs from wheels on every supported Python and OS (network). |
| `tools/package_hosts.py` | Builds `dist/hosts/<host>.zip` and `dist/plugin/`. |
| `tools/install_skill.py` | Installs the skills and runtime into one or more agent hosts. |
| `tools/record_validation.py` | Records test results, coverage and public-callable execution in `reports/`; enforces the gate. |
| `tools/record_packages.py` | Records skill, package and install evidence in `reports/` from checks run here. |
| `tools/build_schemas.py` | Generates the distributed JSON contracts. |
| `tools/build_extension_schemas.py` | Generates the versioned extension document schemas. |
| `tools/setup_assets.py` | Downloads and vendors ELK, Mermaid and other bundled assets (network). |
| `tools/setup_gcp_assets.py` | Vendors the Google Cloud icon sets from user-supplied downloads. |
| `tools/generate_samples.py` | Regenerates `examples/starter-systems`. |
| `tools/generate_payments_samples.py` | Regenerates `examples/payments`. |
| `tools/generate_gcp_samples.py` | Regenerates `examples/ride-dispatch`. |
| `tools/generate_extensions.py` | Regenerates `examples/cli-features` and the fixtures the plugin ships. |

## Dependencies

After an intentional dependency change in both pyproject files, reinstall, then run `python tools/lock_python.py` (needs network). It rewrites `requirements-lock.txt` and the hashed `requirements-runtime.lock`, evaluating dependency markers for every supported Python and OS. Then run `tools/check_wheels.py` and `pip-audit`.

## Agent evals

`evals/` holds a `claude plugin eval` suite: skill triggering (tag `trigger`), prompts that must trigger nothing (`negative`), prompt injection (`safety`) and an end-to-end render (`e2e`, needs Bash/Write and network for the bootstrap):

```text
claude plugin eval . --tag trigger negative safety --ablation none --no-publish
claude plugin eval . --tag e2e --allow-tools Bash Write Edit --no-publish
```

`--ablation none` scores the skill-fired graders (with the default baseline arm they are indicators only). Results go to the ignored `evals/results/`.

## Samples and assets

```text
python tools/generate_payments_samples.py  # examples/payments (PayStream on AWS and Google Cloud)
python tools/generate_gcp_samples.py       # examples/ride-dispatch (RidePulse on Google Cloud)
python tools/generate_samples.py           # examples/starter-systems (three small AWS systems)
python tools/generate_extensions.py        # examples/cli-features, and the small fixtures the plugin ships
```

Samples live in `examples/`, outside the shipped plugin, and are explicitly fictional. To refresh bundled dependencies, run `npm ci --ignore-scripts`, `python tools/setup_assets.py`, `python tools/build_schemas.py` and `python tools/build_extension_schemas.py`. After editing any bundled asset by hand, run `python tools/build_manifest.py`. Review asset sources, licenses and checksums before distributing. The setup utilities access the network; normal generation does not.

## Google Cloud icons

Both official Google Cloud icon sets are vendored from user-supplied downloads (https://cloud.google.com/icons), not by `setup_assets.py`:

```text
python tools/setup_gcp_assets.py --modern <gcp-icons folder> --legacy-zip <google-cloud-legacy-icons.zip>
python tools/generate_gcp_samples.py
```

It writes `assets/gcp/modern/` and `assets/gcp/legacy/` (SVG only, unmodified), `gcp-catalog.json`, `manifest-gcp.json`, `provenance.json` and `manifest.json`. No license file ships with the downloads; see `assets/licenses/GCP-USAGE.md` and re-check the terms before updating.

## Distribution and release

```text
python tools/generate_skills.py        # regenerate the ten SKILL.md files
python tools/sync_manifests.py         # plugin and marketplace manifests from distribution.py
python tools/package_hosts.py          # dist/hosts/<host>.zip and dist/plugin/ (the versioned plugin branch tree)
python tools/install_skill.py --host claude --scope project --project <repository>
claude plugin validate dist/plugin
```

The version lives in `architecture_suite/__init__.py`, `distribution.VERSION`, both pyproject files, `package.json`, `package-lock.json` and the README install line (a test enforces agreement). `python tools/bump_version.py X.Y.Z` rewrites all of them and the manifests; add the CHANGELOG heading yourself. To release, update `CHANGELOG.md`, commit to `main`, then push a tag `v<version>`. `.github/workflows/release.yml` re-runs CI (Linux and Windows gate publishing; macOS runs alongside but does not gate it, because hosted macOS arm64 runners have gone unassigned for whole runs, so check its result before approving the `latest` pull request), attaches the host archives and `SHA256SUMS` to a GitHub release, and publishes `dist/plugin/` (skills, runtime, README, CHANGELOG and license files) as a new branch, `architecture-suite-<version>`, and updates `latest`. Claude Code users install from `latest` (updates) or a version branch (pinned).

Both kinds of plugin branch are protected by the "Plugin release branches" repository ruleset: changes only through a pull request with one approval, no force-pushes, no deletions. Creating a branch is allowed, so a release creates `architecture-suite-<version>` (and `latest`, the first time) directly. For later releases the workflow opens a pull request from `plugin-staging/latest-v<version>` into `latest`; approve and merge it to ship the update, then delete the staging branch. Opening that pull request relies on the repository setting that allows GitHub Actions to create pull requests. Update the version in the README install line too (a test checks it).

Claude and Factory packages use plugin layouts; Codex and Copilot packages use repository skill layouts. Host installers share one engine and do not modify agent configuration. Existing-output controls and backups apply; backups stay outside skill discovery folders.
