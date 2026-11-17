"""Use case: turn sync reports into the public JSON feeds rendered by the website.

Feeds are versioned (`schema`) and self-describing, so the static frontend needs no backend.
When a provider fails on a given day, its section from the previous feed is kept and marked
`stale`, so the site never shows an empty provider because of a transient outage.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

from ..domain import PROVIDERS
from ..observability import Logger, null_logger
from .list_sync import ListSyncReport
from .ports import SiteStore

FEED_SCHEMA = 1
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w342"


def _links(kind: str, row: dict[str, Any]) -> dict[str, str | None]:
    imdb_id = row.get("imdb_id")
    return {
        "tmdb": f"https://www.themoviedb.org/{kind}/{row['tmdb_id']}",
        "imdb": f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else None,
    }


def _poster(row: dict[str, Any]) -> str | None:
    path = row.get("poster_path")
    return f"{TMDB_IMAGE_BASE}{path}" if path else None


def series_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": row["rank"],
        "tmdb_id": row["tmdb_id"],
        "title": row["name"],
        "poster": _poster(row),
        "score": row["score"],
        "score_source": row["score_source"],
        "votes": row["votes"],
        "date": row["episode_date"],
        "label": row["episode"],
        "next_date": row["next_episode_date"],
        "links": _links("tv", row),
    }


def movie_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": row["rank"],
        "tmdb_id": row["tmdb_id"],
        "title": row["title"],
        "poster": _poster(row),
        "score": row["score"],
        "score_source": row["score_source"],
        "votes": row["votes"],
        "date": row["release_date"],
        "label": row["release_kind"],
        "links": _links("movie", row),
    }


ITEM_MAPPERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {"series": series_item, "movies": movie_item}


class SiteFeedPublisher:
    def __init__(self, store: SiteStore, *, now: Callable[[], dt.datetime], log: Logger = null_logger) -> None:
        self._store = store
        self._now = now
        self._log = log

    def publish(self, report: ListSyncReport) -> dict[str, Any]:
        name = f"{report.job}.json"
        to_item = ITEM_MAPPERS[report.job]
        previous = {s["key"]: s for s in (self._store.load(name) or {}).get("providers", [])}

        providers = []
        for p in report.providers:
            section: dict[str, Any] = {
                "key": p.provider,
                "name": PROVIDERS[p.provider].display_name,
                "updated": report.run_date,
                "stale": False,
                "window_days": p.window_days,
                "items": [to_item(row) for row in p.selected],
            }
            if p.status == "error" and p.provider in previous:
                section = {**previous[p.provider], "stale": True}
                self._log("site_section_kept", level="WARNING", feed=name, provider=p.provider)
            providers.append(section)

        document = {
            "schema": FEED_SCHEMA,
            "kind": report.job,
            "run_date": report.run_date,
            "generated_at": self._now().astimezone(dt.UTC).isoformat(timespec="seconds"),
            "list_name": report.list_name,
            "list_url": report.list_url,
            "providers": providers,
        }
        self._store.publish(name, document)
        self._log("site_published", feed=name, providers=[p["key"] for p in providers])
        return document
