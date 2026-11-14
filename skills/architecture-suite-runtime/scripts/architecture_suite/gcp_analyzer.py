"""Conservative static GCP signals; SDK usage never establishes deployment topology."""

from __future__ import annotations
import re
from .aws import resolve_service

# Service label -> infrastructure/SDK patterns. Labels resolve to catalogue icons.
PATTERNS = {
    "Cloud Storage": r"google_storage_bucket\b|@google-cloud/storage|google\.cloud(?:\.|\s+import\s+)storage|cloud\.google\.com/go/storage",
    "Cloud Run": r"google_cloud_run(?:_v2)?_service\b|gcloud run deploy|@google-cloud/run|google\.cloud(?:\.|\s+import\s+)run",
    "Pub/Sub": r"google_pubsub_(?:topic|subscription)\b|@google-cloud/pubsub|google\.cloud(?:\.|\s+import\s+)pubsub\w*|cloud\.google\.com/go/pubsub",
    "Cloud Spanner": r"google_spanner_(?:instance|database)\b|@google-cloud/spanner|google\.cloud(?:\.|\s+import\s+)spanner",
    "BigQuery": r"google_bigquery_(?:dataset|table)\b|@google-cloud/bigquery|google\.cloud(?:\.|\s+import\s+)bigquery",
    "Bigtable": r"google_bigtable_(?:instance|table)\b|@google-cloud/bigtable|google\.cloud(?:\.|\s+import\s+)bigtable",
    "Google Kubernetes Engine": r"google_container_(?:cluster|node_pool)\b",
    "Cloud SQL": r"google_sql_database_instance\b",
    "Memorystore": r"google_redis_instance\b",
    "Compute Engine": r"google_compute_instance\b",
    "Cloud Functions": r"google_cloudfunctions2?_function\b",
}


def detect_gcp(files: dict[str, str]) -> list[dict]:
    signals = []
    for path, text in sorted(files.items()):
        for service, pattern in PATTERNS.items():
            for match in re.finditer(pattern, text, re.I):
                service_id = resolve_service(service, "gcp")
                if service_id:
                    line = text.count("\n", 0, match.start()) + 1
                    signals.append(
                        {
                            "service": service_id,
                            "reference": path,
                            "line": line,
                            "excerpt": text.splitlines()[line - 1][:240],
                            "kind": "infrastructure"
                            if match.group().startswith(("google_", "gcloud"))
                            else "sdk",
                            "confidence": 0.85,
                        }
                    )
    return signals
