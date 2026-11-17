import datetime as dt
import unittest

from streaming_top_series.application import SiteFeedPublisher
from streaming_top_series.bootstrap import Services
from streaming_top_series.domain import PROVIDERS
from streaming_top_series.entrypoints.jobs import run_jobs
from streaming_top_series.observability import null_logger
from tests.support.fakes import FakeCatalog, FakeMovieCatalog, make_movie, make_shows, movie_service, series_service

NETFLIX = (PROVIDERS["netflix"],)


class RecordingStore:
    def __init__(self, fail=False):
        self.fail = fail
        self.published = []

    def load(self, name):
        return None

    def publish(self, name, document):
        if self.fail:
            raise OSError("bucket unavailable")
        self.published.append(name)


def services(store):
    return Services(
        series=series_service(FakeCatalog({"netflix": make_shows(range(1, 21))})),
        movies=movie_service(FakeMovieCatalog({"netflix": [make_movie(1)]}), safety_min_selected=1),
        site=SiteFeedPublisher(store, now=lambda: dt.datetime(2026, 11, 17, tzinfo=dt.UTC)),
    )


class RunJobsTest(unittest.TestCase):
    def test_publishes_one_feed_per_job(self):
        store = RecordingStore()
        outcome = run_jobs(services(store), ["series", "movies"], NETFLIX, dry_run=False, log=null_logger)
        self.assertEqual(store.published, ["series.json", "movies.json"])
        self.assertEqual([r.job for r in outcome.reports], ["series", "movies"])
        self.assertEqual(outcome.failures, [])

    def test_site_failure_is_reported_without_hiding_the_sync_result(self):
        outcome = run_jobs(services(RecordingStore(fail=True)), ["movies"], NETFLIX, dry_run=False, log=null_logger)
        self.assertEqual(outcome.failures, ["site:movies"])
        self.assertEqual(outcome.reports[0].added, [1])


if __name__ == "__main__":
    unittest.main()
