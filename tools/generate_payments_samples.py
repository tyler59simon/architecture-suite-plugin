"""Generate the fictional PayStream online payments example on AWS and on Google Cloud.

    python tools/generate_payments_samples.py   (needs `architecture-suite` next to this Python)

One logical architecture (people, external systems, containers, components, code and flows)
is bound twice, once to AWS services and once to Google Cloud services, and each binding is
rendered as a complete package:

  examples/payments/plans/<cloud>-architecture-plan.md   checked-in, editable input
  examples/payments/<cloud>/01-system-context ... 04-code   C4 levels 1-4
  examples/payments/<cloud>/05-overview            executive and hierarchy overviews
  examples/payments/<cloud>/06-<cloud>-deployment  deployment diagram
  examples/payments/<cloud>/overview-vector-only/  progressive, small-multiples, complete (SVG/Draw.io)
  examples/payments/<cloud>/c4-dynamic.mmd         card payment authorization sequence

Levels 1-4 are identical in both packages apart from cloud icons; the deployment differs.
Every fact here is fictional.
"""

from copy import deepcopy
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/architecture-suite-runtime/scripts"))
from architecture_suite.draft import render_plan  # noqa: E402

OUT = ROOT / "examples/payments"
CLI = Path(sys.executable).with_name(
    "architecture-suite.exe" if sys.platform == "win32" else "architecture-suite"
)
BRIEF = "fictional brief"
CLOUDS = ("aws", "gcp")


def code(name, kind, *members):
    return {
        "name": name,
        "description": "Illustrative implementation",
        "kind": kind,
        "members": list(members),
        "evidence": BRIEF,
    }


def component(name, description, technology, *code_items):
    return {
        "name": name,
        "description": description,
        "technology": technology,
        "evidence": BRIEF,
        "code": list(code_items),
    }


