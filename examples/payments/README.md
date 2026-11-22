# PayStream: online payments example (fictional)

One payments architecture, rendered twice: once on AWS and once on Google Cloud. The editable
plans are in `plans/`. `aws/` is a complete package with C4 levels 1-4, overviews, the cloud
deployment diagram, a card-payment sequence (`c4-dynamic.mmd`) and the fidelity and architecture
reports. `gcp/` holds only the files that differ from `aws/`: the views that use cloud service
icons and the deployment diagram. Where a `gcp/` path is missing, the AWS file at the same path is
byte-identical.

| | AWS | Google Cloud |
| --- | --- | --- |
| Plan | [plans/aws-architecture-plan.md](plans/aws-architecture-plan.md) | [plans/gcp-architecture-plan.md](plans/gcp-architecture-plan.md) |
| L1 system context | [aws/01-system-context](aws/01-system-context) | same as AWS |
| L2 containers | [aws/02-containers](aws/02-containers) | [gcp/02-containers](gcp/02-containers) |
| L3 components | [aws/03-components](aws/03-components) | [gcp/03-components](gcp/03-components) |
| L4 code | [aws/04-code](aws/04-code) | same as AWS |
| Overviews | [aws/05-overview](aws/05-overview) | [gcp/05-overview](gcp/05-overview) |
| Deployment | [aws/06-aws-deployment](aws/06-aws-deployment) | [gcp/06-gcp-deployment](gcp/06-gcp-deployment) |
| Progressive, small-multiples, complete (SVG/Draw.io) | [aws/large-overviews](aws/large-overviews) | [gcp/large-overviews](gcp/large-overviews) |

[left-to-right/](left-to-right) is the AWS plan rendered with `--direction right`, so every
diagram reads left to right. Compare it with `aws/`, where the default `--direction auto` picks
whichever direction lays each diagram out best (mostly top to bottom here). It has levels 1-3, the
executive overview and the deployment; a file identical to its `aws/` twin (a view that `auto`
already drew left to right) is not repeated.

Regenerate with `python tools/generate_payments_samples.py`. Every fact here is fictional.
