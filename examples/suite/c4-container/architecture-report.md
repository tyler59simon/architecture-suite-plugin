# Agentic Living Memory

Internal

Single user, single computer; installed under ~/.codex/agentic-living-memory with data under the user-selected root

## Evidence

- evidence-1: ARCHITECTURE.md: — 
- evidence-10: core/cli.py:21: — 
- evidence-11: core/common.py:1: — 
- evidence-12: core/capture.py; core/tag_taxonomy.py: — 
- evidence-13: core/governance.py: — 
- evidence-14: core/search.py: — 
- evidence-15: core/search.py:1: — 
- evidence-16: core/recursion.py; core/telemetry.py: — 
- evidence-17: core/sync.py: — 
- evidence-18: ARCHITECTURE.md (Markdown storage and lifecycle): — 
- evidence-19: INSTALLATION.md: — 
- evidence-2: ARCHITECTURE.md (Bootstrap and live hooks): — 
- evidence-20: hooks/claude_hooks.py: — 
- evidence-21: AGENTS.md: — 
- evidence-22: core/cli.py:3: — 
- evidence-23: core/cli.py: — 
- evidence-24: core/repository.py: — 
- evidence-25: core/recursion.py: — 
- evidence-3: core/sync.py; OBSIDIAN.md: — 
- evidence-4: core/pdf.py: — 
- evidence-5: hooks/*_hooks.py; integrations/setup.py: — 
- evidence-6: hooks/claude_hooks.py:1: — 
- evidence-7: install.py:1; integrations/setup.py:58: — 
- evidence-8: living_memory.py:1; core/cli.py:1: — 
- evidence-9: core/cli.py:1: — 

## Assumptions

- Container grouping into Hook Adapters, Memory CLI, Note Store and Index is architectural judgment from ARCHITECTURE.md, not from manifests.

## Gaps

- Multi-component flows inside Memory CLI are summarized; full call graph not established.

## Layout verification

```json
{
  "ok": true,
  "diagrams": {
    "02-containers/containers": {
      "findings": [],
      "crossings": 0,
      "bends": 16,
      "aspect_ratio": 1.904,
      "score": 49.90427564398182,
      "advisories": []
    }
  }
}
```
