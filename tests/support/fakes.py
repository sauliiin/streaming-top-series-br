"""In-memory test doubles for the application ports and the HTTP client."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from typing import Any

from streaming_top_series.application import ListRef
from streaming_top_series.domain import Episode, Movie, MovieCriteria, Provider, SelectionCriteria, Show

TODAY = dt.date(2026, 11, 17)


def make_show(
    tmdb_id: int,
    *,
    days_ago: int = 1,
    vote: float = 8.0,
    votes: int = 100,
    name: str | None = None,
    original_name: str = "",
    genres: Iterable[int] = (18,),
    imdb_id: str | None = None,
) -> Show:
    return Show(
        tmdb_id=tmdb_id,
        name=name or f"Show {tmdb_id}",
        original_name=original_name,
        genre_ids=frozenset(genres),
        vote_average=vote,
        vote_count=votes,
        last_episode=Episode(1, 1, TODAY - dt.timedelta(days=days_ago)),
        imdb_id=imdb_id,
    )


def make_shows(ids: Iterable[int]) -> list[Show]:
    return [make_show(i) for i in ids]


def make_movie(
    tmdb_id: int,
    *,
    days_ago: int = 1,
    digital_days_ago: int | None = None,
    vote: float = 6.0,
    votes: int = 100,
    genres: Iterable[int] = (18,),
    imdb_id: str | None = None,
) -> Movie:
    return Movie(
        tmdb_id=tmdb_id,
        title=f"Movie {tmdb_id}",
        genre_ids=frozenset(genres),
        vote_average=vote,
        vote_count=votes,
        primary_release_date=TODAY - dt.timedelta(days=days_ago),
        digital_release_date=None if digital_days_ago is None else TODAY - dt.timedelta(days=digital_days_ago),
        imdb_id=imdb_id,
    )


class FakeMovieCatalog:
    """Returns the provider's movies whose release falls inside the requested window."""

    def __init__(self, by_provider: dict[str, list[Movie]] | None = None, failing: set[str] | None = None) -> None:
        self.by_provider = by_provider or {}
        self.failing = failing or set()
        self.windows: list[tuple[str, int]] = []

    def recent_movies(self, provider: Provider, criteria: MovieCriteria, start: dt.date, end: dt.date) -> list[Movie]:
        self.windows.append((provider.key, (end - start).days))
        if provider.key in self.failing:
            raise ConnectionError("catalog unavailable")
        return [m for m in self.by_provider.get(provider.key, []) if m.release_in(start, end)]


class FakeRatings:
    def __init__(self, ratings: dict[str, tuple[float, int]]) -> None:
        self.ratings = ratings
        self.calls = 0

    def lookup(self, imdb_ids: Iterable[str]) -> dict[str, tuple[float, int]]:
        self.calls += 1
        return {i: self.ratings[i] for i in imdb_ids if i in self.ratings}


class FakeCatalog:
    def __init__(self, by_provider: dict[str, list[Show]] | None = None, failing: set[str] | None = None) -> None:
        self.by_provider = by_provider or {}
        self.failing = failing or set()

    def recent_shows(self, provider: Provider, criteria: SelectionCriteria, today: dt.date) -> list[Show]:
        if provider.key in self.failing:
            raise ConnectionError("catalog unavailable")
        return list(self.by_provider.get(provider.key, []))


class InMemoryListRepository:
    def __init__(self) -> None:
        self.lists: dict[str, tuple[int, set[int]]] = {}
        self.writes: list[tuple[str, int | None, list[int]]] = []

    def ensure_list(self, name: str, *, dry_run: bool) -> ListRef:
        if name in self.lists:
            return ListRef(self.lists[name][0], name)
        if dry_run:
            return ListRef(None, name, created=True)
        self.lists[name] = (len(self.lists) + 1, set())
        return ListRef(self.lists[name][0], name, created=True)

    def items_of(self, name: str) -> set[int]:
        return self.lists[name][1]

    def current_items(self, ref: ListRef) -> set[int]:
        return set(self.items_of(ref.name))

    def add(self, ref: ListRef, tmdb_ids: Iterable[int]) -> None:
        ids = list(tmdb_ids)
        self.writes.append(("add", ref.id, ids))
        self.items_of(ref.name).update(ids)

    def remove(self, ref: ListRef, tmdb_ids: Iterable[int]) -> None:
        ids = list(tmdb_ids)
        self.writes.append(("remove", ref.id, ids))
        self.items_of(ref.name).difference_update(ids)


class InMemorySnapshotStore:
    def __init__(self) -> None:
        self.saved: dict[str, dict[str, Any]] = {}

    def save(self, key: str, document: dict[str, Any]) -> None:
        self.saved[key] = document


class FakeHttp:
    """Answers by (method, path); a callable route receives the params/payload. Records every call."""

    def __init__(self, routes: dict[tuple[str, str], Any]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, str, Any]] = []

    def _answer(self, method: str, path: str, arg: Any) -> Any:
        self.calls.append((method, path, arg))
        answer = self.routes.get((method, path))
        return answer(arg) if callable(answer) else answer

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._answer("GET", path, params)

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        return self._answer("POST", path, payload)


def series_service(catalog, lists=None, snapshots=None, criteria=None, **kwargs):
    from streaming_top_series.application import SeriesListSyncService

    return SeriesListSyncService(
        catalog,
        lists if lists is not None else InMemoryListRepository(),
        snapshots if snapshots is not None else InMemorySnapshotStore(),
        criteria=criteria or SelectionCriteria(),
        today=lambda: TODAY,
        **kwargs,
    )


def movie_service(catalog, lists=None, snapshots=None, criteria=None, **kwargs):
    from streaming_top_series.application import MovieListSyncService

    return MovieListSyncService(
        catalog,
        lists if lists is not None else InMemoryListRepository(),
        snapshots if snapshots is not None else InMemorySnapshotStore(),
        criteria=criteria or MovieCriteria(),
        today=lambda: TODAY,
        **kwargs,
    )