# name, description, technology, {"aws": service, "gcp": service}, components
CONTAINERS = [
    ("Checkout Web SDK", "Hosted payment fields embedded in merchant checkout pages",
     "TypeScript in the shopper's browser", {}, []),
    ("Merchant Dashboard", "Payments, refunds, disputes and payouts for merchants",
     "React single-page app", {"aws": "Amazon CloudFront", "gcp": "Cloud CDN"}, []),
    ("Payments API", "Public REST API for payment intents, captures and refunds",
     "Go", {"aws": "Amazon ECS", "gcp": "Cloud Run"}, [
         component("Merchant Authenticator", "Validates secret API keys and scopes", "Go",
                   code("ApiKeyAuthenticator", "class",
                        "+authenticate(apiKey): Merchant", "+requireScope(merchant, scope)")),
         component("Idempotency Guard", "Makes retried requests return the original result", "Go",
                   code("IdempotencyGuard", "class",
                        "+reserve(key, requestHash): Reservation", "+complete(key, response)")),
         component("Payment Intents Controller", "Creates and confirms payment intents", "Go",
                   code("PaymentIntentController", "class",
                        "+create(request): PaymentIntent", "+confirm(id, cardToken): PaymentIntent",
                        "+refund(id, amount): Refund")),
     ]),
    ("Card Vault", "Tokenizes card numbers inside the cardholder data environment",
     "Rust", {"aws": "Amazon ECS", "gcp": "Google Kubernetes Engine"}, [
         component("Card Tokenizer", "Swaps card numbers for single-purpose tokens", "Rust",
                   code("CardTokenizer", "class",
                        "+tokenize(pan, expiry): CardToken", "+detokenize(token): CardData")),
         component("Envelope Encryptor", "Encrypts card data with per-record data keys", "Rust",
                   code("EnvelopeEncryptor", "class",
                        "+encrypt(plaintext, keyId): Ciphertext", "+decrypt(ciphertext): Bytes")),
     ]),
    ("Payment Orchestrator", "Drives each payment through authorization, capture and refund",
     "Java", {"aws": "Amazon EKS", "gcp": "Google Kubernetes Engine"}, [
         component("Payment State Machine", "Owns payment state transitions and retries", "Java",
                   code("PaymentStateMachine", "class",
                        "+authorize(payment): Authorization", "+capture(payment, amount): Capture",
                        "+refund(payment, amount): Refund"),
                   code("PaymentState", "interface", "+next(event): PaymentState")),
         component("Acquirer Router", "Chooses the acquiring connection by card and region", "Java",
                   code("AcquirerRouter", "class", "+route(payment): AcquirerConnection")),
         component("3DS Handler", "Runs 3-D Secure cardholder authentication", "Java",
                   code("ThreeDSecureClient", "class",
                        "+authenticate(payment): AuthenticationResult")),
     ]),
    ("Fraud Scoring", "Scores each payment for fraud risk before authorization",
     "Python ML model", {"aws": "Amazon SageMaker", "gcp": "Vertex AI"}, [
         component("Risk Scorer", "Returns a risk score from the hosted model", "Python",
                   code("RiskScorer", "class", "+score(payment): RiskScore")),
         component("Rules Engine", "Applies merchant and platform block rules", "Python",
                   code("RuleSet", "class", "+evaluate(payment, score): Decision")),
     ]),
    ("Ledger Service", "Double-entry ledger of balances, fees and payouts",
     "Kotlin", {"aws": "Amazon ECS", "gcp": "Cloud Run"}, [
         component("Journal Writer", "Posts balanced journal entries for money movements", "Kotlin",
                   code("JournalWriter", "class", "+post(entries): JournalId")),
         component("Balance Calculator", "Computes available and pending merchant balances", "Kotlin",
                   code("BalanceCalculator", "class", "+balance(merchantId, currency): Balance")),
     ]),
    ("Webhook Dispatcher", "Signs and delivers payment events to merchants, with retries",
     "Node.js", {"aws": "AWS Lambda", "gcp": "Cloud Functions"}, []),
    ("Settlement Worker", "Reconciles acquirer settlement files and initiates payouts",
     "Python batch jobs", {"aws": "AWS Batch", "gcp": "Batch"}, []),
    ("Payments Database", "Payment intents, merchants and API keys", "PostgreSQL",
     {"aws": "Amazon Aurora", "gcp": "Cloud SQL"}, []),
    ("Ledger Store", "Strongly consistent journal and balance records", "Distributed SQL",
     {"aws": "Amazon Aurora", "gcp": "Cloud Spanner"}, []),
    ("Idempotency Cache", "Short-lived idempotency keys and responses", "Redis",
     {"aws": "Amazon ElastiCache", "gcp": "Memorystore"}, []),
    ("Payment Event Stream", "Ordered payment lifecycle events", "Event bus",
     {"aws": "Amazon EventBridge", "gcp": "Pub/Sub"}, []),
    ("Vault Key Store", "Key-encryption keys for the card vault", "Managed KMS",
     {"aws": "AWS Key Management Service", "gcp": "Key Management Service"}, []),
    ("Reporting Warehouse", "Reconciliation and finance analytics", "Columnar warehouse",
     {"aws": "Amazon Redshift", "gcp": "BigQuery"}, []),
    ("Settlement Archive", "Raw acquirer settlement files", "Object storage",
     {"aws": "Amazon S3", "gcp": "Cloud Storage"}, []),
]

