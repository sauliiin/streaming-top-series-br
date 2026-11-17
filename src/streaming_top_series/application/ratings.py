"""Enrich catalog titles with IMDb ratings (the domain decides how to use them)."""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence

from ..domain import Movie, Rating, Show
from .ports import RatingsProvider


def with_imdb_ratings[TitleT: (Show, Movie)](titles: Sequence[TitleT], ratings: RatingsProvider | None) -> list[TitleT]:
    if ratings is None:
        return list(titles)
    found = ratings.lookup(t.imdb_id for t in titles if t.imdb_id)
    enriched: list[TitleT] = []
    for title in titles:
        hit = found.get(title.imdb_id) if title.imdb_id else None
        enriched.append(dataclasses.replace(title, imdb_rating=hit[0], imdb_votes=hit[1]) if hit else title)
    return enriched


def rating_fields(rating: Rating | None) -> dict[str, object]:
    if rating is None:
        return {"score": None, "votes": 0, "score_source": None}
    return {"score": rating.value, "votes": rating.votes, "score_source": rating.source}
