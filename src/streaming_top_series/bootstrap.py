"""Composition root: the only module that knows every concrete adapter."""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass

from .application import (
    ListRepository,
    MovieListSyncService,
    RatingsProvider,
    SeriesListSyncService,
    SiteFeedPublisher,
    SiteStore,
    SnapshotStore,
)
from .infrastructure.http_client import JsonHttpClient
from .infrastructure.imdb_ratings import ImdbDatasetRatings
from .infrastructure.mdblist_repository import (
    MDBLIST_BASE_URL,
    MdblistListRepository,
    MediaType,
    OfflineListRepository,
)
from .infrastructure.secrets import resolve_secrets
from .infrastructure.site_stores import LocalSiteStore, S3SiteStore
from .infrastructure.snapshot_stores import LocalSnapshotStore, NullSnapshotStore, S3SnapshotStore
from .infrastructure.tmdb_catalog import TMDB_BASE_URL, TmdbMovieCatalog, TmdbShowCatalog
from .observability import Logger, null_logger
from .settings import Settings, today_in_brazil

SECRET_NAMES = ["TMDB_API_KEY", "TMDB_READ_TOKEN", "MDBLIST_API_KEY"]


class ConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Services:
    series: SeriesListSyncService
    movies: MovieListSyncService
    site: SiteFeedPublisher | None = None


def build_services(
    settings: Settings,
    env: Mapping[str, str],
    *,
    dry_run: bool,
    log: Logger = null_logger,
) -> Services:
    credentials = resolve_secrets(env, SECRET_NAMES)

    if credentials.get("TMDB_READ_TOKEN"):
        tmdb_http = JsonHttpClient(TMDB_BASE_URL, headers={"Authorization": f"Bearer {credentials['TMDB_READ_TOKEN']}"})
    elif credentials.get("TMDB_API_KEY"):
        tmdb_http = JsonHttpClient(TMDB_BASE_URL, default_params={"api_key": credentials["TMDB_API_KEY"]})
    else:
        raise ConfigurationError("Set TMDB_API_KEY or TMDB_READ_TOKEN (or the *_PARAM variant pointing to SSM).")

    def list_repository(media_type: MediaType) -> ListRepository:
        if credentials.get("MDBLIST_API_KEY"):
            http = JsonHttpClient(MDBLIST_BASE_URL, default_params={"apikey": credentials["MDBLIST_API_KEY"]})
            return MdblistListRepository(http, media_type)
        if dry_run:
            log("mdblist_offline", level="WARNING", reason="MDBLIST_API_KEY not set; dry-run against empty lists")
            return OfflineListRepository()
        raise ConfigurationError("Set MDBLIST_API_KEY (or MDBLIST_API_KEY_PARAM) to run a real sync.")

    snapshots: SnapshotStore
    if settings.snapshot_bucket:
        snapshots = S3SnapshotStore(settings.snapshot_bucket)
    elif settings.snapshot_dir:
        snapshots = LocalSnapshotStore(settings.snapshot_dir)
    else:
        snapshots = NullSnapshotStore()

    ratings: RatingsProvider | None = ImdbDatasetRatings(settings.imdb_cache_dir) if settings.imdb_ratings else None

    site_store: SiteStore | None = None
    if settings.site_bucket:
        site_store = S3SiteStore(settings.site_bucket)
    elif settings.site_dir:
        site_store = LocalSiteStore(settings.site_dir)
    site = SiteFeedPublisher(site_store, now=lambda: dt.datetime.now(dt.UTC), log=log) if site_store else None

    common = {"today": today_in_brazil, "safety_min_selected": settings.safety_min_selected, "log": log}
    return Services(
        series=SeriesListSyncService(
            TmdbShowCatalog(tmdb_http),
            list_repository("shows"),
            snapshots,
            criteria=settings.criteria,
            ratings=ratings,
            list_name=settings.series_list_name,
            **common,
        ),
        movies=MovieListSyncService(
            TmdbMovieCatalog(tmdb_http),
            list_repository("movies"),
            snapshots,
            criteria=settings.movie_criteria,
            ratings=ratings,
            list_name=settings.movie_list_name,
            **common,
        ),
        site=site,
    )
