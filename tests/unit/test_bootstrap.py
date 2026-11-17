import unittest

from streaming_top_series.bootstrap import ConfigurationError, build_services
from streaming_top_series.infrastructure import secrets
from streaming_top_series.infrastructure.imdb_ratings import ImdbDatasetRatings
from streaming_top_series.infrastructure.mdblist_repository import MdblistListRepository, OfflineListRepository
from streaming_top_series.infrastructure.snapshot_stores import LocalSnapshotStore, NullSnapshotStore
from streaming_top_series.settings import Settings


def build(env, *, dry_run=False):
    return build_services(Settings.from_env(env), env, dry_run=dry_run)


class BuildServicesTest(unittest.TestCase):
    def setUp(self):
        secrets.clear_cache()

    def test_requires_tmdb_credentials(self):
        with self.assertRaises(ConfigurationError):
            build({"MDBLIST_API_KEY": "x"})

    def test_requires_mdblist_credentials_outside_dry_run(self):
        with self.assertRaises(ConfigurationError):
            build({"TMDB_API_KEY": "x"})

    def test_dry_run_without_mdblist_uses_offline_repositories(self):
        services = build({"TMDB_READ_TOKEN": "x", "IMDB_RATINGS": "false"}, dry_run=True)
        self.assertIsInstance(services.series._lists, OfflineListRepository)
        self.assertIsInstance(services.movies._lists, OfflineListRepository)
        self.assertIsInstance(services.series._snapshots, NullSnapshotStore)
        self.assertIsNone(services.movies._ratings)

    def test_full_wiring(self):
        services = build({"TMDB_API_KEY": "x", "MDBLIST_API_KEY": "y", "SNAPSHOT_DIR": "/tmp/unused"})
        self.assertIsInstance(services.series._lists, MdblistListRepository)
        self.assertEqual(services.series._lists._media_type, "shows")
        self.assertEqual(services.movies._lists._media_type, "movies")
        self.assertIsInstance(services.movies._snapshots, LocalSnapshotStore)
        self.assertIsInstance(services.movies._ratings, ImdbDatasetRatings)
        self.assertIs(services.series._ratings, services.movies._ratings)
        self.assertEqual(services.movies.list_name, "StreammyMovies")
        self.assertEqual(services.series.list_name, "StreammySeries")


if __name__ == "__main__":
    unittest.main()