FLOWS = [
    ("Shopper", "Checkout Web SDK", "Enters card details at checkout", "HTTPS"),
    ("Checkout Web SDK", "Card Tokenizer", "Submits card data for a token", "HTTPS"),
    ("Checkout Web SDK", "Payment Intents Controller", "Confirms the payment with the card token", "HTTPS"),
    ("Merchant", "Merchant Dashboard", "Reviews payments, refunds and payouts", "HTTPS"),
    ("Merchant Dashboard", "Payment Intents Controller", "Lists payments and issues refunds", "HTTPS"),
    ("Merchant Webhook Endpoint", "Merchant Authenticator", "Calls the API server-side with a secret key", "HTTPS"),
    ("Merchant Authenticator", "Payments Database", "Looks up API keys", "SQL"),
    ("Payment Intents Controller", "Idempotency Guard", "Reserves the idempotency key", "in-process"),
    ("Idempotency Guard", "Idempotency Cache", "Stores request keys and responses", "Redis"),
    ("Payment Intents Controller", "Payments Database", "Persists payment intents", "SQL"),
    ("Payment Intents Controller", "Payment State Machine", "Starts authorization", "gRPC"),
    ("Payment State Machine", "Risk Scorer", "Requests a fraud score", "gRPC"),
    ("PaymentStateMachine", "PaymentState", "Delegates each transition to the current state", "in-process"),
    ("Risk Scorer", "Rules Engine", "Applies block and review rules", "in-process"),
    ("Risk Analyst", "Rules Engine", "Reviews flagged payments and tunes rules", "HTTPS"),
    ("Payment State Machine", "3DS Handler", "Requests cardholder authentication", "in-process"),
    ("3DS Handler", "3-D Secure Directory Server", "Authenticates the cardholder", "EMV 3DS over HTTPS"),
    ("Payment State Machine", "Acquirer Router", "Sends authorization and capture", "in-process"),
    ("Acquirer Router", "Card Tokenizer", "Detokenizes the card for the network request", "mTLS"),
    ("Acquirer Router", "Acquirer Processor", "Authorizes, captures and refunds", "ISO 8583 over TLS"),
    ("Card Tokenizer", "Envelope Encryptor", "Encrypts card records", "in-process"),
    ("Envelope Encryptor", "Vault Key Store", "Wraps and unwraps data keys", "KMS API"),
    ("Payment State Machine", "Payment Event Stream", "Publishes payment lifecycle events", "events"),
    ("Payment Event Stream", "Journal Writer", "Delivers captured, refunded and fee events", "events"),
    ("Journal Writer", "Ledger Store", "Posts double-entry journal entries", "SQL"),
    ("Journal Writer", "Reporting Warehouse", "Streams journal entries", "batch export"),
    ("Payment Event Stream", "Webhook Dispatcher", "Delivers merchant-facing events", "events"),
    ("Webhook Dispatcher", "Merchant Webhook Endpoint", "Delivers signed webhooks", "HTTPS"),
    ("Settlement Worker", "Acquirer Processor", "Downloads settlement files", "SFTP"),
    ("Settlement Worker", "Settlement Archive", "Archives settlement files", "object API"),
    ("Settlement Worker", "Balance Calculator", "Reconciles merchant balances", "gRPC"),
    ("Settlement Worker", "Bank Payout Rail", "Initiates merchant payouts", "ISO 20022"),
    ("Finance Operations", "Reporting Warehouse", "Runs reconciliation and payout reports", "SQL"),
]


def placements(cloud):
    common = {
        "Checkout Web SDK": "browser-runtime",
        "Payments API": "app-subnet",
        "Payment Orchestrator": "orchestrator-cluster",
        "Ledger Service": "app-subnet",
        "Card Vault": "vault-cluster" if cloud == "gcp" else "cde-subnet",
        "Payments Database": "data-subnet",
        "Ledger Store": "data-subnet" if cloud == "aws" else "paystream-prod",
        "Idempotency Cache": "data-subnet",
        "Reporting Warehouse": "data-subnet" if cloud == "aws" else "paystream-prod",
        "Fraud Scoring": "primary-region",
        "Webhook Dispatcher": "primary-region",
        "Settlement Worker": "primary-region",
        "Payment Event Stream": "primary-region",
        "Vault Key Store": "primary-region",
        "Settlement Archive": "primary-region",
        "Merchant Dashboard": "paystream-prod",
    }
    return [{"element": e, "node_id": n} for e, n in common.items()]


