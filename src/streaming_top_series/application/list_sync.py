"""Shared use-case skeleton: one consolidated static list fed by every provider's Top N.

Concrete jobs (series, movies) only decide how a provider's titles are selected.
Reconciliation, failure isolation, fail-safe removals and snapshots live here, so both
lists behave the same way.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

from ..domain import Provider
from ..observability import Logger, null_logger
from .ports import ListRepository, SnapshotStore
from .reconciliation import reconcile_list, save_snapshot


@dataclass
class ProviderSelection:
    provider: str
    status: str = "ok"  # ok | error
    window_days: int | None = None
    selected: list[dict[str, Any]] = field(default_factory=list)
    rejected: dict[str, int] = field(default_factory=dict)
    error: str | None = None


@dataclass
class ListSyncReport:
    job: str
    run_date: str
    dry_run: bool
    list_name: str
    status: str = "ok"  # ok | degraded | error
    list_id: int | None = None
    list_created: bool = False
    list_url: str | None = None
    providers: list[ProviderSelection] = field(default_factory=list)
    added: list[int] = field(default_factory=list)
    removed: list[int] = field(default_factory=list)
    error: str | None = None

    @property
    def failed(self) -> list[str]:
        failures = [p.provider for p in self.providers if p.status == "error"]
        return failures + (["list"] if self.status == "error" else [])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConsolidatedListSync:
    job = "list"

    def __init__(
        self,
        lists: ListRepository,
        snapshots: SnapshotStore,
        *,
        today: Callable[[], dt.date],
        list_name: str,
        safety_min_selected: int = 5,
        log: Logger = null_logger,
    ) -> None:
        self._lists = lists
        self._snapshots = snapshots
        self._today = today
        self._list_name = list_name
        self._safety_min_selected = safety_min_selected
        self._log = log

    @property
    def list_name(self) -> str:
        return self._list_name

    def _select(self, provider: Provider, today: dt.date, entry: ProviderSelection) -> list[int]:
        """Fill `entry` with the provider's ranked rows and return its TMDB ids in rank order."""
        raise NotImplementedError

    def run(self, providers: Iterable[Provider], *, dry_run: bool = False) -> ListSyncReport:
        today = self._today()
        report = ListSyncReport(job=self.job, run_date=today.isoformat(), dry_run=dry_run, list_name=self._list_name)

        desired: dict[int, None] = {}  # ordered set: provider order, then rank
        for provider in providers:
            entry = ProviderSelection(provider=provider.key)
            try:
                desired.update((tmdb_id, None) for tmdb_id in self._select(provider, today, entry))
            except Exception as exc:  # noqa: BLE001 - failure isolation per provider
                entry.status, entry.error = "error", f"{type(exc).__name__}: {exc}"
                self._log("provider_failed", level="ERROR", job=self.job, provider=provider.key, error=entry.error)
            report.providers.append(entry)

        # Removals are only safe when every provider answered with a sane amount of titles;
        # otherwise an outage would evict that provider's titles from the shared list.
        healthy = not report.failed and all(len(p.selected) >= self._safety_min_selected for p in report.providers)
        if not healthy:
            report.status = "degraded"
        try:
            outcome = reconcile_list(
                self._lists,
                self._list_name,
                desired,
                dry_run=dry_run,
                allow_removals=healthy,
                log=self._log,
                job=self.job,
            )
            report.list_id, report.list_created, report.list_url = outcome.ref.id, outcome.ref.created, outcome.ref.url
            report.added, report.removed = outcome.added, outcome.removed
        except Exception as exc:  # noqa: BLE001 - use-case boundary
            report.status, report.error = "error", f"{type(exc).__name__}: {exc}"
            self._log("list_sync_failed", level="ERROR", job=self.job, error=report.error)

        save_snapshot(self._snapshots, f"{self.job}/{report.run_date}.json", report.to_dict(), self._log)
        self._log("run_finished", job=self.job, dry_run=dry_run, items=len(desired), failed=report.failed)
        return report
