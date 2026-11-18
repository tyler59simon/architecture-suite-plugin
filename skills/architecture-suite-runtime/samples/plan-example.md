# Architecture plan: Bike Share Booking (fictional)

A complete small plan. Every fact is made up and the evidence cites an imaginary design brief. Copy it as a starting point, then replace names and evidence with your own. Check it with `architecture-suite plan-lint --plan plan-example.md --strict` and render it with `architecture-suite plan-render --plan plan-example.md --output <out> --level all --dry-run`.

```yaml
schema_version: architecture-plan/v1
system:
  name: Bike Share Booking
  description: Lets riders reserve a bike, unlock it and pay for the ride
  classification: Synthetic, non-production example
  scope: The booking API, its worker and their data stores; the payment provider is outside the boundary
people:
- name: Rider
  description: Reserves and unlocks bikes from the mobile app
  evidence: design brief section 1
- name: Station Operator
  description: Checks bike availability and reports faults
  evidence: design brief section 1
external_systems:
- name: Payment Provider
  description: Authorizes and captures ride payments
  evidence: design brief section 4
containers:
- name: Booking API
  description: Accepts reservation and unlock requests from the mobile app
  technology: Python, FastAPI
  aws_service: Amazon ECS
  evidence: design brief section 2
  components:
  - name: Reservation Controller
    description: Validates reservation requests and queues accepted ones
    evidence: design brief section 2
    code:
    - name: ReservationHandler
      description: Handles reservation requests
      kind: class
      members:
      - '+reserve(request): Reservation'
      evidence: design brief section 2
    - name: ReservationValidator
      description: Checks that a bike is free and the rider is allowed to book
      kind: class
      members:
      - '+validate(request): bool'
      evidence: design brief section 2
  - name: Payment Adapter
    description: Calls the payment provider for deposits and ride charges
    evidence: design brief section 4
    code:
    - name: PaymentClient
      description: Wraps the payment provider HTTP API
      kind: class
      members:
      - '+authorize(rider, amount): Result'
      evidence: design brief section 4
- name: Ride Worker
  description: Processes queued reservations and closes finished rides
  technology: Go
  aws_service: AWS Lambda
  evidence: design brief section 3
  components:
  - name: Ride Closer
    description: Ends a ride and records its cost
    evidence: design brief section 3
    code:
    - name: CloseRideJob
      description: Closes one ride and stores the result
      kind: class
      members:
      - '+run(ride): Result'
      evidence: design brief section 3
- name: Reservation Queue
  description: Buffers accepted reservations for the worker
  technology: SQS
  aws_service: Amazon SQS
  evidence: design brief section 3
- name: Ride Store
  description: Persists reservations, rides and their cost
  technology: DynamoDB
  aws_service: Amazon DynamoDB
  evidence: design brief section 3
flows:
- from: Rider
  to: ReservationHandler
  description: Requests a bike
  technology: HTTPS
  evidence: design brief section 2
- from: Station Operator
  to: Reservation Controller
  description: Views bike availability
  technology: HTTPS
  evidence: design brief section 2
- from: ReservationHandler
  to: ReservationValidator
  description: Validates the request
  technology: method call
  evidence: design brief section 2
- from: ReservationHandler
  to: PaymentClient
  description: Requests a deposit authorization
  technology: method call
  evidence: design brief section 4
- from: PaymentClient
  to: Payment Provider
  description: Authorizes the deposit
  technology: HTTPS
  evidence: design brief section 4
- from: ReservationHandler
  to: Reservation Queue
  description: Queues the accepted reservation
  technology: SQS
  evidence: design brief section 3
- from: Reservation Queue
  to: CloseRideJob
  description: Delivers reservation events
  technology: event
  evidence: design brief section 3
- from: CloseRideJob
  to: Ride Store
  description: Stores the finished ride
  technology: DynamoDB
  evidence: design brief section 3
assumptions:
- All facts in this example are fictional.
gaps: []
deployment:
  nodes:
  - name: Example Account
    type: account
    children:
    - name: us-east-1
      type: region
      children:
      - name: Booking VPC
        type: vpc
        children:
        - name: Private Subnet
          type: subnet
  placements:
  - element: Booking API
    node: Private Subnet
  - element: Ride Worker
    node: us-east-1
  - element: Reservation Queue
    node: us-east-1
  - element: Ride Store
    node: us-east-1
```
