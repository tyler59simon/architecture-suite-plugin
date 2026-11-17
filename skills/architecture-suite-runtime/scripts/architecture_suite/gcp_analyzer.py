"""Conservative static GCP signals; SDK usage never establishes deployment topology."""

from __future__ import annotations
import re
from .aws_analyzer import declaration_pattern, signals_in

# Service label -> (Terraform resource types, SDK pattern). Labels resolve to catalogue
# icons. Only declarations (`resource "google_storage_bucket" "x"`) and `gcloud run deploy`
# count as infrastructure; references and IAM bindings do not.
SERVICES = {
    "Cloud Storage": (
        ["google_storage_bucket"],
        r"@google-cloud/storage|google\.cloud(?:\.|\s+import\s+)storage|cloud\.google\.com/go/storage",
    ),
    "Cloud Run": (
        ["google_cloud_run_service", "google_cloud_run_v2_service"],
        r"@google-cloud/run|google\.cloud(?:\.|\s+import\s+)run",
    ),
    "Pub/Sub": (
        ["google_pubsub_topic", "google_pubsub_subscription"],
        r"@google-cloud/pubsub|google\.cloud(?:\.|\s+import\s+)pubsub\w*|cloud\.google\.com/go/pubsub",
    ),
    "Cloud Spanner": (
        ["google_spanner_instance", "google_spanner_database"],
        r"@google-cloud/spanner|google\.cloud(?:\.|\s+import\s+)spanner",
    ),
    "BigQuery": (
        ["google_bigquery_dataset", "google_bigquery_table"],
        r"@google-cloud/bigquery|google\.cloud(?:\.|\s+import\s+)bigquery",
    ),
    "Bigtable": (
        ["google_bigtable_instance", "google_bigtable_table"],
        r"@google-cloud/bigtable|google\.cloud(?:\.|\s+import\s+)bigtable",
    ),
    "Google Kubernetes Engine": (["google_container_cluster", "google_container_node_pool"], None),
    "Cloud SQL": (["google_sql_database_instance"], None),
    "Memorystore": (["google_redis_instance"], None),
    "Compute Engine": (["google_compute_instance"], None),
    "Cloud Functions": (["google_cloudfunctions_function", "google_cloudfunctions2_function"], None),
}


def _declaration(terraform: list[str], service: str) -> re.Pattern:
    pattern = declaration_pattern(terraform, "GCP", []).pattern
    if service == "Cloud Run":
        pattern += r"|gcloud run deploy"
    return re.compile(pattern)


PATTERNS = {
    service: (_declaration(terraform, service), re.compile(sdk, re.I) if sdk else None)
    for service, (terraform, sdk) in SERVICES.items()
}


def detect_gcp(files: dict[str, str]) -> list[dict]:
    return signals_in(files, PATTERNS, "gcp")