def deployment(cloud):
    browser = {
        "id": "shopper-browser", "name": "Shopper browser", "type": "device",
        "children": [{"id": "browser-runtime", "name": "Web browser", "type": "execution-environment"}],
    }
    vpc = {
        "id": "payments-vpc", "name": "payments-vpc", "type": "vpc",
        "children": [
            {"id": "app-subnet", "name": "app-subnet", "type": "subnet", "children": [
                {"id": "orchestrator-cluster", "name": "orchestrator-cluster", "type": "cluster"},
            ]},
            {"id": "cde-subnet", "name": "cde-subnet (cardholder data)", "type": "subnet",
             "children": [{"id": "vault-cluster", "name": "vault-cluster", "type": "cluster"}]
             if cloud == "gcp" else []},
            {"id": "data-subnet", "name": "data-subnet", "type": "subnet"},
        ],
    }
    if cloud == "aws":
        nodes = [{
            "id": "paystream-prod", "name": "PayStream production account", "type": "account",
            "children": [{"id": "primary-region", "name": "eu-west-1", "type": "region",
                          "children": [vpc]}],
        }, browser]
        return {"provider": "aws", "nodes": nodes, "placements": placements(cloud)}
    nodes = [{
        "id": "example-org", "name": "Example Organization", "type": "organization",
        "children": [{
            "id": "paystream-prod", "name": "paystream-prod", "type": "project",
            "children": [{"id": "primary-region", "name": "europe-west1", "type": "region",
                          "children": [vpc]}],
        }],
    }, browser]
    return {"provider": "gcp", "nodes": nodes, "placements": placements(cloud)}


def payments_plan(cloud):
    field = cloud + "_service"
    containers = []
    for name, description, technology, services, components in CONTAINERS:
        item = {"name": name, "description": description, "technology": technology,
                "evidence": BRIEF}
        if cloud in services:
            item[field] = services[cloud]
        if components:
            item["components"] = deepcopy(components)
        containers.append(item)
    plan = {
        "schema_version": "architecture-plan/v1",
        "system": {
            "name": "PayStream",
            "description": "Online payments platform: checkout, card processing, ledger and payouts",
            "classification": "Synthetic, non-production example",
            "scope": f"Illustrative owned services running on {'AWS' if cloud == 'aws' else 'Google Cloud'}",
        },
        "people": [
            {"name": "Shopper", "description": "Pays for orders at merchant checkouts", "evidence": BRIEF},
            {"name": "Merchant", "description": "Accepts payments and receives payouts", "evidence": BRIEF},
            {"name": "Risk Analyst", "description": "Reviews flagged payments and fraud rules", "evidence": BRIEF},
            {"name": "Finance Operations", "description": "Reconciles settlements and payouts", "evidence": BRIEF},
        ],
        "external_systems": [
            {"name": "Acquirer Processor", "description": "Card authorization, capture and settlement", "evidence": BRIEF},
            {"name": "3-D Secure Directory Server", "description": "Card network cardholder authentication", "evidence": BRIEF},
            {"name": "Bank Payout Rail", "description": "Bank transfers for merchant payouts", "evidence": BRIEF},
            {"name": "Merchant Webhook Endpoint", "description": "Merchant back-end that calls the API and receives events", "evidence": BRIEF},
        ],
        "containers": containers,
        "flows": [
            {"from": a, "to": b, "description": d, "technology": t, "evidence": BRIEF}
            for a, b, d, t in FLOWS
        ],
        "assumptions": ["All architecture and deployment facts in this example are fictional."],
        "gaps": [],
        "deployment": deployment(cloud),
    }
    if cloud == "gcp":
        plan["gcp_icon_style"] = "auto"
    return plan


