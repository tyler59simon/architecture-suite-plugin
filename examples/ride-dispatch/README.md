# RidePulse: ride dispatch on Google Cloud (fictional)

A real-time ride dispatch and fleet telemetry platform on Google Cloud.

| What | Where |
| --- | --- |
| Editable plan | [plans/architecture-plan.md](plans/architecture-plan.md) |
| L1 system context | [diagrams/01-system-context](diagrams/01-system-context) |
| L2 containers | [diagrams/02-containers](diagrams/02-containers) |
| L3 components | [diagrams/03-components](diagrams/03-components) |
| L4 code | [diagrams/04-code](diagrams/04-code) |
| Overviews (executive, progressive, hierarchy) | [diagrams/05-overview](diagrams/05-overview) |
| Google Cloud deployment | [diagrams/06-gcp-deployment](diagrams/06-gcp-deployment) |
| Ride request sequence | [diagrams/c4-dynamic.mmd](diagrams/c4-dynamic.mmd) |
| Small-multiples and complete overviews (SVG/Draw.io) | [diagrams/large-overviews](diagrams/large-overviews) |
| Modern vs legacy Google Cloud icons | [icon-styles/modern](icon-styles/modern), [icon-styles/legacy](icon-styles/legacy) |
| Reverse-engineered from source code | [from-source-code](from-source-code) |

`from-source-code/` shows the `reverse-engineer-c4` workflow: a small fictional repository
(`ridepulse-repo/`), the editable draft `plan-draft` produced from it, and the diagrams `analyze`
renders directly. Compare the draft with the curated plan to see what a reviewer adds.

Regenerate with `python tools/generate_gcp_samples.py`. Every fact here is fictional.
