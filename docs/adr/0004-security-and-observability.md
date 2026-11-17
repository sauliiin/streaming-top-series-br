# ADR 0004: Secrets, identity and observability

- **Status:** Accepted
- **Date:** 2026-11-17

## Decision

**Secrets.** API keys are SSM Parameter Store SecureStrings, created out of band. Terraform passes
only the parameter *names* to the function, so values never appear in the state, the plan output
or the Lambda console. The function fetches them at cold start and caches them per container.

**Identity.** GitHub Actions assumes a deploy role through OIDC. The trust policy is restricted to
this repository's `main` branch and `production` environment, and the role's permissions are scoped
to resources with the project prefix. No long-lived access keys exist.

**Leak prevention.** API keys travel in query strings, so the HTTP client never includes URLs in
exceptions and suppresses exception chaining (`raise ... from None`). A unit test asserts this.

**Observability.**

- One JSON object per log line, with stable `event` names (`selection_completed`, `list_synced`,
  `provider_failed`, `removals_skipped`, `run_finished`).
- The handler raises when any provider fails, so Lambda's `Errors` metric is the single failure
  signal.
- Three alarms publish to SNS: errors, missed run (no invocation in 24 h, with missing data treated
  as breaching), and DLQ depth.

## Consequences

Rotating a key is a single `put-parameter --overwrite` and needs no redeploy. Failures surface by
e-mail within an hour, and silent failures (the job never running) are also detected.
