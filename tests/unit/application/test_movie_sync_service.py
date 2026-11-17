import unittest

from streaming_top_series.domain import PROVIDERS, MovieCriteria
from tests.support.fakes import (
    FakeMovieCatalog,
    FakeRatings,
    InMemoryListRepository,
    InMemorySnapshotStore,
    make_movie,
    movie_service,
)

ALL_PROVIDERS = list(PROVIDERS.values())
CRITERIA = MovieCriteria(top_n=3, window_steps_days=(30, 60, 120))


def movies(ids, days_ago=1):
    return [make_movie(i, days_ago=days_ago) for i in ids]


def make_service(catalog, lists=None, snapshots=None, **kwargs):
    kwargs.setdefault("safety_min_selected", 1)
    return movie_service(catalog, lists, snapshots, criteria=CRITERIA, **kwargs)


class MovieListSyncServiceTest(unittest.TestCase):
    def test_single_list_with_top_n_per_provider(self):
        lists = InMemoryListRepository()
        catalog = FakeMovieCatalog(
            {"netflix": movies(range(1, 6)), "hbo": movies(range(10, 14)), "prime": movies(range(20, 25))}
        )
        report = make_service(catalog, lists).run(ALL_PROVIDERS)

        self.assertEqual(list(lists.lists), ["StreammyMovies"])
        self.assertEqual(len(lists.items_of("StreammyMovies")), 9)
        self.assertEqual([len(p.selected) for p in report.providers], [3, 3, 3])
        self.assertTrue(report.list_created)

    def test_window_widens_until_top_n_is_reached(self):
        catalog = FakeMovieCatalog({"hbo": [*movies([1], days_ago=10), *movies([2, 3], days_ago=100)]})
        report = make_service(catalog).run([PROVIDERS["hbo"]])
        self.assertEqual(report.providers[0].window_days, 120)
        self.assertEqual(catalog.windows, [("hbo", 30), ("hbo", 60), ("hbo", 120)])

    def test_movie_shared_by_two_providers_is_listed_once(self):
        lists = InMemoryListRepository()
        catalog = FakeMovieCatalog({"netflix": movies([1, 2, 3]), "prime": movies([3, 4, 5])})
        make_service(catalog, lists).run([PROVIDERS["netflix"], PROVIDERS["prime"]])
        self.assertEqual(lists.items_of("StreammyMovies"), {1, 2, 3, 4, 5})

    def test_imdb_rating_overrides_tmdb_for_the_cut(self):
        catalog = FakeMovieCatalog({"netflix": [make_movie(1, vote=8.0, imdb_id="tt1"), make_movie(2, vote=6.0)]})
        ratings = FakeRatings({"tt1": (4.2, 5000)})  # IMDb rejects what TMDB would accept
        report = make_service(catalog, ratings=ratings).run([PROVIDERS["netflix"]])
        self.assertEqual([row["tmdb_id"] for row in report.providers[0].selected], [2])
        self.assertEqual(report.providers[0].rejected, {"low_score": 1})

    def test_rotation_and_idempotency(self):
        catalog = FakeMovieCatalog({"netflix": movies(range(1, 6))})
        service = make_service(catalog)
        service.run([PROVIDERS["netflix"]])
        self.assertEqual(service.run([PROVIDERS["netflix"]]).added, [])

        catalog.by_provider["netflix"] = movies(range(4, 9))
        report = service.run([PROVIDERS["netflix"]])
        self.assertEqual((report.added, report.removed), ([4, 5, 6], [1, 2, 3]))

    def test_provider_failure_blocks_removals_from_the_shared_list(self):
        lists = InMemoryListRepository()
        catalog = FakeMovieCatalog({"netflix": movies([1, 2, 3]), "hbo": movies([10, 11, 12])})
        service = make_service(catalog, lists)
        service.run([PROVIDERS["netflix"], PROVIDERS["hbo"]])

        catalog.failing = {"hbo"}
        report = service.run([PROVIDERS["netflix"], PROVIDERS["hbo"]])
        self.assertEqual(report.status, "degraded")
        self.assertEqual(report.failed, ["hbo"])
        self.assertEqual(report.removed, [])
        self.assertEqual(lists.items_of("StreammyMovies"), {1, 2, 3, 10, 11, 12})

    def test_dry_run_never_writes_and_snapshot_is_saved(self):
        lists, snapshots = InMemoryListRepository(), InMemorySnapshotStore()
        make_service(FakeMovieCatalog({"netflix": movies([1, 2, 3])}), lists, snapshots).run(
            [PROVIDERS["netflix"]], dry_run=True
        )
        self.assertEqual(lists.writes, [])
        self.assertIn("movies/2026-11-17.json", snapshots.saved)

    def test_list_failure_is_reported(self):
        class BrokenLists(InMemoryListRepository):
            def ensure_list(self, name, *, dry_run):
                raise ConnectionError("mdblist down")

        report = make_service(FakeMovieCatalog({"netflix": movies([1, 2, 3])}), BrokenLists()).run(
            [PROVIDERS["netflix"]]
        )
        self.assertEqual(report.failed, ["list"])


if __name__ == "__main__":
    unittest.main()
