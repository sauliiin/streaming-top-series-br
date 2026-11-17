"""Selection and reconciliation rules (pure functions, fully deterministic)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum

from .models import Movie, MovieCriteria, SelectionCriteria, Show


class RejectionReason(StrEnum):
    EXCLUDED_TERM = "excluded_term"
    EXCLUDED_GENRE = "excluded_genre"
    NO_RECENT_EPISODE = "no_recent_episode"
    OUTSIDE_WINDOW = "outside_window"
    NO_RATING = "no_rating"
    LOW_SCORE = "low_score"
    FEW_VOTES = "few_votes"


@dataclass(frozen=True)
class Selection[T]:
    selected: tuple[T, ...]
    rejected: tuple[tuple[T, RejectionReason], ...]

    def rejection_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for _, reason in self.rejected:
            counts[reason.value] = counts.get(reason.value, 0) + 1
        return counts


def matches_excluded_term(name: str, original_name: str, terms: Iterable[str]) -> bool:
    haystack = f"{name} {original_name}".casefold()
    return any(term.casefold() in haystack for term in terms)


# ---------- Series ----------


def rejection_reason(show: Show, criteria: SelectionCriteria, today: dt.date) -> RejectionReason | None:
    """Why a show is NOT eligible, or None when it qualifies."""
    if matches_excluded_term(show.name, show.original_name, criteria.excluded_terms):
        return RejectionReason.EXCLUDED_TERM
    if show.genre_ids & criteria.excluded_genres:
        return RejectionReason.EXCLUDED_GENRE
    if show.last_episode is None:
        return RejectionReason.NO_RECENT_EPISODE
    start, end = criteria.window(today)
    if not start <= show.last_episode.air_date <= end:
        return RejectionReason.OUTSIDE_WINDOW
    rating = show.rating
    if rating is None:
        return RejectionReason.NO_RATING
    if rating.value < criteria.min_vote:
        return RejectionReason.LOW_SCORE
    if rating.votes < criteria.min_vote_count:
        return RejectionReason.FEW_VOTES
    return None


def select_top(shows: Iterable[Show], criteria: SelectionCriteria, today: dt.date) -> Selection[Show]:
    """Filter, then rank by (latest episode date, score) descending and keep the top N."""
    eligible, rejected = _partition(shows, lambda s: rejection_reason(s, criteria, today))
    # -tmdb_id keeps the ordering stable across runs when date and score tie.
    eligible.sort(
        key=lambda s: (s.last_episode.air_date, s.rating.value, -s.tmdb_id),  # type: ignore[union-attr]
        reverse=True,
    )
    return Selection(selected=tuple(eligible[: criteria.top_n]), rejected=tuple(rejected))


# ---------- Movies ----------


def movie_rejection_reason(
    movie: Movie, criteria: MovieCriteria, start: dt.date, end: dt.date
) -> RejectionReason | None:
    if movie.genre_ids & criteria.excluded_genres:
        return RejectionReason.EXCLUDED_GENRE
    if movie.release_in(start, end) is None:
        return RejectionReason.OUTSIDE_WINDOW
    rating = movie.rating
    if rating is None:
        return RejectionReason.NO_RATING
    if rating.value < criteria.min_score:
        return RejectionReason.LOW_SCORE
    return None


def select_latest_movies(
    movies: Iterable[Movie], criteria: MovieCriteria, start: dt.date, end: dt.date
) -> Selection[Movie]:
    """Filter, then rank by (availability date, score) descending and keep the top N."""
    eligible, rejected = _partition(movies, lambda m: movie_rejection_reason(m, criteria, start, end))
    eligible.sort(
        key=lambda m: (m.release_in(start, end)[0], m.rating.value, -m.tmdb_id),  # type: ignore[index,union-attr]
        reverse=True,
    )
    return Selection(selected=tuple(eligible[: criteria.top_n]), rejected=tuple(rejected))


# ---------- Shared ----------


def _partition[TitleT: (Show, Movie)](
    titles: Iterable[TitleT], reason_of: Callable[[TitleT], RejectionReason | None]
) -> tuple[list[TitleT], list[tuple[TitleT, RejectionReason]]]:
    unique: dict[int, TitleT] = {}
    for title in titles:
        unique.setdefault(title.tmdb_id, title)
    eligible: list[TitleT] = []
    rejected: list[tuple[TitleT, RejectionReason]] = []
    for title in unique.values():
        reason = reason_of(title)
        if reason is None:
            eligible.append(title)
        else:
            rejected.append((title, reason))
    return eligible, rejected


@dataclass(frozen=True)
class ListDiff:
    to_add: frozenset[int]
    to_remove: frozenset[int]

    @property
    def is_noop(self) -> bool:
        return not self.to_add and not self.to_remove

    def without_removals(self) -> ListDiff:
        return ListDiff(to_add=self.to_add, to_remove=frozenset())


def compute_diff(current: Iterable[int], desired: Iterable[int]) -> ListDiff:
    current_ids, desired_ids = set(current), set(desired)
    return ListDiff(to_add=frozenset(desired_ids - current_ids), to_remove=frozenset(current_ids - desired_ids))
