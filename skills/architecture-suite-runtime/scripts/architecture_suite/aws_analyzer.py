"""Conservative static AWS signals; SDK usage never establishes deployment topology."""

from __future__ import annotations
import re
from .aws import resolve_service

PATTERNS = {
    "Amazon Simple Storage Service": r"AWS::S3::|aws_s3_bucket\b|boto3\.(?:client|resource)\(['\"]s3['\"]|@aws-sdk/client-s3|software\.amazon\.awssdk\.services\.s3|Amazon\.S3",
    "AWS Lambda": r"AWS::Lambda::|aws_lambda_function\b|@aws-sdk/client-lambda|boto3\.client\(['\"]lambda['\"]",
    "Amazon DynamoDB": r"AWS::DynamoDB::|aws_dynamodb_table\b|@aws-sdk/client-dynamodb|boto3\.(?:client|resource)\(['\"]dynamodb['\"]",
    "Amazon Simple Queue Service": r"AWS::SQS::|aws_sqs_queue\b|@aws-sdk/client-sqs|boto3\.client\(['\"]sqs['\"]",
    "Amazon Elastic Container Service": r"AWS::ECS::|aws_ecs_(?:service|cluster)\b|@aws-sdk/client-ecs",
    "Amazon Relational Database Service": r"AWS::RDS::|aws_db_instance\b",
    "Amazon Elastic Compute Cloud": r"AWS::EC2::Instance|aws_instance\b",
}


def detect_aws(files: dict[str, str]) -> list[dict]:
    signals = []
    for path, text in sorted(files.items()):
        for service, pattern in PATTERNS.items():
            for match in re.finditer(pattern, text, re.I):
                service_id = resolve_service(service)
                if service_id:
                    line = text.count("\n", 0, match.start()) + 1
                    signals.append(
                        {
                            "service": service_id,
                            "reference": path,
                            "line": line,
                            "excerpt": text.splitlines()[line - 1][:240],
                            "kind": "infrastructure"
                            if "AWS::" in match.group()
                            or match.group().startswith("aws_")
                            else "sdk",
                            "confidence": 0.85,
                        }
                    )
    return signals
