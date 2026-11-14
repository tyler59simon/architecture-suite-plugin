"""Fictional Google Cloud example: RidePulse, a real-time ride dispatch platform."""

from copy import deepcopy
from .plan import compile_plan

SYSTEM_ID = "ridepulse"
BRIEF = "fictional brief"


def _code(name, member):
    return {
        "name": name,
        "description": "Illustrative implementation",
        "kind": "class",
        "members": [member],
        "evidence": BRIEF,
    }


def _component(name, description, *code):
    return {
        "name": name,
        "description": description,
        "evidence": BRIEF,
        "code": list(code),
    }


def _container(name, description, technology, service, *components):
    item = {
        "name": name,
        "description": description,
        "technology": technology,
        "gcp_service": service,
        "evidence": BRIEF,
    }
    if components:
        item["components"] = list(components)
    return item


FLOWS = [
    ("Rider", "Rider Gateway", "Requests trips and tracks arrival", "HTTPS"),
    ("Driver", "Rider Gateway", "Accepts offers and reports trip status", "gRPC"),
    ("Driver", "Location Ingest", "Streams GPS pings", "HTTPS"),
    ("Operations Analyst", "Telemetry Lake", "Runs fleet reports", "SQL"),
    ("AuthMiddleware", "Trip Store", "Verifies rider accounts", "Spanner API"),
    ("TripController", "Event Bus", "Publishes trip requested events", "Pub/Sub"),
    ("TripController", "Payment Gateway", "Charges completed trips", "HTTPS"),
    ("Event Bus", "MatchingEngine", "Delivers trip events", "push subscription"),
    ("MatchingEngine", "Location Cache", "Finds nearby drivers", "Redis"),
    ("MatchingEngine", "ETA Model", "Requests arrival estimates", "HTTPS"),
    ("MatchingEngine", "Maps Provider", "Fetches road routes", "HTTPS"),
    ("FarePricer", "Trip Store", "Records quoted fare and assignment", "Spanner API"),
    ("Dispatch Service", "Event Bus", "Publishes driver assignments", "Pub/Sub"),
    ("Location Ingest", "Location Cache", "Updates driver position", "Redis"),
    ("Location Ingest", "Fleet Time Series", "Appends telemetry samples", "Bigtable API"),
    ("Location Ingest", "Event Bus", "Publishes location samples", "Pub/Sub"),
    ("Event Bus", "Notification Worker", "Delivers assignment events", "event"),
    ("Notification Worker", "SMS Gateway", "Sends rider and driver alerts", "HTTPS"),
    ("Event Bus", "Telemetry Lake", "Streams events for analytics", "BigQuery subscription"),
    ("Fleet Time Series", "Location Archive", "Exports daily snapshots", "Dataflow template"),
]


