# Validation

Executable results are recorded in [validation-results.json](../reports/validation-results.json), with source coverage in [coverage.json](../reports/coverage.json) and public-callable execution in [public-coverage.json](../reports/public-coverage.json). `tools/record_validation.py` refuses to write them unless all tests pass, coverage is at least 90% of lines and 85% of branches, and every public function is executed by a test.

The suite covers models, plans, scope projection, source parsers, `plan-draft` container grouping, infrastructure inputs, dynamic scenarios, rules and diffs, offline browser rendering, explorer interaction, path containment, overwrite controls, process limits, asset integrity including the bundled Google Cloud icons, the bootstrap and launcher, dependency locks, and host package layouts and sizes.

**Platforms.** Local verification uses Windows and Python 3.13. CI (`.github/workflows/architecture.yml`) runs the suite on Windows, macOS and Linux with Python 3.11, 3.13 and 3.14, smoke-tests the portable bootstrap on each OS, audits dependencies and proves the runtime lock installs from wheels on every supported Python and OS. A platform counts as verified once its CI job has passed.

**Agent behaviour.** `evals/` is a `claude plugin eval` suite for Claude Code: skill triggering, prompts that must not trigger a skill, prompt injection, and an end-to-end render. On 2026-11-03 (Claude Code 2.1.317, one run per case) all 9 trigger cases, both negative cases and the injection case passed. The end-to-end case needs a shell sandbox, which eval runs on Windows lack; run it on Linux with `.github/workflows/evals.yml`. Codex, Copilot and Factory packages are package-validated only.

Coverage measures executable code, not the accuracy of architectural judgments for arbitrary systems. `plan-draft` output is a reviewable candidate.

Installation and package records are in [installation.json](../reports/installation.json), [skill-manifest.json](../reports/skill-manifest.json) and [host-packages.json](../reports/host-packages.json).
