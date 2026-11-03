# Plan fidelity

```json
{
  "declared": {
    "elements": 21,
    "flows": 15,
    "views": 6
  },
  "compiled": {
    "elements": 21,
    "flows": 28,
    "views": 6
  },
  "merged": [
    "system-context-r2: flow-2, flow-4",
    "containers-r5: flow-9, flow-10"
  ],
  "dropped": [],
  "views": [
    "system-context",
    "containers",
    "component-hook-adapters",
    "component-memory-cli",
    "code-command-dispatcher",
    "code-search-and-read"
  ],
  "lossless": true,
  "augmented": true,
  "layout": {
    "ok": true,
    "diagrams": {
      "01-system-context/system-context": {
        "findings": [],
        "crossings": 0,
        "bends": 4,
        "aspect_ratio": 1.267,
        "score": 13.267232237539767,
        "advisories": []
      },
      "02-containers/containers": {
        "findings": [],
        "crossings": 0,
        "bends": 16,
        "aspect_ratio": 1.904,
        "score": 49.90427564398182,
        "advisories": []
      },
      "03-components/component-hook-adapters": {
        "findings": [],
        "crossings": 1,
        "bends": 2,
        "aspect_ratio": 1.332,
        "score": 107.3320628870891,
        "advisories": []
      },
      "03-components/component-memory-cli": {
        "findings": [],
        "crossings": 0,
        "bends": 16,
        "aspect_ratio": 1.929,
        "score": 49.92926045016077,
        "advisories": []
      },
      "04-code/code-command-dispatcher": {
        "findings": [],
        "crossings": 0,
        "bends": 0,
        "aspect_ratio": 1.025,
        "score": 1.0248447204968945,
        "advisories": []
      },
      "04-code/code-search-and-read": {
        "findings": [],
        "crossings": 0,
        "bends": 0,
        "aspect_ratio": 1.025,
        "score": 1.0248447204968945,
        "advisories": []
      },
      "05-overview/overview-progressive": {
        "findings": [],
        "crossings": 0,
        "bends": 20,
        "aspect_ratio": 3.089,
        "score": 63.08862745098039,
        "advisories": []
      }
    }
  },
  "advisories": []
}
```
