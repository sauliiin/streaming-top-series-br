"""Command-line entrypoint for local runs.

streaming-top-series [--job series|movies|all] [--dry-run] [--providers netflix,hbo] [--json] [--verbose]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from ..application import ListSyncReport
from ..bootstrap import ConfigurationError, build_services
from ..domain import PROVIDERS
from ..observability import json_logger, null_logger
from ..settings import JOBS, Settings
from .jobs import run_jobs

ATTRIBUTION = "Ratings: IMDb (with TMDB fallback). Streaming availability: JustWatch via TMDB."
TITLES = {"series": "Series", "movies": "Movies"}


def _score(row: dict[str, Any]) -> str:
    if row["score"] is None:
        return "no score"
    return f"{row['score']:.1f} {row['score_source'].upper()}, {row['votes']} votes"


def _row(job: str, row: dict[str, Any]) -> str:
    if job == "series":
        return f"{row['rank']:3}. {row['episode_date']}  {row['episode']}  {row['name']}  ({_score(row)})"
    return f"{row['rank']:3}. {row['release_date']} [{row['release_kind']:8}] {row['title']}  ({_score(row)})"


def render(report: ListSyncReport) -> str:
    lines = [
        f"{TITLES[report.job]} run {report.run_date}{' (dry-run)' if report.dry_run else ''}",
        f"== {report.list_name}  [{report.status}]  list_id={report.list_id}",
    ]
    if report.error:
        lines.append(f"   ERROR: {report.error}")
    for p in report.providers:
        lines.append(f"\n-- {PROVIDERS[p.provider].display_name}  [{p.status}]  window={p.window_days} days")
        if p.error:
            lines.append(f"   ERROR: {p.error}")
        lines.extend(_row(report.job, row) for row in p.selected)
        lines.append(f"   rejected={p.rejected}")
    lines.append(f"\n   +{len(report.added)} to add  -{len(report.removed)} to remove")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="streaming-top-series", description="Sync the daily series and movie lists.")
    parser.add_argument("--job", choices=[*JOBS, "all"], default="all", help="which list(s) to sync")
    parser.add_argument("--dry-run", action="store_true", help="compute the diff without writing to MDBList")
    parser.add_argument("--providers", help=f"comma-separated subset of: {','.join(PROVIDERS)}")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    parser.add_argument("--verbose", action="store_true", help="emit structured logs to stderr")
    args = parser.parse_args(argv)

    env = dict(os.environ)
    if args.providers:
        env["PROVIDERS"] = args.providers
    settings = Settings.from_env(env)
    dry_run = args.dry_run or settings.dry_run
    log = json_logger(sys.stderr) if args.verbose else null_logger

    try:
        services = build_services(settings, env, dry_run=dry_run, log=log)
    except ConfigurationError as exc:
        print(exc, file=sys.stderr)
        return 2

    jobs = JOBS if args.job == "all" else (args.job,)
    outcome = run_jobs(services, jobs, settings.providers, dry_run=dry_run, log=log)

    if args.json:
        print(json.dumps({r.job: r.to_dict() for r in outcome.reports}, ensure_ascii=False, indent=2))
    else:
        print("\n\n".join([*(render(r) for r in outcome.reports), ATTRIBUTION]))
    if outcome.failures:
        print(f"Failures: {', '.join(outcome.failures)}", file=sys.stderr)
    return 1 if outcome.failures else 0
