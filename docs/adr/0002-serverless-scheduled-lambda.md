# ADR 0002: Scheduled Lambda instead of a long-running server

- **Status:** Accepted
- **Date:** 2026-11-17

## Context

The workload runs once a day for less than a minute. Options considered:

| Option | Monthly cost | Operational burden |
| --- | --- | --- |
| EC2 / Lightsail with cron | instance running 24/7 | OS patching, cron monitoring, disk, SSH |
| ECS Fargate scheduled task | pay per run | container image, registry, VPC networking |
| **Lambda + EventBridge Scheduler** | free tier | none beyond the function itself |

## Decision

Use AWS Lambda (Python 3.13, arm64) triggered by EventBridge Scheduler with an explicit
`America/Sao_Paulo` time zone. The application uses only the standard library, so the deployment
artefact is a zip of `src/` built by Terraform's `archive_file`.

## Consequences

- Effectively zero cost and no servers to patch.
- The 15-minute Lambda limit is far above the observed runtime (about 1 minute for 3 providers).
- Asynchronous invocation semantics require retry and DLQ configuration (see ADR 0004).
