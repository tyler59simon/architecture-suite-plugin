# Architecture plan

Replace names and cite the actual brief or source. Add components/code only when established. This intentionally supports a container-only request: render it with `--level container` (the default `--level all` also needs component and code evidence).

```yaml
schema_version: architecture-plan/v1
system:
  name: Example System
  description: Replace with the evidenced purpose
  classification: Internal
  scope: Replace with the ownership boundary
people: []
external_systems: []
containers:
  - name: Example Application
    description: Replace with the established responsibility
    technology: Unspecified
    evidence: Replace with a brief or file reference
    # status: proposed   # optional: observed | inferred | proposed | unknown (also on flows)
flows: []
assumptions: []
gaps:
  - Users, relationships and deeper implementation are not established by this template.
```
