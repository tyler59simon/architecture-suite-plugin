# Architecture plan

Drafted by bounded static analysis. Review candidate boundaries and gaps before publishing.

```yaml
schema_version: architecture-plan/v1
system:
  name: PayStream
  description: 'Online payments platform: checkout, card processing, ledger and payouts'
  classification: Synthetic, non-production example
  scope: Illustrative owned services running on Google Cloud
people:
- name: Shopper
  description: Pays for orders at merchant checkouts
  evidence: fictional brief
- name: Merchant
  description: Accepts payments and receives payouts
  evidence: fictional brief
- name: Risk Analyst
  description: Reviews flagged payments and fraud rules
  evidence: fictional brief
- name: Finance Operations
  description: Reconciles settlements and payouts
  evidence: fictional brief
external_systems:
- name: Acquirer Processor
  description: Card authorization, capture and settlement
  evidence: fictional brief
- name: 3-D Secure Directory Server
  description: Card network cardholder authentication
  evidence: fictional brief
- name: Bank Payout Rail
  description: Bank transfers for merchant payouts
  evidence: fictional brief
- name: Merchant Webhook Endpoint
  description: Merchant back-end that calls the API and receives events
  evidence: fictional brief
containers:
- name: Checkout Web SDK
  description: Hosted payment fields embedded in merchant checkout pages
  technology: TypeScript in the shopper's browser
  evidence: fictional brief
- name: Merchant Dashboard
  description: Payments, refunds, disputes and payouts for merchants
  technology: React single-page app
  evidence: fictional brief
  gcp_service: Cloud CDN
- name: Payments API
  description: Public REST API for payment intents, captures and refunds
  technology: Go
  evidence: fictional brief
  gcp_service: Cloud Run
  components:
  - name: Merchant Authenticator
    description: Validates secret API keys and scopes
    technology: Go
    evidence: fictional brief
    code:
    - name: ApiKeyAuthenticator
      description: Illustrative implementation
      kind: class
      members:
      - '+authenticate(apiKey): Merchant'
      - +requireScope(merchant, scope)
      evidence: fictional brief
  - name: Idempotency Guard
    description: Makes retried requests return the original result
    technology: Go
    evidence: fictional brief
    code:
    - name: IdempotencyGuard
      description: Illustrative implementation
      kind: class
      members:
      - '+reserve(key, requestHash): Reservation'
      - +complete(key, response)
      evidence: fictional brief
  - name: Payment Intents Controller
    description: Creates and confirms payment intents
    technology: Go
    evidence: fictional brief
    code:
    - name: PaymentIntentController
      description: Illustrative implementation
      kind: class
      members:
      - '+create(request): PaymentIntent'
      - '+confirm(id, cardToken): PaymentIntent'
      - '+refund(id, amount): Refund'
      evidence: fictional brief
- name: Card Vault
  description: Tokenizes card numbers inside the cardholder data environment
  technology: Rust
  evidence: fictional brief
  gcp_service: Google Kubernetes Engine
  components:
  - name: Card Tokenizer
    description: Swaps card numbers for single-purpose tokens
    technology: Rust
    evidence: fictional brief
    code:
    - name: CardTokenizer
      description: Illustrative implementation
      kind: class
      members:
      - '+tokenize(pan, expiry): CardToken'
      - '+detokenize(token): CardData'
      evidence: fictional brief
  - name: Envelope Encryptor
    description: Encrypts card data with per-record data keys
    technology: Rust
    evidence: fictional brief
    code:
    - name: EnvelopeEncryptor
      description: Illustrative implementation
      kind: class
      members:
      - '+encrypt(plaintext, keyId): Ciphertext'
      - '+decrypt(ciphertext): Bytes'
      evidence: fictional brief
- name: Payment Orchestrator
  description: Drives each payment through authorization, capture and refund
  technology: Java
  evidence: fictional brief
  gcp_service: Google Kubernetes Engine
  components:
  - name: Payment State Machine
    description: Owns payment state transitions and retries
    technology: Java
    evidence: fictional brief
    code:
    - name: PaymentStateMachine
      description: Illustrative implementation
      kind: class
      members:
      - '+authorize(payment): Authorization'
      - '+capture(payment, amount): Capture'
      - '+refund(payment, amount): Refund'
      evidence: fictional brief
    - name: PaymentState
      description: Illustrative implementation
      kind: interface
      members:
      - '+next(event): PaymentState'
      evidence: fictional brief
  - name: Acquirer Router
    description: Chooses the acquiring connection by card and region
    technology: Java
    evidence: fictional brief
    code:
    - name: AcquirerRouter
      description: Illustrative implementation
      kind: class
      members:
      - '+route(payment): AcquirerConnection'
      evidence: fictional brief
  - name: 3DS Handler
    description: Runs 3-D Secure cardholder authentication
    technology: Java
    evidence: fictional brief
    code:
    - name: ThreeDSecureClient
      description: Illustrative implementation
      kind: class
      members:
      - '+authenticate(payment): AuthenticationResult'
      evidence: fictional brief
- name: Fraud Scoring
  description: Scores each payment for fraud risk before authorization
  technology: Python ML model
  evidence: fictional brief
  gcp_service: Vertex AI
  components:
  - name: Risk Scorer
    description: Returns a risk score from the hosted model
    technology: Python
    evidence: fictional brief
    code:
    - name: RiskScorer
      description: Illustrative implementation
      kind: class
      members:
      - '+score(payment): RiskScore'
      evidence: fictional brief
  - name: Rules Engine
    description: Applies merchant and platform block rules
    technology: Python
    evidence: fictional brief
    code:
    - name: RuleSet
      description: Illustrative implementation
      kind: class
      members:
      - '+evaluate(payment, score): Decision'
      evidence: fictional brief
- name: Ledger Service
  description: Double-entry ledger of balances, fees and payouts
  technology: Kotlin
  evidence: fictional brief
  gcp_service: Cloud Run
  components:
  - name: Journal Writer
    description: Posts balanced journal entries for money movements
    technology: Kotlin
    evidence: fictional brief
    code:
    - name: JournalWriter
      description: Illustrative implementation
      kind: class
      members:
      - '+post(entries): JournalId'
      evidence: fictional brief
  - name: Balance Calculator
    description: Computes available and pending merchant balances
    technology: Kotlin
    evidence: fictional brief
    code:
    - name: BalanceCalculator
      description: Illustrative implementation
      kind: class
      members:
      - '+balance(merchantId, currency): Balance'
      evidence: fictional brief
- name: Webhook Dispatcher
  description: Signs and delivers payment events to merchants, with retries
  technology: Node.js
  evidence: fictional brief
  gcp_service: Cloud Functions
- name: Settlement Worker
  description: Reconciles acquirer settlement files and initiates payouts
  technology: Python batch jobs
  evidence: fictional brief
  gcp_service: Batch
- name: Payments Database
  description: Payment intents, merchants and API keys
  technology: PostgreSQL
  evidence: fictional brief
  gcp_service: Cloud SQL
- name: Ledger Store
  description: Strongly consistent journal and balance records
  technology: Distributed SQL
  evidence: fictional brief
  gcp_service: Cloud Spanner
- name: Idempotency Cache
  description: Short-lived idempotency keys and responses
  technology: Redis
  evidence: fictional brief
  gcp_service: Memorystore
- name: Payment Event Stream
  description: Ordered payment lifecycle events
  technology: Event bus
  evidence: fictional brief
  gcp_service: Pub/Sub
- name: Vault Key Store
  description: Key-encryption keys for the card vault
  technology: Managed KMS
  evidence: fictional brief
  gcp_service: Key Management Service
- name: Reporting Warehouse
  description: Reconciliation and finance analytics
  technology: Columnar warehouse
  evidence: fictional brief
  gcp_service: BigQuery
- name: Settlement Archive
  description: Raw acquirer settlement files
  technology: Object storage
  evidence: fictional brief
  gcp_service: Cloud Storage
flows:
- from: Shopper
  to: Checkout Web SDK
  description: Enters card details at checkout
  technology: HTTPS
  evidence: fictional brief
- from: Checkout Web SDK
  to: Card Tokenizer
  description: Submits card data for a token
  technology: HTTPS
  evidence: fictional brief
- from: Checkout Web SDK
  to: Payment Intents Controller
  description: Confirms the payment with the card token
  technology: HTTPS
  evidence: fictional brief
- from: Merchant
  to: Merchant Dashboard
  description: Reviews payments, refunds and payouts
  technology: HTTPS
  evidence: fictional brief
- from: Merchant Dashboard
  to: Payment Intents Controller
  description: Lists payments and issues refunds
  technology: HTTPS
  evidence: fictional brief
- from: Merchant Webhook Endpoint
  to: Merchant Authenticator
  description: Calls the API server-side with a secret key
  technology: HTTPS
  evidence: fictional brief
- from: Merchant Authenticator
  to: Payments Database
  description: Looks up API keys
  technology: SQL
  evidence: fictional brief
- from: Payment Intents Controller
  to: Idempotency Guard
  description: Reserves the idempotency key
  technology: in-process
  evidence: fictional brief
- from: Idempotency Guard
  to: Idempotency Cache
  description: Stores request keys and responses
  technology: Redis
  evidence: fictional brief
- from: Payment Intents Controller
  to: Payments Database
  description: Persists payment intents
  technology: SQL
  evidence: fictional brief
- from: Payment Intents Controller
  to: Payment State Machine
  description: Starts authorization
  technology: gRPC
  evidence: fictional brief
- from: Payment State Machine
  to: Risk Scorer
  description: Requests a fraud score
  technology: gRPC
  evidence: fictional brief
- from: PaymentStateMachine
  to: PaymentState
  description: Delegates each transition to the current state
  technology: in-process
  evidence: fictional brief
- from: Risk Scorer
  to: Rules Engine
  description: Applies block and review rules
  technology: in-process
  evidence: fictional brief
- from: Risk Analyst
  to: Rules Engine
  description: Reviews flagged payments and tunes rules
  technology: HTTPS
  evidence: fictional brief
- from: Payment State Machine
  to: 3DS Handler
  description: Requests cardholder authentication
  technology: in-process
  evidence: fictional brief
- from: 3DS Handler
  to: 3-D Secure Directory Server
  description: Authenticates the cardholder
  technology: EMV 3DS over HTTPS
  evidence: fictional brief
- from: Payment State Machine
  to: Acquirer Router
  description: Sends authorization and capture
  technology: in-process
  evidence: fictional brief
- from: Acquirer Router
  to: Card Tokenizer
  description: Detokenizes the card for the network request
  technology: mTLS
  evidence: fictional brief
- from: Acquirer Router
  to: Acquirer Processor
  description: Authorizes, captures and refunds
  technology: ISO 8583 over TLS
  evidence: fictional brief
- from: Card Tokenizer
  to: Envelope Encryptor
  description: Encrypts card records
  technology: in-process
  evidence: fictional brief
- from: Envelope Encryptor
  to: Vault Key Store
  description: Wraps and unwraps data keys
  technology: KMS API
  evidence: fictional brief
- from: Payment State Machine
  to: Payment Event Stream
  description: Publishes payment lifecycle events
  technology: events
  evidence: fictional brief
- from: Payment Event Stream
  to: Journal Writer
  description: Delivers captured, refunded and fee events
  technology: events
  evidence: fictional brief
- from: Journal Writer
  to: Ledger Store
  description: Posts double-entry journal entries
  technology: SQL
  evidence: fictional brief
- from: Journal Writer
  to: Reporting Warehouse
  description: Streams journal entries
  technology: batch export
  evidence: fictional brief
- from: Payment Event Stream
  to: Webhook Dispatcher
  description: Delivers merchant-facing events
  technology: events
  evidence: fictional brief
- from: Webhook Dispatcher
  to: Merchant Webhook Endpoint
  description: Delivers signed webhooks
  technology: HTTPS
  evidence: fictional brief
- from: Settlement Worker
  to: Acquirer Processor
  description: Downloads settlement files
  technology: SFTP
  evidence: fictional brief
- from: Settlement Worker
  to: Settlement Archive
  description: Archives settlement files
  technology: object API
  evidence: fictional brief
- from: Settlement Worker
  to: Balance Calculator
  description: Reconciles merchant balances
  technology: gRPC
  evidence: fictional brief
- from: Settlement Worker
  to: Bank Payout Rail
  description: Initiates merchant payouts
  technology: ISO 20022
  evidence: fictional brief
- from: Finance Operations
  to: Reporting Warehouse
  description: Runs reconciliation and payout reports
  technology: SQL
  evidence: fictional brief
assumptions:
- All architecture and deployment facts in this example are fictional.
gaps: []
deployment:
  provider: gcp
  nodes:
  - id: example-org
    name: Example Organization
    type: organization
    children:
    - id: paystream-prod
      name: paystream-prod
      type: project
      children:
      - id: primary-region
        name: europe-west1
        type: region
        children:
        - id: payments-vpc
          name: payments-vpc
          type: vpc
          children:
          - id: app-subnet
            name: app-subnet
            type: subnet
            children:
            - id: orchestrator-cluster
              name: orchestrator-cluster
              type: cluster
          - id: cde-subnet
            name: cde-subnet (cardholder data)
            type: subnet
            children:
            - id: vault-cluster
              name: vault-cluster
              type: cluster
          - id: data-subnet
            name: data-subnet
            type: subnet
  - id: shopper-browser
    name: Shopper browser
    type: device
    children:
    - id: browser-runtime
      name: Web browser
      type: execution-environment
  placements:
  - element: Checkout Web SDK
    node_id: browser-runtime
  - element: Payments API
    node_id: app-subnet
  - element: Payment Orchestrator
    node_id: orchestrator-cluster
  - element: Ledger Service
    node_id: app-subnet
  - element: Card Vault
    node_id: vault-cluster
  - element: Payments Database
    node_id: data-subnet
  - element: Ledger Store
    node_id: paystream-prod
  - element: Idempotency Cache
    node_id: data-subnet
  - element: Reporting Warehouse
    node_id: paystream-prod
  - element: Fraud Scoring
    node_id: primary-region
  - element: Webhook Dispatcher
    node_id: primary-region
  - element: Settlement Worker
    node_id: primary-region
  - element: Payment Event Stream
    node_id: primary-region
  - element: Vault Key Store
    node_id: primary-region
  - element: Settlement Archive
    node_id: primary-region
  - element: Merchant Dashboard
    node_id: paystream-prod
gcp_icon_style: auto
```
