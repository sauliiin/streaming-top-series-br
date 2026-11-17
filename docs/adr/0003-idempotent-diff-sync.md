# ADR 0003: Idempotent, diff-based list reconciliation

- **Status:** Accepted
- **Date:** 2026-11-17

## Context

The simplest approach (clear the list, then add 20 items) is not atomic. A failure between the two
steps leaves a public list empty, and every run produces writes and change notifications even when
nothing changed. Retries (from the scheduler or Lambda) could also run the job more than once.

## Decision

Treat the MDBList list as state to be **reconciled**:

1. read the current items;
2. compute `to_add = desired - current` and `to_remove = current - desired`;
3. apply removals, then additions, in batches;
4. skip all writes when the diff is empty.

As a safety net, when the selection has fewer than `SAFETY_MIN_SELECTED` shows (a sign of upstream
degradation), removals are suppressed and the provider is reported as `degraded`.

Lists are found by slug or name and created on demand, so the very first run bootstraps them.

## Consequences

- Re-running the job any number of times converges to the same state (verified by tests).
- A transient TMDB problem can never empty a list.
- The ranking order is kept in the S3 snapshot. MDBList displays the items using the list's
  configured sort.
