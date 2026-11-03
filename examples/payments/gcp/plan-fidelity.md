# Plan fidelity

```json
{
  "declared": {
    "elements": 50,
    "flows": 33,
    "views": 19
  },
  "compiled": {
    "elements": 50,
    "flows": 63,
    "views": 19
  },
  "merged": [
    "system-context-r6: flow-20, flow-29",
    "containers-r7: flow-7, flow-10"
  ],
  "dropped": [],
  "views": [
    "system-context",
    "containers",
    "component-payments-api",
    "component-card-vault",
    "component-payment-orchestrator",
    "component-fraud-scoring",
    "component-ledger-service",
    "code-merchant-authenticator",
    "code-idempotency-guard",
    "code-payment-intents-controller",
    "code-card-tokenizer",
    "code-envelope-encryptor",
    "code-payment-state-machine",
    "code-acquirer-router",
    "code-3ds-handler",
    "code-risk-scorer",
    "code-rules-engine",
    "code-journal-writer",
    "code-balance-calculator"
  ],
  "lossless": true,
  "augmented": false,
  "layout": {
    "ok": true,
    "diagrams": {
      "01-system-context/system-context": {
        "findings": [],
        "crossings": 0,
        "bends": 14,
        "aspect_ratio": 1.698,
        "score": 43.69779389543669,
        "advisories": []
      },
      "02-containers/containers": {
        "findings": [],
        "crossings": 6,
        "bends": 52,
        "aspect_ratio": 1.235,
        "score": 757.235172143975,
        "advisories": []
      },
      "03-components/component-card-vault": {
        "findings": [],
        "crossings": 0,
        "bends": 2,
        "aspect_ratio": 1.65,
        "score": 7.65016146393972,
        "advisories": []
      },
      "03-components/component-fraud-scoring": {
        "findings": [],
        "crossings": 1,
        "bends": 4,
        "aspect_ratio": 1.209,
        "score": 113.20911722141824,
        "advisories": []
      },
      "03-components/component-ledger-service": {
        "findings": [],
        "crossings": 1,
        "bends": 4,
        "aspect_ratio": 1.399,
        "score": 113.39933365064255,
        "advisories": []
      },
      "03-components/component-payment-orchestrator": {
        "findings": [],
        "crossings": 0,
        "bends": 14,
        "aspect_ratio": 1.075,
        "score": 43.07467948717949,
        "advisories": []
      },
      "03-components/component-payments-api": {
        "findings": [],
        "crossings": 0,
        "bends": 14,
        "aspect_ratio": 2.348,
        "score": 44.34788879096226,
        "advisories": []
      },
      "04-code/code-3ds-handler": {
        "findings": [],
        "crossings": 0,
        "bends": 0,
        "aspect_ratio": 1.025,
        "score": 1.0248447204968945,
        "advisories": []
      },
      "04-code/code-acquirer-router": {
        "findings": [],
        "crossings": 0,
        "bends": 0,
        "aspect_ratio": 1.025,
        "score": 1.0248447204968945,
        "advisories": []
      },
      "04-code/code-balance-calculator": {
        "findings": [],
        "crossings": 0,
        "bends": 0,
        "aspect_ratio": 1.025,
        "score": 1.0248447204968945,
        "advisories": []
      },
      "04-code/code-card-tokenizer": {
        "findings": [],
        "crossings": 0,
        "bends": 0,
        "aspect_ratio": 1.025,
        "score": 1.0248447204968945,
        "advisories": []
      },
      "04-code/code-envelope-encryptor": {
        "findings": [],
        "crossings": 0,
        "bends": 0,
        "aspect_ratio": 1.025,
        "score": 1.0248447204968945,
        "advisories": []
      },
      "04-code/code-idempotency-guard": {
        "findings": [],
        "crossings": 0,
        "bends": 0,
        "aspect_ratio": 1.025,
        "score": 1.0248447204968945,
        "advisories": []
      },
      "04-code/code-journal-writer": {
        "findings": [],
        "crossings": 0,
        "bends": 0,
        "aspect_ratio": 1.025,
        "score": 1.0248447204968945,
        "advisories": []
      },
      "04-code/code-merchant-authenticator": {
        "findings": [],
        "crossings": 0,
        "bends": 0,
        "aspect_ratio": 1.025,
        "score": 1.0248447204968945,
        "advisories": []
      },
      "04-code/code-payment-intents-controller": {
        "findings": [],
        "crossings": 0,
        "bends": 0,
        "aspect_ratio": 1.025,
        "score": 1.0248447204968945,
        "advisories": []
      },
      "04-code/code-payment-state-machine": {
        "findings": [],
        "crossings": 0,
        "bends": 0,
        "aspect_ratio": 1.097,
        "score": 1.096969696969697,
        "advisories": []
      },
      "04-code/code-risk-scorer": {
        "findings": [],
        "crossings": 0,
        "bends": 0,
        "aspect_ratio": 1.025,
        "score": 1.0248447204968945,
        "advisories": []
      },
      "04-code/code-rules-engine": {
        "findings": [],
        "crossings": 0,
        "bends": 0,
        "aspect_ratio": 1.025,
        "score": 1.0248447204968945,
        "advisories": []
      },
      "05-overview/overview-executive": {
        "findings": [],
        "crossings": 3,
        "bends": 50,
        "aspect_ratio": 1.079,
        "score": 451.0794665184774,
        "advisories": []
      },
      "05-overview/overview-hierarchy": {
        "findings": [],
        "crossings": 0,
        "bends": 0,
        "aspect_ratio": 10.476,
        "score": 10.475757575757576,
        "advisories": [
          "Dense view; split by scope or use small-multiples",
          "Long page; consider a different direction"
        ]
      },
      "06-gcp-deployment/gcp-deployment": {
        "findings": [],
        "crossings": 4,
        "bends": 34,
        "aspect_ratio": 1.564,
        "score": 503.5640735792827,
        "advisories": []
      }
    }
  },
  "advisories": []
}
```
