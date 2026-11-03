# Security

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's **Report a vulnerability** button on the repository's Security tab (private vulnerability reporting), not in a public issue. Include the version (`architecture-suite --version`), your OS and Python version, and steps to reproduce. You should get an acknowledgement within a week.

Supported versions: the latest release.

## Security model

Architecture Suite analyzes repositories and documents that may be untrusted.

- **No code execution.** Analysis parses source statically (Python AST, pinned Tree-sitter grammars). It never runs repository code, build tools, package managers or language servers, and never evaluates infrastructure expressions.
- **Offline after setup.** Only `bootstrap.py` uses the network. Generation never downloads anything or calls cloud APIs.
- **Untrusted text stays data.** The skills instruct agents to treat repository and document content as evidence, never as instructions. Text that looks like prompt injection is flagged in `prompt_injection_paths`, and the eval suite includes an injection case.
- **Secrets.** Credential-like values are redacted before evidence is saved. `.env` files are skipped, and models containing likely secrets fail validation.
- **Bounded scans.** File count, per-file size, total size and time limits apply. Symlinks and reparse points are not followed.
- **Controlled writes.** Writes need `--confirm-write` (and `--confirm-overwrite` for existing output), are staged and rolled back on failure, refuse to write inside the analyzed repository, and stay within the output directory.
- **Asset integrity.** Bundled assets and optional Google Cloud icons are verified against SHA-256 manifests, and SVGs are rejected if they contain scripts, event handlers, external references or DTDs.
- **Supply chain.** Runtime dependencies install with `pip --require-hashes --only-binary=:all:` from a lock that CI audits with `pip-audit`.
- **Explorer.** The HTML explorer is read-only, embeds escaped model data and ships with a restrictive Content-Security-Policy. It embeds model evidence, so review it before sharing.
