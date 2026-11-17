"""Job orchestration shared by the Lambda handler and the CLI."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from ..application import ListSyncReport
from ..bootstrap import Services
from ..domain import Provider
from ..observability import Logger


@dataclass
class JobsOutcome:
    reports: list[ListSyncReport] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


def run_jobs(
    services: Services, jobs: Iterable[str], providers: tuple[Provider, ...], *, dry_run: bool, log: Logger
) -> JobsOutcome:
    outcome = JobsOutcome()
    by_job = {"series": services.series, "movies": services.movies}
    for job in jobs:
        report = by_job[job].run(providers, dry_run=dry_run)
        outcome.reports.append(report)
        outcome.failures += [f"{job}:{failure}" for failure in report.failed]
        if services.site:
            try:
                services.site.publish(report)
            except Exception as exc:  # noqa: BLE001 - the list sync already succeeded; report and move on
                log("site_publish_failed", level="ERROR", feed=job, error=f"{type(exc).__name__}: {exc}")
                outcome.failures.append(f"site:{job}")
    return outcome
