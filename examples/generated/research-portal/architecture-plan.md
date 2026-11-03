# Architecture plan

Drafted by bounded static analysis. Review candidate boundaries and gaps before publishing.

```yaml
schema_version: architecture-plan/v1
system:
  name: Research Portal
  description: Portal and query service
  classification: Synthetic, non-production example
  scope: Illustrative owned applications
people:
- name: Customer
  description: Submits requests
  evidence: fictional brief
external_systems:
- name: Payment Provider
  description: Authorizes payments
  evidence: fictional brief
containers:
- name: API
  description: Accepts customer requests
  technology: Python HTTPS
  aws_service: Amazon ECS
  evidence: fictional brief
  components:
  - name: Request Controller
    description: Validates and routes requests
    evidence: fictional brief
    code:
    - name: RequestHandler
      description: Illustrative implementation
      kind: class
      members:
      - '+handle(request): Response'
      evidence: fictional brief
    - name: RequestValidator
      description: Illustrative implementation
      kind: class
      members:
      - '+validate(request): bool'
      evidence: fictional brief
  - name: Payment Adapter
    description: Calls payment provider
    evidence: fictional brief
    code:
    - name: PaymentClient
      description: Illustrative implementation
      kind: class
      members:
      - '+authorize(order): Result'
      evidence: fictional brief
- name: Worker
  description: Processes queued requests
  technology: Go
  aws_service: AWS Lambda
  evidence: fictional brief
  components:
  - name: Fulfillment
    description: Dispatches fulfillment work
    evidence: fictional brief
    code:
    - name: FulfillmentJob
      description: Illustrative implementation
      kind: class
      members:
      - '+run(order): Result'
      evidence: fictional brief
- name: Order Queue
  description: Buffers accepted work
  technology: SQS
  aws_service: Amazon SQS
  evidence: fictional brief
- name: Order Store
  description: Persists request state
  technology: DynamoDB
  aws_service: Amazon DynamoDB
  evidence: fictional brief
flows:
- from: Customer
  to: RequestHandler
  description: Submits request
  technology: HTTPS
  evidence: fictional brief
- from: RequestHandler
  to: RequestValidator
  description: Validates input
  technology: method
  evidence: fictional brief
- from: RequestHandler
  to: PaymentClient
  description: Requests authorization
  technology: method
  evidence: fictional brief
- from: PaymentClient
  to: Payment Provider
  description: Authorizes payment
  technology: HTTPS
  evidence: fictional brief
- from: RequestHandler
  to: Order Queue
  description: Queues accepted work
  technology: SQS
  evidence: fictional brief
- from: Order Queue
  to: FulfillmentJob
  description: Delivers work
  technology: event
  evidence: fictional brief
- from: FulfillmentJob
  to: Order Store
  description: Stores result
  technology: DynamoDB
  evidence: fictional brief
assumptions:
- All architecture and deployment facts in this example are fictional.
gaps: []
deployment:
  nodes:
  - name: Example Account
    type: account
    children:
    - name: us-east-1
      type: region
      children:
      - name: Application VPC
        type: vpc
        children:
        - name: Private Subnet
          type: subnet
  placements:
  - element: API
    node: Private Subnet
  - element: Worker
    node: us-east-1
  - element: Order Queue
    node: us-east-1
  - element: Order Store
    node: us-east-1
```
