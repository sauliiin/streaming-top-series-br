"""12-factor configuration: everything comes from the environment; defaults encode the agreed criteria."""

from __future__ import annotations

import datetime as dt
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .application import DEFAULT_MOVIE_LIST_NAME, DEFAULT_SERIES_LIST_NAME
from .domain import PROVIDERS, MovieCriteria, Provider, SelectionCriteria

# Brazil abolished daylight saving time in 2019; a fixed UTC-3 offset avoids depending on tzdata.
BRASILIA_TZ = dt.timezone(dt.timedelta(hours=-3), "BRT")
JOBS = ("series", "movies")


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_list(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _genres(env: Mapping[str, str], key: str, default: frozenset[int]) -> frozenset[int]:
    return frozenset(int(g) for g in _as_list(env[key])) if key in env else default


@dataclass(frozen=True)
class Settings:
    providers: tuple[Provider, ...]
    criteria: SelectionCriteria
    movie_criteria: MovieCriteria
    series_list_name: str
    movie_list_name: str
    safety_min_selected: int
    imdb_ratings: bool
    imdb_cache_dir: str
    dry_run: bool
    snapshot_bucket: str | None
    snapshot_dir: str | None
    site_bucket: str | None
    site_dir: str | None

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Settings:
        keys = _as_list(env.get("PROVIDERS")) or list(PROVIDERS)
        unknown = [k for k in keys if k not in PROVIDERS]
        if unknown:
            raise ValueError(f"Unknown PROVIDERS {unknown}; valid values: {sorted(PROVIDERS)}")

        region = env.get("REGION", "BR")
        series = SelectionCriteria()
        criteria = SelectionCriteria(
            region=region,
            window_days=int(env.get("WINDOW_DAYS", series.window_days)),
            top_n=int(env.get("TOP_N", series.top_n)),
            min_vote=float(env.get("MIN_VOTE", series.min_vote)),
            min_vote_count=int(env.get("MIN_VOTE_COUNT", series.min_vote_count)),
            excluded_terms=(
                tuple(_as_list(env["EXCLUDED_TERMS"])) if "EXCLUDED_TERMS" in env else series.excluded_terms
            ),
            excluded_genres=_genres(env, "EXCLUDED_GENRES", series.excluded_genres),
            window_steps_days=(
                tuple(int(d) for d in _as_list(env["WINDOW_STEPS_DAYS"]))
                if "WINDOW_STEPS_DAYS" in env
                else series.window_steps_days
            ),
        )
        movies = MovieCriteria()
        movie_criteria = MovieCriteria(
            region=region,
            top_n=int(env.get("MOVIES_TOP_N", movies.top_n)),
            min_score=float(env.get("MOVIES_MIN_SCORE", movies.min_score)),
            excluded_genres=_genres(env, "MOVIES_EXCLUDED_GENRES", movies.excluded_genres),
            window_steps_days=(
                tuple(int(d) for d in _as_list(env["MOVIES_WINDOW_STEPS_DAYS"]))
                if "MOVIES_WINDOW_STEPS_DAYS" in env
                else movies.window_steps_days
            ),
        )
        return cls(
            providers=tuple(PROVIDERS[k] for k in keys),
            criteria=criteria,
            movie_criteria=movie_criteria,
            series_list_name=env.get("SERIES_LIST_NAME", DEFAULT_SERIES_LIST_NAME),
            movie_list_name=env.get("MOVIES_LIST_NAME", DEFAULT_MOVIE_LIST_NAME),
            safety_min_selected=int(env.get("SAFETY_MIN_SELECTED", 5)),
            imdb_ratings=_as_bool(env.get("IMDB_RATINGS"), default=True),
            imdb_cache_dir=env.get("IMDB_CACHE_DIR") or str(Path(tempfile.gettempdir()) / "streaming-top-series-imdb"),
            dry_run=_as_bool(env.get("DRY_RUN")),
            snapshot_bucket=env.get("SNAPSHOT_BUCKET") or None,
            snapshot_dir=env.get("SNAPSHOT_DIR") or None,
            site_bucket=env.get("SITE_BUCKET") or None,
            site_dir=env.get("SITE_DIR") or None,
        )


def today_in_brazil() -> dt.date:
    return dt.datetime.now(BRASILIA_TZ).date()
