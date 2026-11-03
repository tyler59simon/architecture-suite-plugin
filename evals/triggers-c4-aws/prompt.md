---
tags: [trigger]
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

Draw the AWS deployment diagram for this Terraform: an aws_vpc with two private subnets, an aws_ecs_service running the API on Fargate, an aws_db_instance (PostgreSQL) and an aws_sqs_queue, all in eu-west-1.
