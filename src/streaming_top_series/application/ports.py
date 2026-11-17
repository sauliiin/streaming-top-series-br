"""Ports required by the application layer. Infrastructure adapters implement them.

Swapping TMDB for another catalog, MDBList for Trakt, or the IMDb dataset for another
ratings source never touches the domain.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from ..domain import Movie, MovieCriteria, Provider, SelectionCriteria, Show


@dataclass(frozen=True)
class ListRef:
    id: int | None
    name: str
    slug: str = ""
    created: bool = False
    url: str | None = None  # public page of the list, when known


class ShowCatalog(Protocol):
    def recent_shows(self, provider: Provider, criteria: SelectionCriteria, today: dt.date) -> list[Show]: ...


class MovieCatalog(Protocol):
    def recent_movies(
        self, provider: Provider, criteria: MovieCriteria, start: dt.date, end: dt.date
    ) -> list[Movie]: ...


class RatingsProvider(Protocol):
    def lookup(self, imdb_ids: Iterable[str]) -> dict[str, tuple[float, int]]:
        """Return {imdb_id: (average_rating, votes)} for the ids that have a rating."""
        ...


class ListRepository(Protocol):
    """A static list of a single media type (shows or movies), identified by TMDB ids."""

    def ensure_list(self, name: str, *, dry_run: bool) -> ListRef: ...

    def current_items(self, ref: ListRef) -> set[int]: ...

    def add(self, ref: ListRef, tmdb_ids: Iterable[int]) -> None: ...

    def remove(self, ref: ListRef, tmdb_ids: Iterable[int]) -> None: ...


class SnapshotStore(Protocol):
    def save(self, key: str, document: dict[str, Any]) -> None: ...


class SiteStore(Protocol):
    """Public JSON documents consumed by the static website (e.g. data/movies.json)."""

    def load(self, name: str) -> dict[str, Any] | None: ...

    def publish(self, name: str, document: dict[str, Any]) -> None: ...
