"""Shared reconciliation step: converge a static list to the desired set of TMDB ids."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ..domain import compute_diff
from ..observability import Logger
from .ports import ListRef, ListRepository, SnapshotStore


@dataclass(frozen=True)
class ReconcileResult:
    ref: ListRef
    added: list[int]
    removed: list[int]


def reconcile_list(
    lists: ListRepository,
    list_name: str,
    desired: Iterable[int],
    *,
    dry_run: bool,
    allow_removals: bool,
    log: Logger,
    **log_context: Any,
) -> ReconcileResult:
    ref = lists.ensure_list(list_name, dry_run=dry_run)
    current = lists.current_items(ref) if ref.id is not None else set()
    diff = compute_diff(current, desired)
    if not allow_removals and diff.to_remove:
        log("removals_skipped", level="WARNING", list=list_name, skipped=len(diff.to_remove), **log_context)
        diff = diff.without_removals()

    added, removed = sorted(diff.to_add), sorted(diff.to_remove)
    if diff.is_noop:
        log("list_unchanged", list=list_name, list_id=ref.id, **log_context)
    elif dry_run:
        log("dry_run_diff", list=list_name, add=added, remove=removed, **log_context)
    else:
        if removed:
            lists.remove(ref, removed)
        if added:
            lists.add(ref, added)
        log("list_synced", list=list_name, list_id=ref.id, add=added, remove=removed, **log_context)
    return ReconcileResult(ref=ref, added=added, removed=removed)


def save_snapshot(snapshots: SnapshotStore, key: str, document: dict[str, Any], log: Logger) -> None:
    try:
        snapshots.save(key, document)
    except Exception as exc:  # noqa: BLE001 - snapshots are an audit trail, never block the sync
        log("snapshot_failed", level="WARNING", key=key, error=f"{type(exc).__name__}: {exc}")
