# Examples

Rendered output from Architecture Suite for fictional systems. Every diagram comes in Mermaid
(`.mmd`), editable Draw.io (`.drawio`), PNG and SVG, and every package has the same layout:

```text
01-system-context/   C4 level 1
02-containers/       C4 level 2
03-components/       C4 level 3 (one diagram per container)
04-code/             C4 level 4 (one diagram per component)
05-overview/         overview styles
06-*-deployment/     AWS or Google Cloud deployment
architecture-report.md, plan-fidelity.md
```

None of this ships in the plugin. All systems and facts are invented.

## Systems

| Example | Cloud | What it shows |
| --- | --- | --- |
| [payments](payments/README.md) | AWS **and** Google Cloud | PayStream online payments, the most complete example: one architecture rendered on both clouds with every level, overview and deployment, plus a card-payment sequence |
| [ride-dispatch](ride-dispatch/README.md) | Google Cloud | RidePulse ride dispatch: full set, modern vs legacy GCP icons, and reverse-engineering diagrams from a small source repository |
| [starter-systems](starter-systems/index.md) | AWS | Three small systems (order platform, research portal, telemetry platform), the output of `architecture-suite examples` |
| [cli-features](cli-features/README.md) | - | Request scenarios, architecture diffs, rule checks, infrastructure import and the offline HTML explorer |

## Find an example for a skill

| Skill | Look at |
| --- | --- |
| `c4-diagrams` | [payments/aws](payments/aws), [ride-dispatch/diagrams](ride-dispatch/diagrams) |
| `c4-system` | [payments/aws/01-system-context](payments/aws/01-system-context) |
| `c4-container` | [payments/aws/02-containers](payments/aws/02-containers) |
| `c4-component` | [payments/aws/03-components](payments/aws/03-components) |
| `c4-code` | [payments/aws/04-code](payments/aws/04-code) |
| `c4-overview` | [payments/aws/05-overview](payments/aws/05-overview), [payments/aws/large-overviews](payments/aws/large-overviews), [cli-features/explorer](cli-features/explorer/explorer.html) |
| `c4-aws` | [payments/aws/06-aws-deployment](payments/aws/06-aws-deployment), [starter-systems](starter-systems/index.md), [cli-features/infrastructure](cli-features/infrastructure) |
| `c4-gcp` | [payments/gcp/06-gcp-deployment](payments/gcp/06-gcp-deployment), [ride-dispatch/diagrams/06-gcp-deployment](ride-dispatch/diagrams/06-gcp-deployment), [ride-dispatch/icon-styles](ride-dispatch/icon-styles) |
| `reverse-engineer-c4` | [ride-dispatch/from-source-code](ride-dispatch/from-source-code) |

## Regenerate

```text
python tools/generate_payments_samples.py   # payments/
python tools/generate_gcp_samples.py        # ride-dispatch/
python tools/generate_samples.py            # starter-systems/
python tools/generate_extensions.py         # cli-features/
```
