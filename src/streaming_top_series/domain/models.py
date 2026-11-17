"""Domain entities and value objects. Pure Python: no I/O, no network, no cloud SDKs."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

REALITY_GENRE_ID = 10764
COMEDY_GENRE_ID = 35


@dataclass(frozen=True)
class Provider:
    key: str
    tmdb_id: int
    display_name: str


PROVIDERS: dict[str, Provider] = {
    "netflix": Provider("netflix", 8, "Netflix"),
    "hbo": Provider("hbo", 1899, "HBO Max"),
    "prime": Provider("prime", 119, "Prime Video"),
}


@dataclass(frozen=True)
class Rating:
    value: float
    votes: int
    source: str  # "imdb" | "tmdb"


def effective_rating(imdb_rating: float | None, imdb_votes: int, tmdb_rating: float, tmdb_votes: int) -> Rating | None:
    """IMDb is the primary score; TMDB is only a fallback. No score at all -> None."""
    if imdb_rating is not None and imdb_votes > 0:
        return Rating(imdb_rating, imdb_votes, "imdb")
    if tmdb_rating > 0:
        return Rating(tmdb_rating, tmdb_votes, "tmdb")
    return None


@dataclass(frozen=True)
class Episode:
    season: int
    number: int
    air_date: dt.date

    @property
    def code(self) -> str:
        return f"S{self.season:02}E{self.number:02}"


@dataclass(frozen=True)
class Show:
    tmdb_id: int
    name: str
    original_name: str = ""
    genre_ids: frozenset[int] = frozenset()
    vote_average: float = 0.0
    vote_count: int = 0
    last_episode: Episode | None = None
    next_episode_date: dt.date | None = None
    status: str = ""
    imdb_id: str | None = None
    poster_path: str | None = None
    imdb_rating: float | None = None
    imdb_votes: int = 0

    @property
    def rating(self) -> Rating | None:
        return effective_rating(self.imdb_rating, self.imdb_votes, self.vote_average, self.vote_count)


@dataclass(frozen=True)
class Movie:
    tmdb_id: int
    title: str
    genre_ids: frozenset[int] = frozenset()
    vote_average: float = 0.0
    vote_count: int = 0
    primary_release_date: dt.date | None = None
    digital_release_date: dt.date | None = None  # latest digital (TMDB type 4) release in the region
    imdb_id: str | None = None
    poster_path: str | None = None
    imdb_rating: float | None = None
    imdb_votes: int = 0

    @property
    def rating(self) -> Rating | None:
        return effective_rating(self.imdb_rating, self.imdb_votes, self.vote_average, self.vote_count)

    def release_in(self, start: dt.date, end: dt.date) -> tuple[dt.date, str] | None:
        """Date the movie became available inside [start, end]: digital release first, then premiere."""
        if self.digital_release_date and start <= self.digital_release_date <= end:
            return self.digital_release_date, "digital"
        if self.primary_release_date and start <= self.primary_release_date <= end:
            return self.primary_release_date, "premiere"
        return None


@dataclass(frozen=True)
class SelectionCriteria:
    """Business rules for what qualifies as a 'recent, well-rated series'."""

    region: str = "BR"
    window_days: int = 14  # window currently being evaluated (the first step by default)
    top_n: int = 20
    min_vote: float = 6.0
    min_vote_count: int = 0
    excluded_terms: tuple[str, ...] = ("chicago", "lei & ordem", "law & order", "ncis")
    excluded_genres: frozenset[int] = field(default_factory=lambda: frozenset({REALITY_GENRE_ID}))
    # There must always be a Top N: when the first window has fewer than top_n eligible
    # series, it widens step by step, which yields the N most recently aired ones.
    window_steps_days: tuple[int, ...] = (14, 21, 30, 45, 60, 90, 180, 365)

    def window(self, today: dt.date) -> tuple[dt.date, dt.date]:
        return today - dt.timedelta(days=self.window_days), today

    def widened_windows(self) -> tuple[int, ...]:
        """Window sizes to try, in order, starting with the configured window_days."""
        return (self.window_days, *sorted(d for d in self.window_steps_days if d > self.window_days))


@dataclass(frozen=True)
class MovieCriteria:
    """Business rules for the latest movie releases per provider."""

    region: str = "BR"
    top_n: int = 20
    min_score: float = 5.0
    excluded_genres: frozenset[int] = field(default_factory=lambda: frozenset({COMEDY_GENRE_ID}))
    # The window widens step by step until top_n movies qualify.
    window_steps_days: tuple[int, ...] = (30, 60, 120, 240, 365)