def ridepulse_plan() -> dict:
    plan = {
        "schema_version": "architecture-plan/v1",
        "gcp_icon_style": "auto",
        "system": {
            "name": "RidePulse",
            "description": "Real-time ride dispatch and fleet telemetry platform",
            "classification": "Synthetic, non-production example",
            "scope": "Illustrative owned services running on Google Cloud",
        },
        "people": [
            {"name": "Rider", "description": "Requests and takes trips", "evidence": BRIEF},
            {"name": "Driver", "description": "Accepts offers and drives trips", "evidence": BRIEF},
            {
                "name": "Operations Analyst",
                "description": "Monitors fleet health and demand",
                "evidence": BRIEF,
            },
        ],
        "external_systems": [
            {"name": "Maps Provider", "description": "Routing and geocoding", "evidence": BRIEF},
            {"name": "Payment Gateway", "description": "Card authorization and capture", "evidence": BRIEF},
            {"name": "SMS Gateway", "description": "Text message delivery", "evidence": BRIEF},
        ],
        "containers": [
            _container(
                "Rider Gateway",
                "Terminates rider and driver mobile traffic",
                "Go gRPC and HTTPS",
                "Google Kubernetes Engine",
                _component(
                    "Auth Middleware",
                    "Authenticates callers and enforces quotas",
                    _code("AuthMiddleware", "+authenticate(token): Principal"),
                ),
                _component(
                    "Trip Controller",
                    "Accepts trip requests and publishes events",
                    _code("TripController", "+requestTrip(request): TripId"),
                ),
            ),
            _container(
                "Dispatch Service",
                "Matches riders with nearby drivers and prices fares",
                "Java on Cloud Run",
                "Cloud Run",
                _component(
                    "Matching Engine",
                    "Scores candidate drivers",
                    _code("MatchingEngine", "+match(trip): Assignment"),
                ),
                _component(
                    "Fare Pricer",
                    "Quotes surge-aware fares",
                    _code("FarePricer", "+quote(trip): Fare"),
                ),
            ),
            _container(
                "Location Ingest",
                "Accepts driver GPS pings at high volume",
                "Rust on Cloud Run",
                "Cloud Run",
            ),
            _container(
                "Notification Worker",
                "Sends push and SMS alerts",
                "Node.js",
                "Cloud Functions",
            ),
            _container("Event Bus", "Carries trip and location events", "Pub/Sub", "Pub/Sub"),
            _container("Trip Store", "Transactional trip and account records", "Spanner", "Cloud Spanner"),
            _container("Location Cache", "Latest driver positions", "Redis", "Memorystore"),
            _container("Fleet Time Series", "High-rate telemetry history", "Bigtable", "Bigtable"),
            _container("Telemetry Lake", "Analytics warehouse", "BigQuery", "BigQuery"),
            _container("Location Archive", "Daily telemetry snapshots", "Object storage", "Cloud Storage"),
            _container("ETA Model", "Arrival time predictions", "Vertex AI endpoint", "Vertex AI"),
        ],
        "flows": [
            {
                "from": a,
                "to": b,
                "description": d,
                "technology": t,
                "evidence": BRIEF,
            }
            for a, b, d, t in FLOWS
        ],
        "assumptions": ["All architecture and deployment facts in this example are fictional."],
        "gaps": [],
        "deployment": {
            "provider": "gcp",
            "nodes": [
                {
                    "name": "Example Organization",
                    "type": "organization",
                    "children": [
                        {
                            "name": "ridepulse-prod",
                            "type": "project",
                            "children": [
                                {
                                    "name": "us-central1",
                                    "type": "region",
                                    "children": [
                                        {
                                            "name": "ridepulse-vpc",
                                            "type": "vpc",
                                            "children": [
                                                {"name": "app-subnet", "type": "subnet"},
                                                {"name": "data-subnet", "type": "subnet"},
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
            "placements": [
                {"element": e, "node": n}
                for e, n in [
                    ("Rider Gateway", "app-subnet"),
                    ("Dispatch Service", "us-central1"),
                    ("Location Ingest", "us-central1"),
                    ("Notification Worker", "us-central1"),
                    ("ETA Model", "us-central1"),
                    ("Location Cache", "data-subnet"),
                    ("Event Bus", "ridepulse-prod"),
                    ("Trip Store", "ridepulse-prod"),
                    ("Fleet Time Series", "ridepulse-prod"),
                    ("Telemetry Lake", "ridepulse-prod"),
                    ("Location Archive", "ridepulse-prod"),
                ]
            ],
        },
    }
    return deepcopy(plan)


def ridepulse_model(gcp_icon_style: str | None = None) -> dict:
    return compile_plan(ridepulse_plan(), gcp_icon_style)[0]


DYNAMIC_SEQUENCE = """%% Illustrative scenario; authored separately from schema 2.0 C4 views.
sequenceDiagram
  actor Rider
  participant Gateway as Rider Gateway
  participant Bus as Event Bus
  participant Dispatch as Dispatch Service
  participant Cache as Location Cache
  participant ETA as ETA Model
  participant Store as Trip Store
  actor Driver
  Rider->>Gateway: Request trip (HTTPS)
  Gateway->>Bus: Publish trip requested
  Bus->>Dispatch: Deliver trip event
  Dispatch->>Cache: Find nearby drivers
  Dispatch->>ETA: Predict arrival times
  Dispatch->>Store: Record assignment
  Dispatch->>Bus: Publish driver assignment
  Bus-->>Gateway: Deliver assignment
  Gateway-->>Driver: Offer trip (gRPC)
  Driver-->>Gateway: Accept
  Gateway-->>Rider: Driver on the way
"""
