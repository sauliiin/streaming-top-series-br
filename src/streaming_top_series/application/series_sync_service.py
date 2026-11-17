"""Use case: the consolidated series list (default "StreammySeries").

Per provider: series with the most recently aired episodes, IMDb-first score cut, Top N.
The 14-day window widens step by step until N series qualify, so there is always a Top N.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Any

from ..domain import Provider, Selection, SelectionCriteria, Show, select_top
from .list_sync import ConsolidatedListSync, ProviderSelection
from .ports import RatingsProvider, ShowCatalog
from .ratings import rating_fields, with_imdb_ratings

DEFAULT_SERIES_LIST_NAME = "StreammySeries"


def series_row(rank: int, show: Show) -> dict[str, Any]:
    episode = show.last_episode
    return {
        "rank": rank,
        "tmdb_id": show.tmdb_id,
        "imdb_id": show.imdb_id,
        "poster_path": show.poster_path,
        "name": show.name,
        **rating_fields(show.rating),
        "episode": episode.code if episode else None,
        "episode_date": episode.air_date.isoformat() if episode else None,
        "next_episode_date": show.next_episode_date.isoformat() if show.next_episode_date else None,
        "status": show.status,
    }


class SeriesListSyncService(ConsolidatedListSync):
    job = "series"

    def __init__(
        self,
        catalog: ShowCatalog,
        *args: Any,
        criteria: SelectionCriteria,
        ratings: RatingsProvider | None = None,
        list_name: str = DEFAULT_SERIES_LIST_NAME,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, list_name=list_name, **kwargs)
        self._catalog = catalog
        self._criteria = criteria
        self._ratings = ratings

    def _select(self, provider: Provider, today: dt.date, entry: ProviderSelection) -> list[int]:
        selection: Selection[Show] = Selection(selected=(), rejected=())
        candidates = 0
        for days in self._criteria.widened_windows():
            criteria = dataclasses.replace(self._criteria, window_days=days)
            shows = with_imdb_ratings(self._catalog.recent_shows(provider, criteria, today), self._ratings)
            selection = select_top(shows, criteria, today)
            candidates, entry.window_days = len(shows), days
            if len(selection.selected) >= self._criteria.top_n:
                break
        entry.selected = [series_row(i, s) for i, s in enumerate(selection.selected, 1)]
        entry.rejected = selection.rejection_counts()
        self._log(
            "selection_completed",
            job=self.job,
            provider=provider.key,
            window_days=entry.window_days,
            candidates=candidates,
            selected=len(selection.selected),
            rejected=entry.rejected,
        )
        return [s.tmdb_id for s in selection.selected]
