# Architecture plan

Drafted by bounded static analysis. Review candidate boundaries and gaps before publishing.

```yaml
schema_version: architecture-plan/v1
gcp_icon_style: auto
system:
  name: RidePulse
  description: Real-time ride dispatch and fleet telemetry platform
  classification: Synthetic, non-production example
  scope: Illustrative owned services running on Google Cloud
people:
- name: Rider
  description: Requests and takes trips
  evidence: fictional brief
- name: Driver
  description: Accepts offers and drives trips
  evidence: fictional brief
- name: Operations Analyst
  description: Monitors fleet health and demand
  evidence: fictional brief
external_systems:
- name: Maps Provider
  description: Routing and geocoding
  evidence: fictional brief
- name: Payment Gateway
  description: Card authorization and capture
  evidence: fictional brief
- name: SMS Gateway
  description: Text message delivery
  evidence: fictional brief
containers:
- name: Rider Gateway
  description: Terminates rider and driver mobile traffic
  technology: Go gRPC and HTTPS
  gcp_service: Google Kubernetes Engine
  evidence: fictional brief
  components:
  - name: Auth Middleware
    description: Authenticates callers and enforces quotas
    evidence: fictional brief
    code:
    - name: AuthMiddleware
      description: Illustrative implementation
      kind: class
      members:
      - '+authenticate(token): Principal'
      evidence: fictional brief
  - name: Trip Controller
    description: Accepts trip requests and publishes events
    evidence: fictional brief
    code:
    - name: TripController
      description: Illustrative implementation
      kind: class
      members:
      - '+requestTrip(request): TripId'
      evidence: fictional brief
- name: Dispatch Service
  description: Matches riders with nearby drivers and prices fares
  technology: Java on Cloud Run
  gcp_service: Cloud Run
  evidence: fictional brief
  components:
  - name: Matching Engine
    description: Scores candidate drivers
    evidence: fictional brief
    code:
    - name: MatchingEngine
      description: Illustrative implementation
      kind: class
      members:
      - '+match(trip): Assignment'
      evidence: fictional brief
  - name: Fare Pricer
    description: Quotes surge-aware fares
    evidence: fictional brief
    code:
    - name: FarePricer
      description: Illustrative implementation
      kind: class
      members:
      - '+quote(trip): Fare'
      evidence: fictional brief
- name: Location Ingest
  description: Accepts driver GPS pings at high volume
  technology: Rust on Cloud Run
  gcp_service: Cloud Run
  evidence: fictional brief
- name: Notification Worker
  description: Sends push and SMS alerts
  technology: Node.js
  gcp_service: Cloud Functions
  evidence: fictional brief
- name: Event Bus
  description: Carries trip and location events
  technology: Pub/Sub
  gcp_service: Pub/Sub
  evidence: fictional brief
- name: Trip Store
  description: Transactional trip and account records
  technology: Spanner
  gcp_service: Cloud Spanner
  evidence: fictional brief
- name: Location Cache
  description: Latest driver positions
  technology: Redis
  gcp_service: Memorystore
  evidence: fictional brief
- name: Fleet Time Series
  description: High-rate telemetry history
  technology: Bigtable
  gcp_service: Bigtable
  evidence: fictional brief
- name: Telemetry Lake
  description: Analytics warehouse
  technology: BigQuery
  gcp_service: BigQuery
  evidence: fictional brief
- name: Location Archive
  description: Daily telemetry snapshots
  technology: Object storage
  gcp_service: Cloud Storage
  evidence: fictional brief
- name: ETA Model
  description: Arrival time predictions
  technology: Vertex AI endpoint
  gcp_service: Vertex AI
  evidence: fictional brief
flows:
- from: Rider
  to: Rider Gateway
  description: Requests trips and tracks arrival
  technology: HTTPS
  evidence: fictional brief
- from: Driver
  to: Rider Gateway
  description: Accepts offers and reports trip status
  technology: gRPC
  evidence: fictional brief
- from: Driver
  to: Location Ingest
  description: Streams GPS pings
  technology: HTTPS
  evidence: fictional brief
- from: Operations Analyst
  to: Telemetry Lake
  description: Runs fleet reports
  technology: SQL
  evidence: fictional brief
- from: AuthMiddleware
  to: Trip Store
  description: Verifies rider accounts
  technology: Spanner API
  evidence: fictional brief
- from: TripController
  to: Event Bus
  description: Publishes trip requested events
  technology: Pub/Sub
  evidence: fictional brief
- from: TripController
  to: Payment Gateway
  description: Charges completed trips
  technology: HTTPS
  evidence: fictional brief
- from: Event Bus
  to: MatchingEngine
  description: Delivers trip events
  technology: push subscription
  evidence: fictional brief
- from: MatchingEngine
  to: Location Cache
  description: Finds nearby drivers
  technology: Redis
  evidence: fictional brief
- from: MatchingEngine
  to: ETA Model
  description: Requests arrival estimates
  technology: HTTPS
  evidence: fictional brief
- from: MatchingEngine
  to: Maps Provider
  description: Fetches road routes
  technology: HTTPS
  evidence: fictional brief
- from: FarePricer
  to: Trip Store
  description: Records quoted fare and assignment
  technology: Spanner API
  evidence: fictional brief
- from: Dispatch Service
  to: Event Bus
  description: Publishes driver assignments
  technology: Pub/Sub
  evidence: fictional brief
- from: Location Ingest
  to: Location Cache
  description: Updates driver position
  technology: Redis
  evidence: fictional brief
- from: Location Ingest
  to: Fleet Time Series
  description: Appends telemetry samples
  technology: Bigtable API
  evidence: fictional brief
- from: Location Ingest
  to: Event Bus
  description: Publishes location samples
  technology: Pub/Sub
  evidence: fictional brief
- from: Event Bus
  to: Notification Worker
  description: Delivers assignment events
  technology: event
  evidence: fictional brief
- from: Notification Worker
  to: SMS Gateway
  description: Sends rider and driver alerts
  technology: HTTPS
  evidence: fictional brief
- from: Event Bus
  to: Telemetry Lake
  description: Streams events for analytics
  technology: BigQuery subscription
  evidence: fictional brief
- from: Fleet Time Series
  to: Location Archive
  description: Exports daily snapshots
  technology: Dataflow template
  evidence: fictional brief
assumptions:
- All architecture and deployment facts in this example are fictional.
gaps: []
deployment:
  provider: gcp
  nodes:
  - name: Example Organization
    type: organization
    children:
    - name: ridepulse-prod
      type: project
      children:
      - name: us-central1
        type: region
        children:
        - name: ridepulse-vpc
          type: vpc
          children:
          - name: app-subnet
            type: subnet
          - name: data-subnet
            type: subnet
  placements:
  - element: Rider Gateway
    node: app-subnet
  - element: Dispatch Service
    node: us-central1
  - element: Location Ingest
    node: us-central1
  - element: Notification Worker
    node: us-central1
  - element: ETA Model
    node: us-central1
  - element: Location Cache
    node: data-subnet
  - element: Event Bus
    node: ridepulse-prod
  - element: Trip Store
    node: ridepulse-prod
  - element: Fleet Time Series
    node: ridepulse-prod
  - element: Telemetry Lake
    node: ridepulse-prod
  - element: Location Archive
    node: ridepulse-prod
```
