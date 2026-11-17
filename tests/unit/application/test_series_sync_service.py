import unittest

from streaming_top_series.domain import PROVIDERS
from tests.support.fakes import (
    FakeCatalog,
    FakeRatings,
    InMemoryListRepository,
    InMemorySnapshotStore,
    make_show,
    make_shows,
    series_service,
)

ALL_PROVIDERS = list(PROVIDERS.values())
NETFLIX = PROVIDERS["netflix"]
LIST = "StreammySeries"


class SeriesListSyncServiceTest(unittest.TestCase):
    def test_one_consolidated_list_with_top_20_per_provider(self):
        lists = InMemoryListRepository()
        catalog = FakeCatalog(
            {
                "netflix": make_shows(range(1, 26)),
                "hbo": make_shows(range(100, 125)),
                "prime": make_shows(range(200, 225)),
            }
        )
        report = series_service(catalog, lists).run(ALL_PROVIDERS)

        self.assertEqual(list(lists.lists), [LIST])
        self.assertEqual(len(lists.items_of(LIST)), 60)
        self.assertEqual([len(p.selected) for p in report.providers], [20, 20, 20])
        self.assertTrue(report.list_created)

    def test_series_shared_by_two_providers_is_listed_once(self):
        lists = InMemoryListRepository()
        catalog = FakeCatalog({"netflix": make_shows(range(1, 21)), "prime": make_shows(range(15, 35))})
        series_service(catalog, lists).run([NETFLIX, PROVIDERS["prime"]])
        self.assertEqual(len(lists.items_of(LIST)), 34)

    def test_second_run_is_idempotent(self):
        lists = InMemoryListRepository()
        service = series_service(FakeCatalog({"netflix": make_shows(range(1, 21))}), lists)
        service.run([NETFLIX])
        writes = len(lists.writes)
        report = service.run([NETFLIX])
        self.assertEqual(len(lists.writes), writes)
        self.assertEqual((report.added, report.removed), ([], []))

    def test_rotates_series_that_dropped_out_of_the_top(self):
        catalog = FakeCatalog({"netflix": make_shows(range(1, 21))})
        service = series_service(catalog)
        service.run([NETFLIX])
        catalog.by_provider["netflix"] = make_shows(range(3, 23))
        report = service.run([NETFLIX])
        self.assertEqual((report.added, report.removed), ([21, 22], [1, 2]))

    def test_dry_run_never_writes(self):
        lists = InMemoryListRepository()
        report = series_service(FakeCatalog({"netflix": make_shows(range(1, 21))}), lists).run([NETFLIX], dry_run=True)
        self.assertEqual((lists.writes, lists.lists), ([], {}))
        self.assertEqual(len(report.added), 20)

    def test_degraded_provider_blocks_removals_from_the_shared_list(self):
        lists = InMemoryListRepository()
        catalog = FakeCatalog({"netflix": make_shows(range(1, 21)), "hbo": make_shows(range(100, 120))})
        service = series_service(catalog, lists)
        service.run([NETFLIX, PROVIDERS["hbo"]])

        catalog.by_provider["hbo"] = []  # upstream returned nothing for HBO
        report = service.run([NETFLIX, PROVIDERS["hbo"]])
        self.assertEqual(report.status, "degraded")
        self.assertEqual(report.removed, [])
        self.assertEqual(len(lists.items_of(LIST)), 40)

    def test_provider_failure_is_isolated_and_reported(self):
        catalog = FakeCatalog({"netflix": make_shows(range(1, 21))}, failing={"hbo"})
        report = series_service(catalog).run([NETFLIX, PROVIDERS["hbo"]])
        self.assertEqual({p.provider: p.status for p in report.providers}, {"netflix": "ok", "hbo": "error"})
        self.assertEqual(report.failed, ["hbo"])
        self.assertEqual(len(report.added), 20)

    def test_snapshot_is_saved_per_job_and_day(self):
        snapshots = InMemorySnapshotStore()
        series_service(FakeCatalog({"netflix": make_shows(range(1, 21))}), snapshots=snapshots).run([NETFLIX])
        self.assertEqual(snapshots.saved["series/2026-11-17.json"]["providers"][0]["selected"][0]["rank"], 1)

    def test_snapshot_failure_does_not_fail_the_run(self):
        class BrokenStore:
            def save(self, key, document):
                raise OSError("storage unavailable")

        report = series_service(FakeCatalog({"netflix": make_shows(range(1, 21))}), snapshots=BrokenStore()).run(
            [NETFLIX]
        )
        self.assertEqual(report.failed, [])

    def test_imdb_rating_drives_the_cut_with_tmdb_fallback(self):
        shows = [make_show(1, vote=9.0, imdb_id="tt1"), make_show(2, vote=7.5, imdb_id="tt2"), make_show(3, vote=7.2)]
        ratings = FakeRatings({"tt1": (5.9, 900), "tt2": (8.4, 1200)})
        report = series_service(FakeCatalog({"netflix": shows}), ratings=ratings).run([NETFLIX])
        rows = report.providers[0].selected
        self.assertEqual([(r["tmdb_id"], r["score_source"]) for r in rows], [(2, "imdb"), (3, "tmdb")])

    def test_window_widens_until_there_is_a_top_20(self):
        recent = make_shows(range(1, 13))  # 12 series with an episode yesterday
        older = [make_show(i, days_ago=40) for i in range(100, 120)]  # 20 more, 40 days ago
        catalog = WindowAwareCatalog({"prime": recent + older})
        entry = series_service(catalog).run([PROVIDERS["prime"]]).providers[0]

        self.assertEqual(entry.window_days, 45)
        self.assertEqual(catalog.windows, [14, 21, 30, 45])
        self.assertEqual(len(entry.selected), 20)
        self.assertEqual([r["tmdb_id"] for r in entry.selected[:12]], list(range(1, 13)))  # most recent first

    def test_window_stays_at_14_days_when_already_full(self):
        catalog = WindowAwareCatalog({"netflix": make_shows(range(1, 25))})
        entry = series_service(catalog).run([NETFLIX]).providers[0]
        self.assertEqual((entry.window_days, catalog.windows), (14, [14]))


class WindowAwareCatalog:
    """Fake catalog that, like TMDB discover, only returns shows aired inside the window."""

    def __init__(self, by_provider):
        self.by_provider = by_provider
        self.windows = []

    def recent_shows(self, provider, criteria, today):
        self.windows.append(criteria.window_days)
        start, end = criteria.window(today)
        return [s for s in self.by_provider.get(provider.key, []) if start <= s.last_episode.air_date <= end]


if __name__ == "__main__":
    unittest.main()
