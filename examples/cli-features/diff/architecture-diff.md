# Architecture report

```json
{
  "schema_version": "architecture-diff/v1",
  "changes": [
    {
      "section": "elements",
      "id": "api",
      "kind": "changed",
      "before": {
        "name": "API",
        "description": "Accepts customer requests",
        "technology": "Python HTTPS",
        "id": "api",
        "type": "container",
        "parent_id": "order-platform",
        "cloud": {
          "provider": "aws",
          "service": "Amazon-Elastic-Container-Service"
        }
      },
      "after": {
        "name": "API",
        "description": "Accepts customer requests",
        "technology": "Go HTTPS",
        "id": "api",
        "type": "container",
        "parent_id": "order-platform",
        "cloud": {
          "provider": "aws",
          "service": "Amazon-Elastic-Container-Service"
        }
      }
    },
    {
      "section": "relationships",
      "id": "('fulfillmentjob', 'order-store')",
      "kind": "removed",
      "before": {
        "source_id": "fulfillmentjob",
        "destination_id": "order-store",
        "description": "Stores result",
        "technology": "DynamoDB"
      },
      "after": null
    }
  ],
  "changed": true
}
```
