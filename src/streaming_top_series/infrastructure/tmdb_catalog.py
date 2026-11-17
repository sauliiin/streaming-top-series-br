"""TMDB adapters implementing the ShowCatalog and MovieCatalog ports.

Series:
  1. /discover/tv  -> provider's flat-rate series in the region with at least one
     episode aired inside the window, excluding blocked genres, by popularity.
  2. /tv/{id}?append_to_response=external_ids -> episodes, score, genres, IMDb id.
Movies (TMDB has no "added to catalog" date, so availability is approximated by):
  1. /discover/movie with a regional DIGITAL release (type 4) inside the window, plus
     /discover/movie with the primary release inside the window (streaming originals).
  2. /movie/{id}?append_to_response=release_dates -> IMDb id, regional digital date.

Streaming availability data is provided by JustWatch through TMDB (attribution required).
"""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import threading
from typing import Any, Protocol

from ..domain import Episode, Movie, MovieCriteria, Provider, SelectionCriteria, Show, matches_excluded_term

TMDB_BASE_URL = "https://api.themoviedb.org/3"
DIGITAL_RELEASE_TYPE = 4


class HttpGetter(Protocol):
    def get(self, path: str, params: dict[str, Any] | None = None) -> Any: ...


def _parse_date(value: Any) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def show_from_details(data: dict[str, Any]) -> Show:
    last = data.get("last_episode_to_air") or {}
    air_date = _parse_date(last.get("air_date"))
    episode = (
        Episode(int(last.get("season_number") or 0), int(last.get("episode_number") or 0), air_date)
        if air_date
        else None
    )
    return Show(
        tmdb_id=int(data["id"]),
        name=data.get("name") or data.get("original_name") or "",
        original_name=data.get("original_name") or "",
        genre_ids=frozenset(int(g["id"]) for g in data.get("genres") or [] if "id" in g),
        vote_average=float(data.get("vote_average") or 0.0),
        vote_count=int(data.get("vote_count") or 0),
        last_episode=episode,
        next_episode_date=_parse_date((data.get("next_episode_to_air") or {}).get("air_date")),
        status=data.get("status") or "",
        imdb_id=(data.get("external_ids") or {}).get("imdb_id") or None,
        poster_path=data.get("poster_path") or None,
    )


def movie_from_details(data: dict[str, Any], region: str) -> Movie:
    digital_dates = [
        date
        for country in (data.get("release_dates") or {}).get("results") or []
        if country.get("iso_3166_1") == region
        for release in country.get("release_dates") or []
        if release.get("type") == DIGITAL_RELEASE_TYPE and (date := _parse_date(release.get("release_date")))
    ]
    return Movie(
        tmdb_id=int(data["id"]),
        title=data.get("title") or data.get("original_title") or "",
        genre_ids=frozenset(int(g["id"]) for g in data.get("genres") or [] if "id" in g),
        vote_average=float(data.get("vote_average") or 0.0),
        vote_count=int(data.get("vote_count") or 0),
        primary_release_date=_parse_date(data.get("release_date")),
        digital_release_date=max(digital_dates) if digital_dates else None,
        imdb_id=data.get("imdb_id") or None,
        poster_path=data.get("poster_path") or None,
    )


class _TmdbBase:
    def __init__(self, http: HttpGetter, *, language: str = "pt-BR", max_pages: int = 10, workers: int = 8) -> None:
        self._http = http
        self._language = language
        self._max_pages = max_pages
        self._workers = workers
        # Widening windows re-discover the same titles; details are fetched once per run.
        self._details_cache: dict[str, Any] = {}
        self._lock = threading.Lock()

    def _cached_get(self, path: str, params: dict[str, Any]) -> Any:
        with self._lock:
            if path in self._details_cache:
                return self._details_cache[path]
        data = self._http.get(path, params)
        with self._lock:
            self._details_cache[path] = data
        return data

    def _discover(self, kind: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        page, total_pages = 1, 1
        while page <= min(total_pages, self._max_pages):
            data = self._http.get(f"/discover/{kind}", {**params, "page": page}) or {}
            total_pages = int(data.get("total_pages") or 1)
            results.extend(data.get("results") or [])
            page += 1
        return results

    def _parallel(self, fn: Any, items: list[Any]) -> list[Any]:
        with concurrent.futures.ThreadPoolExecutor(max_workers=self._workers) as pool:
            return list(pool.map(fn, items))


class TmdbShowCatalog(_TmdbBase):
    def discover(self, provider: Provider, criteria: SelectionCriteria, today: dt.date) -> list[dict[str, Any]]:
        start, end = criteria.window(today)
        params: dict[str, Any] = {
            "watch_region": criteria.region,
            "with_watch_providers": provider.tmdb_id,
            "with_watch_monetization_types": "flatrate",
            "air_date.gte": start.isoformat(),
            "air_date.lte": end.isoformat(),
            "sort_by": "popularity.desc",
            "language": self._language,
        }
        if criteria.excluded_genres:
            params["without_genres"] = "|".join(str(g) for g in sorted(criteria.excluded_genres))
        return self._discover("tv", params)

    def recent_shows(self, provider: Provider, criteria: SelectionCriteria, today: dt.date) -> list[Show]:
        candidates = [
            raw
            for raw in self.discover(provider, criteria, today)
            # Drop early what the domain would reject anyway: fewer /tv/{id} calls.
            if not matches_excluded_term(raw.get("name") or "", raw.get("original_name") or "", criteria.excluded_terms)
        ]
        ids = list(dict.fromkeys(int(raw["id"]) for raw in candidates))
        details = self._parallel(self._details, ids)
        return [show_from_details(d) for d in details if d]

    def _details(self, tmdb_id: int) -> Any:
        return self._cached_get(f"/tv/{tmdb_id}", {"language": self._language, "append_to_response": "external_ids"})


class TmdbMovieCatalog(_TmdbBase):
    def recent_movies(self, provider: Provider, criteria: MovieCriteria, start: dt.date, end: dt.date) -> list[Movie]:
        base: dict[str, Any] = {
            "watch_region": criteria.region,
            "with_watch_providers": provider.tmdb_id,
            "with_watch_monetization_types": "flatrate",
            "sort_by": "primary_release_date.desc",
            "language": self._language,
        }
        if criteria.excluded_genres:
            base["without_genres"] = "|".join(str(g) for g in sorted(criteria.excluded_genres))
        digital = self._discover(
            "movie",
            {
                **base,
                "region": criteria.region,
                "with_release_type": DIGITAL_RELEASE_TYPE,
                "release_date.gte": start.isoformat(),
                "release_date.lte": end.isoformat(),
            },
        )
        premieres = self._discover(
            "movie",
            {**base, "primary_release_date.gte": start.isoformat(), "primary_release_date.lte": end.isoformat()},
        )
        ids = list(
            dict.fromkeys(
                int(raw["id"])
                for raw in digital + premieres
                if not set(raw.get("genre_ids") or []) & criteria.excluded_genres
            )
        )
        details = self._parallel(self._details, ids)
        return [movie_from_details(d, criteria.region) for d in details if d]

    def _details(self, tmdb_id: int) -> Any:
        return self._cached_get(
            f"/movie/{tmdb_id}", {"language": self._language, "append_to_response": "release_dates"}
        )
