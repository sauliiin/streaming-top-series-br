# ADR 0005: IMDb as the primary score, TMDB as fallback

- **Status:** Accepted
- **Date:** 2026-11-17

## Context

TMDB scores for new releases are often inflated by a handful of votes. For example, a series scored
10.0 on TMDB from a single vote scored 8.9 on IMDb from 24 votes, and a documentary scored 10.0 on
TMDB but 7.8 on IMDb with 951 votes. IMDb ratings are the reference most viewers recognise and
usually have one or two orders of magnitude more votes.

Options for obtaining IMDb ratings:

| Option | Key | Limits | Notes |
| --- | --- | --- | --- |
| OMDb API | required | 1,000 req/day (free tier) | Third-party service; one request per title |
| MDBList API | required | per-plan | Already a dependency, but couples scoring to the list provider |
| **IMDb non-commercial datasets** | none | none | Official `title.ratings.tsv.gz` (~9 MB), refreshed daily |

## Decision

- Use the official `title.ratings.tsv.gz` behind a `RatingsProvider` port
  (`ImdbDatasetRatings` adapter).
- TMDB provides the IMDb id: `external_ids` for series, `imdb_id` for movies, both fetched in the
  same request as the details through `append_to_response`.
- The domain computes an **effective rating**: the IMDb rating when it exists, otherwise the TMDB
  score. Titles without any score are rejected (`no_rating`).
- The dataset is downloaded atomically to a cache directory (`/tmp` in Lambda) and reused for 20 hours.
  Lookups stream the gzip once per batch of unseen ids and keep only the matches in memory.
- If the download fails, the provider run fails. The job does not silently fall back to TMDB-only
  scores, because that would churn the lists. Operators can opt out with `IMDB_RATINGS=false`.

## Consequences

- No new secrets, no rate limits and no per-title HTTP calls for ratings.
- About 1–2 s per lookup batch and about 9 MB of transfer per cold container per day.
- The datasets are licensed for personal and non-commercial use, which matches this project.
  Attribution is given in the README.
