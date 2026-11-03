# Architecture plan

Drafted by bounded static analysis. Review candidate boundaries and gaps before publishing.

```yaml
schema_version: architecture-plan/v1
system:
  name: Imported Infrastructure
  description: Reviewable infrastructure candidates
  classification: Internal
  scope: Imported declarations; ownership requires review
containers:
- name: input-0-api
  description: compose/service
  technology: compose/service
  evidence: examples/extensions/compose.json
- name: input-0-database
  description: compose/service
  technology: compose/service
  evidence: examples/extensions/compose.json
flows:
- from: input-0-api
  to: input-0-database
  description: explicit-reference
  evidence: examples/extensions/compose.json
- from: input-0-api
  to: input-0-database
  description: depends-on
  evidence: examples/extensions/compose.json
assumptions: []
gaps: []
```
