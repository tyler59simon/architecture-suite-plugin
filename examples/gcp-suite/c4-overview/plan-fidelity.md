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
      "05-overview/overview-executive": {
        "findings": [],
        "crossings": 3,
        "bends": 28,
        "aspect_ratio": 1.082,
        "score": 385.08195780590717,
        "advisories": []
      },
      "05-overview/overview-progressive": {
        "findings": [],
        "crossings": 9,
        "bends": 36,
        "aspect_ratio": 1.446,
        "score": 1009.4460896767466,
        "advisories": []
      },
      "05-overview/overview-hierarchy": {
        "findings": [],
        "crossings": 0,
        "bends": 0,
        "aspect_ratio": 5.934,
        "score": 5.9340796019900495,
        "advisories": [
          "Long page; consider a different direction"
        ]
      }
    }
  },
  "advisories": []
}
```
