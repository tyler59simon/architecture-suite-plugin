# Architecture planning guide

How to build a `plan.md` that produces accurate diagrams. The `architecture-plan` skill follows this guide, and `architecture-suite plan-review` checks the result. Plan format: `runtime.md` (Plans) and `assets/architecture-plan-template.md`.

## Choose target levels first

| Audience | Levels | Plan needs |
| --- | --- | --- |
| Executives, sponsors | L1, executive overview | system, people, external systems, flows between them |
| Architects, reviewers | L1-L2 | plus every container (application, service, data store) with technology |
| Delivery teams | L1-L3 | plus components inside each container that has any |
| Detailed design | L4 for a few components | plus code elements with members |
| Operations, platform | deployment | containers, cloud services, deployment nodes and placements |

Levels are a prefix: L3 needs L1 and L2 to be sound. Stop at the deepest level the audience will use; detail nobody reads is detail nobody checks.

## Question bank

Ask a few questions at a time, starting at L1. Record anything unanswered under `gaps`.

**Scope (always)**
- What decision or conversation are these diagrams for, and who will read them?
- Which system is being described, and what is inside its ownership boundary (owned and changed by the same team or organization)?
- Is this the current state, a target state, or a transition? (A target state is mostly `status: proposed`.)

**L1 System context**
- Who uses the system? Include operators, administrators, support staff and partner staff, not only end users.
- Which systems outside the boundary does it call, receive data from, or get called by (identity provider, payment, email, analytics, upstream or downstream systems)?
- For each interaction, what is exchanged and why (one verb phrase, e.g. "Submits orders")?

**L2 Containers**
- What separately deployable or runnable units are there: web or mobile apps, APIs, workers, scheduled jobs, functions?
- Where is data kept: databases, caches, queues, topics, object storage, search indexes? Each one is a container.
- What is each built with (language, framework, product) and how do they talk (HTTPS/JSON, gRPC, SQL, AMQP, events)?
- Which containers does each person or external system interact with directly?

**L3 Components (per container that needs it)**
- What are the main responsibilities inside this container (controllers, services, domain modules, adapters, repositories)?
- Which component handles each flow arriving at or leaving the container?

**L4 Code (sparingly)**
- For the few components that need it: which classes, interfaces, modules or functions matter, and which members (methods or fields) explain them?

**Deployment**
- Which cloud (AWS or Google Cloud) and which accounts or projects, regions, networks (VPC), subnets or clusters?
- Where does each container run, and which managed service is it (`aws_service` / `gcp_service`)?
- Are there devices or on-premises locations outside the cloud?

## Evidence

Every element and flow should cite where it comes from in `evidence`, a reference string or a list of them:

- Documents: `"Order platform brief §2.1"`, `"ADR-007 Use a queue for fulfilment"`.
- Files: `"services/api/main.py:42"`, `"infra/main.tf:118"`.
- People and meetings: `"Interview with the platform lead, 2026-11-09"`.
- This conversation: `"User, this conversation"`.

Evidence describes the source, not a conclusion. If there is no source, record the element as an assumption or a gap, or mark it `status: proposed`.

## Claim status

| Status | Use when | Drawn as |
| --- | --- | --- |
| *(unset)* | the plan's sources state it | solid |
| `observed` | you verified it yourself in code, configuration or a running system; cite where | solid |
| `inferred` | it follows from evidence but was not confirmed (drafted or imported candidates) | dotted, «inferred» |
| `proposed` | it is planned or a target-state design, not yet true | dotted, «proposed» |
| `unknown` | it probably exists but the facts are unclear | dotted, «unknown» |

Never mark something `observed` without evidence; `plan-review` reports it as `observed-without-evidence`.

## Naming and structure

- Names must be unique across the plan once slugified (`Order API` and `order-api` collide). Use the name people use for the thing.
- Describe each element by its responsibility in one sentence ("Accepts and validates customer orders"), not by restating its name.
- Nest once: components inside their container, code inside its component. Give each flow at the most specific level known; coarser arrows are derived.
- Use `group` to frame related elements, with at least two per group.
- Keep views readable: about 35 boxes at most per view. Split by scope or use groups and the small-multiples overview.

## Common mistakes

- **Folders or libraries as containers.** A container is something that runs or stores data on its own. A shared library is a component (or nothing at all).
- **Missing data stores.** Databases, queues and buckets are containers and usually carry the most important flows.
- **Unlabelled or vague flows.** "Uses" says nothing; say what is sent and how ("Publishes OrderPlaced events", technology `AMQP`).
- **Invented actors or externals.** Only add people and systems that a source mentions.
- **Isolated elements.** An element with no flows floats in the diagram; either its interactions are missing or it does not belong.
- **SDK usage as placement.** Calling a cloud SDK does not show where something runs; placements need deployment evidence.
- **Template text left in.** `Replace with ...` and `Unspecified` are placeholders, not facts.

## Ready to render

- [ ] Purpose, audience and target levels are stated (in the plan's prose or `assumptions`).
- [ ] `plan-review` shows every target level as `ready`.
- [ ] Every element and flow cites evidence, or is marked `proposed`/`inferred`/`unknown`, or is listed in `assumptions`.
- [ ] Every container has a technology; every flow has a description (and technology at L2 and below).
- [ ] No isolated elements, placeholder text or `observed` claims without evidence.
- [ ] Open questions are in `gaps`, and the user knows about them.
- [ ] `plan-lint --strict` is clean, or each remaining advisory is explained to the user.
