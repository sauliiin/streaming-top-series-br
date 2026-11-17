# ADR 0001: Hexagonal architecture

- **Status:** Accepted
- **Date:** 2026-11-17

## Context

The job integrates two third-party APIs (TMDB, MDBList) and three AWS services. The selection rules
are the part most likely to change, and also the part that most needs exhaustive tests. A single
script that mixes HTTP calls with business rules is quick to write but hard to test and to evolve.

## Decision

Organise the code in concentric layers (Ports & Adapters / Clean Architecture):

- `domain`: immutable entities and pure functions (`select_top`, `compute_diff`).
- `application`: the `TopSeriesSyncService` use case and the `Protocol` ports it needs.
- `infrastructure`: adapters that implement the ports.
- `entrypoints`: Lambda and CLI. `bootstrap.py` is the only composition root.

Dependencies point inwards only. Ports are structural (`typing.Protocol`), so adapters do not
inherit from framework classes.

## Consequences

- Domain and use-case tests run in milliseconds with no network and no mocks of third-party SDKs.
- Replacing MDBList with another list provider (e.g. Trakt) means adding one adapter.
- There are slightly more files than a single script would need. That is acceptable for a
  long-running, unattended job.
