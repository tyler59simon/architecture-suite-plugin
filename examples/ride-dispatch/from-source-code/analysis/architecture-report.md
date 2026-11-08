# Ridepulse Repo

Inherited from source repository

Repository boundary; runtime ownership unconfirmed

## Evidence

- evidence-1: dispatch/pyproject.toml:1 — [project]
- evidence-10: notifier/main.go:1 — package main
- evidence-11: notifier/main.go:6 — func main() {
- evidence-12: infra/main.tf:39 — resource "google_storage_bucket" "archive" {
- evidence-13: infra/main.tf:7 — resource "google_cloud_run_v2_service" "dispatch" {
- evidence-14: infra/main.tf:12 — resource "google_cloud_run_v2_service" "ingest" {
- evidence-15: infra/main.tf:17 — resource "google_pubsub_topic" "events" {
- evidence-16: infra/main.tf:21 — resource "google_spanner_instance" "trips" {
- evidence-17: infra/main.tf:35 — resource "google_bigquery_dataset" "lake" {
- evidence-18: infra/main.tf:31 — resource "google_bigtable_instance" "telemetry" {
- evidence-19: infra/main.tf:2 — resource "google_container_cluster" "gateway" {
- evidence-2: dispatch/dispatch/__init__.py:1 — 
- evidence-20: infra/main.tf:26 — resource "google_redis_instance" "locations" {
- evidence-21: dispatch/dispatch/matching.py:4 — from dispatch import pricing
- evidence-3: dispatch/dispatch/matching.py:1 — """Scores candidate drivers for a trip."""
- evidence-4: dispatch/dispatch/matching.py:7 — class MatchingEngine:
- evidence-5: dispatch/dispatch/pricing.py:1 — """Quotes surge-aware fares."""
- evidence-6: dispatch/dispatch/pricing.py:5 — class FarePricer:
- evidence-7: ingest/package.json:1 — { "name": "ridepulse-ingest", "version": "0.1.0" }
- evidence-8: ingest/handler.js:1 — // Accepts driver GPS pings and appends them to Bigtable.
- evidence-9: notifier/go.mod:1 — module example.invalid/ridepulse/notifier

## Assumptions

- Manifest roots are candidate runtime containers; confirm independent deployability and ownership.

## Gaps

- GCP project, region, VPC, zone, subnet and placements require explicit evidence; none invented.
- Static analysis does not establish users, runtime call graphs, or deployment placement.
- dispatch/dispatch/matching.py:2: SDK usage of GCP-Legacy-pubsub; deployment and call semantics unconfirmed.
- dispatch/dispatch/pricing.py:2: SDK usage of GCP-Cloud-Spanner; deployment and call semantics unconfirmed.
- ingest/handler.js:2: SDK usage of GCP-Legacy-bigtable; deployment and call semantics unconfirmed.

## Claim status

- observed: 3 elements, 0 relationships
- inferred: 17 elements, 1 relationships
- not stated: 1 elements, 0 relationships

## Layout verification

```json
{
  "ok": true,
  "diagrams": {
    "01-system-context/system-context": {
      "findings": [],
      "crossings": 0,
      "bends": 0,
      "aspect_ratio": 1.59,
      "score": 1.5903614457831325,
      "advisories": []
    },
    "02-containers/containers": {
      "findings": [],
      "crossings": 0,
      "bends": 0,
      "aspect_ratio": 4.318,
      "score": 4.318181818181818,
      "advisories": []
    },
    "03-components/component-ridepulse-repo-go-notifier": {
      "findings": [],
      "crossings": 0,
      "bends": 0,
      "aspect_ratio": 1.026,
      "score": 1.0257575757575759,
      "advisories": []
    },
    "03-components/component-ridepulse-repo-node-ingest": {
      "findings": [],
      "crossings": 0,
      "bends": 0,
      "aspect_ratio": 1.026,
      "score": 1.0257575757575759,
      "advisories": []
    },
    "03-components/component-ridepulse-repo-python-dispatch": {
      "findings": [],
      "crossings": 0,
      "bends": 0,
      "aspect_ratio": 1.034,
      "score": 1.0341207349081365,
      "advisories": []
    },
    "04-code/code-ridepulse-repo-go-notifier-notifier-main-go": {
      "findings": [],
      "crossings": 0,
      "bends": 0,
      "aspect_ratio": 1.026,
      "score": 1.0257575757575759,
      "advisories": []
    },
    "04-code/code-ridepulse-repo-python-dispatch-dispatch-dispatch-matching-py": {
      "findings": [],
      "crossings": 0,
      "bends": 0,
      "aspect_ratio": 1.026,
      "score": 1.0257575757575759,
      "advisories": []
    },
    "04-code/code-ridepulse-repo-python-dispatch-dispatch-dispatch-pricing-py": {
      "findings": [],
      "crossings": 0,
      "bends": 0,
      "aspect_ratio": 1.026,
      "score": 1.0257575757575759,
      "advisories": []
    },
    "05-overview/overview-progressive": {
      "findings": [],
      "crossings": 0,
      "bends": 0,
      "aspect_ratio": 3.044,
      "score": 3.043633125556545,
      "advisories": []
    }
  }
}
```
