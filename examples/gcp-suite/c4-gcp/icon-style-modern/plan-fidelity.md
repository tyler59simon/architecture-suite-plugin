# Plan fidelity

```json
{
  "declared": {
    "elements": 26,
    "flows": 20,
    "views": 8
  },
  "compiled": {
    "elements": 26,
    "flows": 42,
    "views": 8
  },
  "merged": [
    "system-context-r2: flow-2, flow-3"
  ],
  "dropped": [],
  "views": [
    "system-context",
    "containers",
    "component-rider-gateway",
    "component-dispatch-service",
    "code-auth-middleware",
    "code-trip-controller",
    "code-matching-engine",
    "code-fare-pricer"
  ],
  "lossless": true,
  "augmented": false,
  "layout": {
    "ok": true,
    "diagrams": {
      "01-system-context/system-context": {
        "findings": [],
        "crossings": 0,
        "bends": 8,
        "aspect_ratio": 1.032,
        "score": 25.032287822878228,
        "advisories": []
      },
      "02-containers/containers": {
        "findings": [],
        "crossings": 3,
        "bends": 32,
        "aspect_ratio": 1.183,
        "score": 397.1828804830403,
        "advisories": []
      },
      "03-components/component-dispatch-service": {
        "findings": [],
        "crossings": 0,
        "bends": 6,
        "aspect_ratio": 1.147,
        "score": 19.147119767923748,
        "advisories": []
      },
      "03-components/component-rider-gateway": {
        "findings": [],
        "crossings": 0,
        "bends": 4,
        "aspect_ratio": 1.039,
        "score": 13.039323046291688,
        "advisories": []
      },
      "04-code/code-auth-middleware": {
        "findings": [],
        "crossings": 0,
        "bends": 0,
        "aspect_ratio": 1.582,
        "score": 1.5818181818181818,
        "advisories": []
      },
      "04-code/code-fare-pricer": {
        "findings": [],
        "crossings": 0,
        "bends": 0,
        "aspect_ratio": 1.582,
        "score": 1.5818181818181818,
        "advisories": []
      },
      "04-code/code-matching-engine": {
        "findings": [],
        "crossings": 0,
        "bends": 4,
        "aspect_ratio": 1.665,
        "score": 13.66504854368932,
        "advisories": []
      },
      "04-code/code-trip-controller": {
        "findings": [],
        "crossings": 0,
        "bends": 2,
        "aspect_ratio": 1.19,
        "score": 7.189842805320435,
        "advisories": []
      },
      "05-overview/overview-executive": {
        "findings": [],
        "crossings": 3,
        "bends": 28,
        "aspect_ratio": 1.116,
        "score": 385.11585726718886,
        "advisories": []
      },
      "06-gcp-deployment/gcp-deployment": {
        "findings": [],
        "crossings": 3,
        "bends": 40,
        "aspect_ratio": 1.146,
        "score": 421.1460659223817,
        "advisories": []
      }
    }
  },
  "advisories": [
    {
      "code": "gcp-icon-unavailable",
      "message": "No modern icon for this service; it renders without an icon",
      "where": "Notification Worker",
      "severity": "advisory"
    },
    {
      "code": "gcp-icon-unavailable",
      "message": "No modern icon for this service; it renders without an icon",
      "where": "Event Bus",
      "severity": "advisory"
    },
    {
      "code": "gcp-icon-unavailable",
      "message": "No modern icon for this service; it renders without an icon",
      "where": "Location Cache",
      "severity": "advisory"
    },
    {
      "code": "gcp-icon-unavailable",
      "message": "No modern icon for this service; it renders without an icon",
      "where": "Fleet Time Series",
      "severity": "advisory"
    }
  ]
}
```
