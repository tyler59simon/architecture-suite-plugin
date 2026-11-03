# Contributing

Thanks for helping. See [docs/development.md](docs/development.md) for the full workflow; in short:

1. Use Python 3.11-3.14 (3.13 recommended) and install the locked development tree (`requirements-lock.txt`, then `pip install --no-deps -e .`).
2. Never edit `SKILL.md` files directly: change `tools/generate_skills.py` and run it. Manifests come from `distribution.py` through `tools/sync_manifests.py`.
3. Before opening a pull request, run `ruff check .`, the full `pytest` suite with coverage, and `python tools/record_validation.py` (at least 90% lines and 85% branches, and every public function executed by a test).
4. If you change how the skills behave, run the trigger, negative and safety evals (`claude plugin eval . --tag trigger negative safety --ablation none --no-publish`).
5. Keep generation offline: no network access, repository code execution or cloud API calls outside `bootstrap.py` and the maintainer tools in `tools/`.
6. Do not add Google Cloud icon files to the repository (see `assets/licenses/GCP-USAGE.md`).

By contributing you agree that your contributions are licensed under the Apache License 2.0.
