"""AWS Lambda entrypoint, invoked daily by EventBridge Scheduler (one schedule per job).

Optional event payload: {"job": "series" | "movies" | "all", "dry_run": true, "providers": ["netflix"]}
After each job the website feed (data/<job>.json) is refreshed.
If anything fails the invocation raises, which feeds the Errors metric and its alarm.
"""

from __future__ import annotations

import os
from typing import Any

from ..bootstrap import build_services
from ..domain import PROVIDERS
from ..observability import json_logger
from ..settings import JOBS, Settings
from .jobs import run_jobs


class SyncFailedError(RuntimeError):
    pass


def handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    event = event or {}
    log = json_logger(request_id=getattr(context, "aws_request_id", None))

    job = event.get("job", "all")
    jobs = JOBS if job == "all" else (job,)
    if any(j not in JOBS for j in jobs):
        raise ValueError(f"Unknown job {job!r}; valid values: {', '.join(JOBS)}, all")

    settings = Settings.from_env(os.environ)
    dry_run = settings.dry_run or bool(event.get("dry_run"))
    providers = settings.providers
    if event.get("providers"):
        providers = tuple(PROVIDERS[key] for key in event["providers"])

    services = build_services(settings, os.environ, dry_run=dry_run, log=log)
    outcome = run_jobs(services, jobs, providers, dry_run=dry_run, log=log)

    summary: dict[str, Any] = {"dry_run": dry_run}
    for report in outcome.reports:
        summary["run_date"] = report.run_date
        summary[report.job] = {
            "list": report.list_name,
            "status": report.status,
            "list_id": report.list_id,
            "added": len(report.added),
            "removed": len(report.removed),
            "per_provider": {p.provider: len(p.selected) for p in report.providers},
        }
    if outcome.failures:
        raise SyncFailedError(f"Sync failed for: {', '.join(outcome.failures)}")
    return summary
