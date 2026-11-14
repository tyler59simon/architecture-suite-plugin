"""Fictional reproducible examples, never analysis defaults."""

from copy import deepcopy
from .plan import compile_plan

SCENARIOS = (
    {
        "id": "order-platform",
        "name": "Order Platform",
        "pattern": "API and asynchronous worker",
    },
    {
        "id": "research-portal",
        "name": "Research Portal",
        "pattern": "Portal and query service",
    },
    {
        "id": "telemetry-platform",
        "name": "Telemetry Platform",
        "pattern": "Ingestion and processing",
    },
)


def example_plan(index: int = 0) -> dict:
    scenario = SCENARIOS[index]

    def code(name, member):
        return {
            "name": name,
            "description": "Illustrative implementation",
            "kind": "class",
            "members": [member],
            "evidence": "fictional brief",
        }

    plan = {
        "schema_version": "architecture-plan/v1",
        "system": {
            "name": scenario["name"],
            "description": scenario["pattern"],
            "classification": "Synthetic, non-production example",
            "scope": "Illustrative owned applications",
        },
        "people": [
            {
                "name": "Customer",
                "description": "Submits requests",
                "evidence": "fictional brief",
            }
        ],
        "external_systems": [
            {
                "name": "Payment Provider",
                "description": "Authorizes payments",
                "evidence": "fictional brief",
            }
        ],
        "containers": [
            {
                "name": "API",
                "description": "Accepts customer requests",
                "technology": "Python HTTPS",
                "aws_service": "Amazon ECS",
                "evidence": "fictional brief",
                "components": [
                    {
                        "name": "Request Controller",
                        "description": "Validates and routes requests",
                        "evidence": "fictional brief",
                        "code": [
                            code("RequestHandler", "+handle(request): Response"),
                            code("RequestValidator", "+validate(request): bool"),
                        ],
                    },
                    {
                        "name": "Payment Adapter",
                        "description": "Calls payment provider",
                        "evidence": "fictional brief",
                        "code": [code("PaymentClient", "+authorize(order): Result")],
                    },
                ],
            },
            {
                "name": "Worker",
                "description": "Processes queued requests",
                "technology": "Go",
                "aws_service": "AWS Lambda",
                "evidence": "fictional brief",
                "components": [
                    {
                        "name": "Fulfillment",
                        "description": "Dispatches fulfillment work",
                        "evidence": "fictional brief",
                        "code": [code("FulfillmentJob", "+run(order): Result")],
                    }
                ],
            },
            {
                "name": "Order Queue",
                "description": "Buffers accepted work",
                "technology": "SQS",
                "aws_service": "Amazon SQS",
                "evidence": "fictional brief",
            },
            {
                "name": "Order Store",
                "description": "Persists request state",
                "technology": "DynamoDB",
                "aws_service": "Amazon DynamoDB",
                "evidence": "fictional brief",
            },
        ],
        "flows": [
            {
                "from": a,
                "to": b,
                "description": d,
                "technology": t,
                "evidence": "fictional brief",
            }
            for a, b, d, t in [
                ("Customer", "RequestHandler", "Submits request", "HTTPS"),
                ("RequestHandler", "RequestValidator", "Validates input", "method"),
                ("RequestHandler", "PaymentClient", "Requests authorization", "method"),
                ("PaymentClient", "Payment Provider", "Authorizes payment", "HTTPS"),
                ("RequestHandler", "Order Queue", "Queues accepted work", "SQS"),
                ("Order Queue", "FulfillmentJob", "Delivers work", "event"),
                ("FulfillmentJob", "Order Store", "Stores result", "DynamoDB"),
            ]
        ],
        "assumptions": [
            "All architecture and deployment facts in this example are fictional."
        ],
        "gaps": [],
        "deployment": {
            "nodes": [
                {
                    "name": "Example Account",
                    "type": "account",
                    "children": [
                        {
                            "name": "us-east-1",
                            "type": "region",
                            "children": [
                                {
                                    "name": "Application VPC",
                                    "type": "vpc",
                                    "children": [
                                        {"name": "Private Subnet", "type": "subnet"}
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
            "placements": [
                {
                    "element": name,
                    "node": "Private Subnet" if name == "API" else "us-east-1",
                }
                for name in ("API", "Worker", "Order Queue", "Order Store")
            ],
        },
    }
    return deepcopy(plan)


def example_model(index: int = 0) -> dict:
    return compile_plan(example_plan(index))[0]


def all_example_models() -> list[tuple[dict, dict]]:
    return [(scenario, example_model(i)) for i, scenario in enumerate(SCENARIOS)]
