"""Conservative static AWS and GCP signals; SDK usage never establishes deployment topology."""

from __future__ import annotations
import re
from .aws import resolve_service

# Service label -> (Terraform resource types, CloudFormation types, SDK pattern). Only
# declarations count as infrastructure: `resource "aws_s3_bucket" "x"` (HCL),
# `"aws_s3_bucket": {` (.tf.json) and `Type: AWS::S3::Bucket`, not references
# (`aws_s3_bucket.x.id`) or attachment types (bucket policies, Lambda permissions).
AWS_SERVICES = {
    "Amazon Simple Storage Service": (
        ["aws_s3_bucket"],
        ["S3::Bucket"],
        r"boto3\.(?:client|resource)\(['\"]s3['\"]|@aws-sdk/client-s3|software\.amazon\.awssdk\.services\.s3|Amazon\.S3",
    ),
    "AWS Lambda": (
        ["aws_lambda_function"],
        ["Lambda::Function"],
        r"@aws-sdk/client-lambda|boto3\.client\(['\"]lambda['\"]",
    ),
    "Amazon DynamoDB": (
        ["aws_dynamodb_table"],
        ["DynamoDB::Table", "DynamoDB::GlobalTable"],
        r"@aws-sdk/client-dynamodb|boto3\.(?:client|resource)\(['\"]dynamodb['\"]",
    ),
    "Amazon Simple Queue Service": (
        ["aws_sqs_queue"],
        ["SQS::Queue"],
        r"@aws-sdk/client-sqs|boto3\.client\(['\"]sqs['\"]",
    ),
    "Amazon Elastic Container Service": (
        ["aws_ecs_service", "aws_ecs_cluster"],
        ["ECS::Service", "ECS::Cluster"],
        r"@aws-sdk/client-ecs",
    ),
    "Amazon Relational Database Service": (
        ["aws_db_instance", "aws_rds_cluster"],
        ["RDS::DBInstance", "RDS::DBCluster"],
        None,
    ),
    "Amazon Elastic Compute Cloud": (["aws_instance"], ["EC2::Instance"], None),
}


def declaration_pattern(terraform: list[str], cloud: str, stacks: list[str]) -> re.Pattern:
    """Terraform `resource "type" "name"` / .tf.json `"type": {`, and stack `Type: <cloud>::X`."""
    types = "|".join(re.escape(t) for t in terraform)
    kinds = "|".join(re.escape(t) for t in stacks) or "(?!)"
    return re.compile(
        rf"\bresource\s+\"(?:{types})\"\s+\""
        rf"|\"(?:{types})\"\s*:\s*\{{"
        rf"|\bType[\"']?\s*:\s*[\"']?{cloud}::(?:{kinds})(?![\w:])"
    )


AWS_PATTERNS = {
    service: (
        declaration_pattern(terraform, "AWS", stacks),
        re.compile(sdk, re.I) if sdk else None,
    )
    for service, (terraform, stacks, sdk) in AWS_SERVICES.items()
}


def signals_in(files: dict[str, str], patterns: dict, provider: str = "aws") -> list[dict]:
    """One signal per declaration (kind infrastructure) or SDK use (kind sdk), in file order."""
    signals = []
    for path, text in sorted(files.items()):
        for service, (declaration, sdk) in patterns.items():
            service_id = resolve_service(service, provider)
            if not service_id:
                continue
            matches = sorted(
                (match.start(), kind)
                for kind, pattern in (("infrastructure", declaration), ("sdk", sdk))
                if pattern is not None
                for match in pattern.finditer(text)
            )
            for start, kind in matches:
                line = text.count("\n", 0, start) + 1
                signals.append(
                    {
                        "service": service_id,
                        "reference": path,
                        "line": line,
                        "excerpt": text.splitlines()[line - 1][:240],
                        "kind": kind,
                        "confidence": 0.85,
                    }
                )
    return signals


def detect_aws(files: dict[str, str]) -> list[dict]:
    return signals_in(files, AWS_PATTERNS)


# Service label -> (Terraform resource types, SDK pattern). Labels resolve to catalogue
# icons. Only declarations (`resource "google_storage_bucket" "x"`) and `gcloud run deploy`
# count as infrastructure; references and IAM bindings do not.
GCP_SERVICES = {
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


GCP_PATTERNS = {
    service: (_declaration(terraform, service), re.compile(sdk, re.I) if sdk else None)
    for service, (terraform, sdk) in GCP_SERVICES.items()
}


def detect_gcp(files: dict[str, str]) -> list[dict]:
    return signals_in(files, GCP_PATTERNS, "gcp")
