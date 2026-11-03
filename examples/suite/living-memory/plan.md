# Architecture plan: Agentic Living Memory

```yaml
schema_version: architecture-plan/v1
system:
  name: Agentic Living Memory
  description: Local, harness-independent durable memory for coding agents, stored as Markdown notes with derived search indexes
  classification: Internal
  scope: Single user, single computer; installed under ~/.codex/agentic-living-memory with data under the user-selected root
people:
- name: Developer
  description: Installs the system, approves governance plans, reads notes
  evidence: ARCHITECTURE.md
external_systems:
- name: Agent Harness
  description: Codex, Claude Code, Factory or Copilot; fires lifecycle hooks and runs the agent that decides what to capture
  evidence: ARCHITECTURE.md (Bootstrap and live hooks)
- name: Obsidian
  description: Optional vault receiving a staged overlay of notes, canvas and dashboards
  evidence: core/sync.py; OBSIDIAN.md
- name: Headless Browser
  description: Renders approved corporate PDFs in an isolated temporary profile
  evidence: core/pdf.py
containers:
- name: Hook Adapters
  description: Per-harness lifecycle hooks that inject protocol and retrieved context at session start and request one capture review at stop
  technology: Python
  evidence: hooks/*_hooks.py; integrations/setup.py
  components:
  - name: Harness Hook Handlers
    description: Claude, Codex, Copilot and Factory payload adapters
    evidence: hooks/claude_hooks.py:1
  - name: Installer
    description: Writes managed hook and instruction blocks into harness configuration
    evidence: install.py:1; integrations/setup.py:58
- name: Memory CLI
  description: Single compact script interface (living_memory.py) used by hooks and by the agent for every action
  technology: Python
  evidence: living_memory.py:1; core/cli.py:1
  components:
  - name: Command Dispatcher
    description: Parses subcommands, payloads and domain flags; runs doctor
    evidence: core/cli.py:1
    code:
    - name: doctor
      description: Reports interpreter, FTS5, binding, pending recovery and index state
      kind: function
      members:
      - '+doctor(root, cwd, explicit): dict'
      evidence: core/cli.py:21
  - name: Domain Resolver
    description: Longest-prefix project binding and scope selection
    evidence: core/common.py:1
  - name: Capture and Tagging
    description: Controlled tag facets, idempotency and duplicate checks
    evidence: core/capture.py; core/tag_taxonomy.py
  - name: Governance and Journal
    description: Approved plans for rename, retag, merge, delete, remap and undo; durable pre/post journal
    evidence: core/governance.py
  - name: Search and Read
    description: Scoped FTS5 and canonical BM25 retrieval with rank fusion
    evidence: core/search.py
    code:
    - name: NoteIndex
      description: Derived SQLite FTS5 projection of notes
      kind: class
      members:
      - '+rebuild(domain): None'
      - '+query(text, scope): list'
      evidence: core/search.py:1
  - name: Improvement Engines
    description: Twelve deterministic evidence engines in off, shadow or active mode
    evidence: core/recursion.py; core/telemetry.py
  - name: Obsidian Sync
    description: Staged manifest-based overlay publisher
    evidence: core/sync.py
  - name: PDF Publisher
    description: Builds reviewed, classified PDFs from a selection cart
    evidence: core/pdf.py
- name: Canonical Note Store
  description: Markdown notes with JSON-compatible frontmatter, bindings, taxonomy and operation journals
  technology: Markdown files
  evidence: ARCHITECTURE.md (Markdown storage and lifecycle)
- name: Derived Index
  description: Disposable SQLite FTS5 databases and catalogs, rebuildable from the note store
  technology: SQLite FTS5
  evidence: core/search.py
flows:
- from: Developer
  to: Installer
  description: Runs one-time setup and wizard
  evidence: INSTALLATION.md
- from: Agent Harness
  to: Harness Hook Handlers
  description: Fires SessionStart, UserPromptSubmit and Stop events
  technology: Hook payload JSON
  evidence: ARCHITECTURE.md
- from: Harness Hook Handlers
  to: Command Dispatcher
  description: Requests retrieval and records turns
  evidence: hooks/claude_hooks.py
- from: Agent Harness
  to: Command Dispatcher
  description: Agent invokes capture and governance scripts
  technology: CLI
  evidence: AGENTS.md
- from: Command Dispatcher
  to: Domain Resolver
  description: Resolves project domain
  evidence: core/cli.py:3
- from: Command Dispatcher
  to: Capture and Tagging
  description: Validates and stages new notes
  evidence: core/cli.py
- from: Command Dispatcher
  to: Search and Read
  description: Runs scoped retrieval
  evidence: core/cli.py
- from: Command Dispatcher
  to: Governance and Journal
  description: Applies approved plans
  evidence: core/governance.py
- from: Capture and Tagging
  to: Canonical Note Store
  description: Atomic locked writes with revision checks
  evidence: core/repository.py
- from: Governance and Journal
  to: Canonical Note Store
  description: Journaled mutations and recovery
  evidence: core/governance.py
- from: Search and Read
  to: Derived Index
  description: Queries and rebuilds the index
  technology: SQLite
  evidence: core/search.py
- from: Derived Index
  to: Canonical Note Store
  description: Rebuilt from notes when dirty
  evidence: core/search.py
- from: Improvement Engines
  to: Search and Read
  description: Reads categorical evidence
  evidence: core/recursion.py
- from: Obsidian Sync
  to: Obsidian
  description: Publishes staged overlay
  evidence: core/sync.py
- from: PDF Publisher
  to: Headless Browser
  description: Renders approved PDF
  evidence: core/pdf.py
assumptions:
- Container grouping into Hook Adapters, Memory CLI, Note Store and Index is architectural judgment from ARCHITECTURE.md, not from manifests.
gaps:
- Multi-component flows inside Memory CLI are summarized; full call graph not established.
```
