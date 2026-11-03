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
        "crossings": 2,
        "bends": 54,
        "aspect_ratio": 1.342,
        "score": 363.3415681352797,
        "advisories": [
          "Dense view; split by scope or use small-multiples"
        ]
      },
      "05-overview/overview-complete": {
        "findings": [],
        "crossings": 6,
        "bends": 34,
        "aspect_ratio": 1.891,
        "score": 703.8907035175879,
        "advisories": []
      }
    }
  },
  "advisories": []
}
```
