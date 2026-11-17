# Changelog

All notable changes to this project are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to
[Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-11-17

### Added

- Streammy website on GitHub Pages: movies and series rankings per provider. It reads
  `data/movies.json` and `data/series.json`, which the job publishes daily to a private S3 bucket,
  through CloudFront (OAC, CORS restricted to the Pages origin).
- `StreammySeries`: a single public MDBList list with the Top 20 series of each provider, replacing
  the three per-provider series lists.
- `StreammyMovies`: a single public MDBList list with the latest 20 movie releases per provider
  (IMDb ≥ 5.0, no unrated titles, no comedies). The release window widens until 20 movies qualify.
- IMDb ratings from the official datasets, with TMDB as fallback, for both series and movies.
- `--job series|movies|all` in the CLI and `{"job": ...}` in the Lambda event.
- One EventBridge schedule per job (series 06:00, movies 06:15).
- Series always fill a Top 20: the 14-day window widens step by step (up to 365 days) when needed.

### Changed

- The series score cut now uses the effective rating (IMDb first) and the default minimum is 6.0. Unrated titles are reported as
  `no_rating`.
- Snapshots are stored per job: `snapshots/series/` and `snapshots/movies/`.
- Lambda memory raised to 512 MB and timeout to 10 minutes.

## [0.1.0] - 2026-11-17

### Added

- Daily Top 20 selection per provider (Netflix, HBO Max, Prime Video, BR) using TMDB/JustWatch data.
- Idempotent synchronisation of one public static MDBList list per provider.
- Fail-safe that suppresses removals when upstream data degrades.
- AWS infrastructure in Terraform: Lambda, EventBridge Scheduler, S3 snapshots, SSM secrets,
  CloudWatch alarms, SNS and an SQS DLQ.
- Bootstrap stack with remote state and GitHub OIDC deploy role.
- CI (ruff, mypy, pytest, terraform validate) and CD with a post-deploy smoke test.
