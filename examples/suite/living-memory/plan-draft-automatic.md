# Architecture plan

Drafted by bounded static analysis. Review candidate boundaries and gaps before publishing.

```yaml
schema_version: architecture-plan/v1
system:
  name: Agentic Living Memory
  description: Source repository under static analysis
  classification: Internal
  scope: Repository boundary; runtime ownership unconfirmed
containers:
- name: Agentic Living Memory Python integrations
  description: Candidate Python application from integrations/setup.py
  technology: Python
  evidence: integrations/setup.py:1
  components:
  - name: Agentic Living Memory Python integrations integrations/setup.py
    description: Source module integrations/setup.py; responsibility requires review
    technology: Python
    evidence: integrations/setup.py:1
    code:
    - name: Agentic Living Memory Python integrations integrations/setup.py managed_handlers
      description: Declared function managed_handlers
      kind: function
      members:
      - '+managed_handlers(config, harness): unspecified'
      evidence: integrations/setup.py:23
    - name: Agentic Living Memory Python integrations integrations/setup.py hooks
      description: Declared function hooks
      kind: function
      members:
      - '+hooks(harness): unspecified'
      evidence: integrations/setup.py:28
    - name: Agentic Living Memory Python integrations integrations/setup.py instruction_block
      description: Declared function instruction_block
      kind: function
      members:
      - '+instruction_block(harness, enable_hooks): unspecified'
      evidence: integrations/setup.py:47
    - name: Agentic Living Memory Python integrations integrations/setup.py pretty
      description: Declared function pretty
      kind: function
      members:
      - '+pretty(value): unspecified'
      evidence: integrations/setup.py:56
    - name: Agentic Living Memory Python integrations integrations/setup.py setup_plan
      description: Declared function setup_plan
      kind: function
      members:
      - '+setup_plan(harness, home=None, enable_hooks=False, uninstall=False): unspecified'
      evidence: integrations/setup.py:58
    - name: Agentic Living Memory Python integrations integrations/setup.py main
      description: Declared function main
      kind: function
      members:
      - '+main(argv=None): unspecified'
      evidence: integrations/setup.py:104
- name: Agentic Living Memory Python integrations/copilot
  description: Candidate Python application from integrations/copilot/setup.py
  technology: Python
  evidence: integrations/copilot/setup.py:1
  components:
  - name: Agentic Living Memory Python integrations/copilot integrations/copilot/setup.py
    description: Source module integrations/copilot/setup.py; responsibility requires
      review
    technology: Python
    evidence: integrations/copilot/setup.py:1
    code: []
flows:
- from: Agentic Living Memory Python integrations/copilot integrations/copilot/setup.py
  to: Agentic Living Memory Python integrations integrations/setup.py
  description: Imports source module
  technology: static dependency
  evidence: integrations/copilot/setup.py:5
assumptions:
- Manifest roots are candidate runtime containers; confirm independent deployability
  and ownership.
gaps:
- Static analysis does not establish users, runtime call graphs, or deployment placement.
```
