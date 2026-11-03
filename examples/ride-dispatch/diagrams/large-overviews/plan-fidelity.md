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
      "05-overview/overview-small-multiples": {
        "findings": [],
        "crossings": 3,
        "bends": 52,
        "aspect_ratio": 1.222,
        "score": 457.2215071871053,
        "advisories": [
          "Dense view; split by scope or use small-multiples"
        ]
      },
      "05-overview/overview-complete": {
        "findings": [],
        "crossings": 9,
        "bends": 36,
        "aspect_ratio": 1.379,
        "score": 1009.3786188579018,
        "advisories": []
      }
    }
  },
  "advisories": []
}
```
