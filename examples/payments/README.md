# PayStream: online payments example (fictional)

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
| Progressive, small-multiples, complete (SVG/Draw.io) | [aws/large-overviews](aws/large-overviews) | [gcp/large-overviews](gcp/large-overviews) |

Regenerate with `python tools/generate_payments_samples.py`. Every fact here is fictional.