DYNAMIC_SEQUENCE = """%% Illustrative scenario; authored separately from schema 2.0 C4 views.
sequenceDiagram
  actor Shopper
  participant SDK as Checkout Web SDK
  participant Vault as Card Vault
  participant API as Payments API
  participant Orch as Payment Orchestrator
  participant Fraud as Fraud Scoring
  participant DS as 3-D Secure Directory Server
  participant Acq as Acquirer Processor
  participant Bus as Payment Event Stream
  participant Ledger as Ledger Service
  Shopper->>SDK: Enter card details
  SDK->>Vault: Tokenize card
  Vault-->>SDK: Card token
  SDK->>API: Confirm payment intent (token, idempotency key)
  API->>Orch: Authorize payment
  Orch->>Fraud: Score payment
  Fraud-->>Orch: Risk score and decision
  alt challenge required
    Orch->>DS: Authenticate cardholder
    DS-->>Orch: Authentication result
  end
  Orch->>Vault: Detokenize for network request
  Orch->>Acq: Authorization request
  Acq-->>Orch: Approved
  Orch->>Bus: payment.authorized
  Bus->>Ledger: Post pending journal entries
  Orch-->>API: Authorized
  API-->>SDK: Payment succeeded
"""

JOBS = {
    ".": ["--level", "all", "--overview-style", "executive,hierarchy"],
    # These overview styles exceed the 6,000 px PNG width limit at this size: vector formats only.
    "overview-vector-only": [
        "--level", "overview", "--overview-style", "progressive,small-multiples,complete",
    ],
}


def run(*args, label):
    result = subprocess.run([str(CLI), *map(str, args)], capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(f"{label} failed\n{result.stdout}{result.stderr}")
    return result


README = """# PayStream: online payments example (fictional)

One payments architecture, rendered twice: once on AWS and once on Google Cloud. The editable
plans are in `plans/`. Each cloud folder is a complete package with C4 levels 1-4, overviews, the cloud deployment diagram,
a card-payment sequence (`c4-dynamic.mmd`) and the fidelity and architecture reports. Levels 1-4
match apart from cloud service icons; the deployment diagrams differ.

| | AWS | Google Cloud |
| --- | --- | --- |
| Plan | [plans/aws-architecture-plan.md](plans/aws-architecture-plan.md) | [plans/gcp-architecture-plan.md](plans/gcp-architecture-plan.md) |
| L1 system context | [aws/01-system-context](aws/01-system-context) | [gcp/01-system-context](gcp/01-system-context) |
| L2 containers | [aws/02-containers](aws/02-containers) | [gcp/02-containers](gcp/02-containers) |
| L3 components | [aws/03-components](aws/03-components) | [gcp/03-components](gcp/03-components) |
| L4 code | [aws/04-code](aws/04-code) | [gcp/04-code](gcp/04-code) |
| Overviews | [aws/05-overview](aws/05-overview) | [gcp/05-overview](gcp/05-overview) |
| Deployment | [aws/06-aws-deployment](aws/06-aws-deployment) | [gcp/06-gcp-deployment](gcp/06-gcp-deployment) |
| Progressive, small-multiples, complete (SVG/Draw.io) | [aws/overview-vector-only](aws/overview-vector-only) | [gcp/overview-vector-only](gcp/overview-vector-only) |

Regenerate with `python tools/generate_payments_samples.py`. Every fact here is fictional.
"""


def main():
    (OUT / "plans").mkdir(parents=True, exist_ok=True)
    for cloud in CLOUDS:
        folder = OUT / cloud
        if folder.exists():
            shutil.rmtree(folder)
        plan_path = OUT / "plans" / f"{cloud}-architecture-plan.md"
        plan_path.write_bytes(render_plan(payments_plan(cloud)).encode("utf-8"))
        run("plan-lint", "--plan", plan_path, "--strict", label=f"{cloud} plan-lint")
        for job, extra in JOBS.items():
            target = folder if job == "." else folder / job
            formats = "mermaid,drawio,svg" if job.endswith("vector-only") else "mermaid,drawio,png,svg"
            run("plan-render", "--plan", plan_path, "--output", target, "--format", formats,
                "--confirm-write", *extra, label=f"{cloud} {job} render")
        (folder / "c4-dynamic.mmd").write_bytes(DYNAMIC_SEQUENCE.encode("utf-8"))
        print(f"{cloud}: {sum(1 for p in folder.rglob('*') if p.is_file())} files")
    (OUT / "README.md").write_bytes(README.encode("utf-8"))


if __name__ == "__main__":
    main()
