# Architecture plan

Drafted by bounded static analysis. Review candidate boundaries and gaps before publishing.

```yaml
schema_version: architecture-plan/v1
system:
  name: Ridepulse Repo
  description: Source repository under static analysis
  classification: Internal
  scope: Repository boundary; runtime ownership unconfirmed
containers:
- name: Ridepulse Repo Python dispatch
  description: Candidate Python application from dispatch/pyproject.toml
  technology: Python
  evidence: dispatch/pyproject.toml:1
  status: inferred
  components:
  - name: Ridepulse Repo Python dispatch dispatch/dispatch/__init__.py
    description: Source module dispatch/dispatch/__init__.py; responsibility requires
      review
    technology: Python
    evidence: dispatch/dispatch/__init__.py:1
    status: inferred
    code: []
  - name: Ridepulse Repo Python dispatch dispatch/dispatch/matching.py
    description: Source module dispatch/dispatch/matching.py; responsibility requires
      review
    technology: Python
    evidence: dispatch/dispatch/matching.py:1
    status: inferred
    code:
    - name: Ridepulse Repo Python dispatch dispatch/dispatch/matching.py MatchingEngine
      description: Declared class MatchingEngine
      kind: class
      members:
      - '+match(self, trip): unspecified'
      evidence: dispatch/dispatch/matching.py:7
      status: observed
  - name: Ridepulse Repo Python dispatch dispatch/dispatch/pricing.py
    description: Source module dispatch/dispatch/pricing.py; responsibility requires
      review
    technology: Python
    evidence: dispatch/dispatch/pricing.py:1
    status: inferred
    code:
    - name: Ridepulse Repo Python dispatch dispatch/dispatch/pricing.py FarePricer
      description: Declared class FarePricer
      kind: class
      members:
      - '+quote(self, trip): unspecified'
      evidence: dispatch/dispatch/pricing.py:5
      status: observed
- name: Ridepulse Repo Node ingest
  description: Candidate Node application from ingest/package.json
  technology: Node
  evidence: ingest/package.json:1
  status: inferred
  components:
  - name: Ridepulse Repo Node ingest ingest/handler.js
    description: Source module ingest/handler.js; responsibility requires review
    technology: Node
    evidence: ingest/handler.js:1
    status: inferred
    code: []
- name: Ridepulse Repo Go notifier
  description: Candidate Go application from notifier/go.mod
  technology: Go
  evidence: notifier/go.mod:1
  status: inferred
  components:
  - name: Ridepulse Repo Go notifier notifier/main.go
    description: Source module notifier/main.go; responsibility requires review
    technology: Go
    evidence: notifier/main.go:1
    status: inferred
    code:
    - name: Ridepulse Repo Go notifier notifier/main.go main
      description: Declared function main
      kind: function
      members:
      - +main()
      evidence: notifier/main.go:6
      status: observed
- name: GCP resource infra/main.tf line 39 GCP-Cloud-Storage
  description: Infrastructure resource declaration; runtime ownership requires review
  technology: GCP infrastructure
  gcp_service: GCP-Cloud-Storage
  evidence: infra/main.tf:39
  status: inferred
- name: GCP resource infra/main.tf line 7 GCP-Cloud-Run
  description: Infrastructure resource declaration; runtime ownership requires review
  technology: GCP infrastructure
  gcp_service: GCP-Cloud-Run
  evidence: infra/main.tf:7
  status: inferred
- name: GCP resource infra/main.tf line 12 GCP-Cloud-Run
  description: Infrastructure resource declaration; runtime ownership requires review
  technology: GCP infrastructure
  gcp_service: GCP-Cloud-Run
  evidence: infra/main.tf:12
  status: inferred
- name: GCP resource infra/main.tf line 17 GCP-Legacy-pubsub
  description: Infrastructure resource declaration; runtime ownership requires review
  technology: GCP infrastructure
  gcp_service: GCP-Legacy-pubsub
  evidence: infra/main.tf:17
  status: inferred
- name: GCP resource infra/main.tf line 21 GCP-Cloud-Spanner
  description: Infrastructure resource declaration; runtime ownership requires review
  technology: GCP infrastructure
  gcp_service: GCP-Cloud-Spanner
  evidence: infra/main.tf:21
  status: inferred
- name: GCP resource infra/main.tf line 35 GCP-BigQuery
  description: Infrastructure resource declaration; runtime ownership requires review
  technology: GCP infrastructure
  gcp_service: GCP-BigQuery
  evidence: infra/main.tf:35
  status: inferred
- name: GCP resource infra/main.tf line 31 GCP-Legacy-bigtable
  description: Infrastructure resource declaration; runtime ownership requires review
  technology: GCP infrastructure
  gcp_service: GCP-Legacy-bigtable
  evidence: infra/main.tf:31
  status: inferred
- name: GCP resource infra/main.tf line 2 GCP-Google-Kubernetes-Engine
  description: Infrastructure resource declaration; runtime ownership requires review
  technology: GCP infrastructure
  gcp_service: GCP-Google-Kubernetes-Engine
  evidence: infra/main.tf:2
  status: inferred
- name: GCP resource infra/main.tf line 26 GCP-Legacy-memorystore
  description: Infrastructure resource declaration; runtime ownership requires review
  technology: GCP infrastructure
  gcp_service: GCP-Legacy-memorystore
  evidence: infra/main.tf:26
  status: inferred
flows:
- from: Ridepulse Repo Python dispatch dispatch/dispatch/matching.py
  to: Ridepulse Repo Python dispatch dispatch/dispatch/pricing.py
  description: Imports source module
  technology: static dependency
  evidence: dispatch/dispatch/matching.py:4
  status: inferred
assumptions:
- Manifest roots are candidate runtime containers; confirm independent deployability
  and ownership.
gaps:
- Static analysis does not establish users, runtime call graphs, or deployment placement.
- 'dispatch/dispatch/matching.py:2: SDK usage of GCP-Legacy-pubsub; deployment and
  call semantics unconfirmed.'
- 'dispatch/dispatch/pricing.py:2: SDK usage of GCP-Cloud-Spanner; deployment and
  call semantics unconfirmed.'
- 'ingest/handler.js:2: SDK usage of GCP-Legacy-bigtable; deployment and call semantics
  unconfirmed.'
- GCP project, region, VPC, zone, subnet and placements require explicit evidence;
  none invented.
```
