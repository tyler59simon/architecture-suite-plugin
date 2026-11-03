---
tags: [trigger]
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

Create a Google Cloud deployment architecture diagram: a Cloud Run service behind a load balancer in europe-west1 publishes events to Pub/Sub, a Dataflow job writes them to BigQuery, and Cloud SQL stores user profiles.
