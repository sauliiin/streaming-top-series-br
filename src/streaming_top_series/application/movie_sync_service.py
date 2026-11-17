"""Use case: the consolidated movie list (default "StreammyMovies").

Per provider the release window widens step by step (30, 60, 120... days) until
`top_n` movies qualify; the union of all providers feeds a single list.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from ..domain import Movie, MovieCriteria, Provider, Selection, select_latest_movies
from .list_sync import ConsolidatedListSync, ProviderSelection
from .ports import MovieCatalog, RatingsProvider
from .ratings import rating_fields, with_imdb_ratings

DEFAULT_MOVIE_LIST_NAME = "StreammyMovies"


def movie_row(rank: int, movie: Movie, start: dt.date, end: dt.date) -> dict[str, Any]:
    release = movie.release_in(start, end)
    return {
        "rank": rank,
        "tmdb_id": movie.tmdb_id,
        "imdb_id": movie.imdb_id,
        "poster_path": movie.poster_path,
        "title": movie.title,
        **rating_fields(movie.rating),
        "release_date": release[0].isoformat() if release else None,
        "release_kind": release[1] if release else None,
    }


class MovieListSyncService(ConsolidatedListSync):
    job = "movies"

    def __init__(
        self,
        catalog: MovieCatalog,
        *args: Any,
        criteria: MovieCriteria,
        ratings: RatingsProvider | None = None,
        list_name: str = DEFAULT_MOVIE_LIST_NAME,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, list_name=list_name, **kwargs)
        self._catalog = catalog
        self._criteria = criteria
        self._ratings = ratings

    def _select(self, provider: Provider, today: dt.date, entry: ProviderSelection) -> list[int]:
        selection: Selection[Movie] = Selection(selected=(), rejected=())
        start = today
        for days in self._criteria.window_steps_days:
            start = today - dt.timedelta(days=days)
            movies = with_imdb_ratings(
                self._catalog.recent_movies(provider, self._criteria, start, today), self._ratings
            )
            selection = select_latest_movies(movies, self._criteria, start, today)
            entry.window_days = days
            if len(selection.selected) >= self._criteria.top_n:
                break
        entry.selected = [movie_row(i, m, start, today) for i, m in enumerate(selection.selected, 1)]
        entry.rejected = selection.rejection_counts()
        self._log(
            "selection_completed",
            job=self.job,
            provider=provider.key,
            window_days=entry.window_days,
            selected=len(selection.selected),
            rejected=entry.rejected,
        )
        return [m.tmdb_id for m in selection.selected]
