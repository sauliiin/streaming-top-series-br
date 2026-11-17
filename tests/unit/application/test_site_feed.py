import datetime as dt
import unittest

from streaming_top_series.application import SiteFeedPublisher
from streaming_top_series.domain import PROVIDERS
from tests.support.fakes import FakeCatalog, FakeMovieCatalog, make_movie, make_shows, movie_service, series_service

NOW = dt.datetime(2026, 11, 17, 9, 15, tzinfo=dt.UTC)


class InMemorySiteStore:
    def __init__(self, initial=None):
        self.documents = dict(initial or {})

    def load(self, name):
        return self.documents.get(name)

    def publish(self, name, document):
        self.documents[name] = document


def series_report(catalog):
    return series_service(catalog).run(list(PROVIDERS.values()), dry_run=True)


class SiteFeedPublisherTest(unittest.TestCase):
    def test_series_feed_shape(self):
        store = InMemorySiteStore()
        feed = SiteFeedPublisher(store, now=lambda: NOW).publish(
            series_report(FakeCatalog({"netflix": make_shows(range(1, 4))}))
        )

        self.assertIs(store.documents["series.json"], feed)
        self.assertEqual((feed["schema"], feed["kind"], feed["run_date"]), (1, "series", "2026-11-17"))
        self.assertEqual(feed["generated_at"], "2026-11-17T09:15:00+00:00")
        self.assertEqual(feed["list_name"], "StreammySeries")
        self.assertEqual([p["key"] for p in feed["providers"]], ["netflix", "hbo", "prime"])
        item = feed["providers"][0]["items"][0]
        self.assertEqual((item["rank"], item["label"]), (1, "S01E01"))
        self.assertEqual(item["links"]["tmdb"], f"https://www.themoviedb.org/tv/{item['tmdb_id']}")

    def test_movie_feed_has_posters_and_imdb_links(self):
        movie = make_movie(9, imdb_id="tt0009")
        movie = movie.__class__(**{**movie.__dict__, "poster_path": "/abc.jpg"})
        report = movie_service(FakeMovieCatalog({"prime": [movie]})).run([PROVIDERS["prime"]], dry_run=True)
        feed = SiteFeedPublisher(InMemorySiteStore(), now=lambda: NOW).publish(report)

        item = feed["providers"][0]["items"][0]
        self.assertEqual(item["poster"], "https://image.tmdb.org/t/p/w342/abc.jpg")
        self.assertEqual(item["links"]["imdb"], "https://www.imdb.com/title/tt0009/")
        self.assertEqual(item["label"], "premiere")
        self.assertEqual((feed["kind"], feed["list_name"]), ("movies", "StreammyMovies"))

    def test_failed_provider_keeps_previous_section_marked_stale(self):
        previous_section = {
            "key": "hbo",
            "name": "HBO Max",
            "updated": "2026-11-16",
            "stale": False,
            "items": [{"x": 1}],
        }
        store = InMemorySiteStore({"series.json": {"providers": [previous_section]}})
        report = series_report(FakeCatalog({"netflix": make_shows([1])}, failing={"hbo", "prime"}))
        feed = SiteFeedPublisher(store, now=lambda: NOW).publish(report)

        sections = {p["key"]: p for p in feed["providers"]}
        self.assertTrue(sections["hbo"]["stale"])
        self.assertEqual(sections["hbo"]["updated"], "2026-11-16")
        self.assertEqual(sections["hbo"]["items"], [{"x": 1}])
        self.assertFalse(sections["netflix"]["stale"])
        self.assertEqual(sections["prime"]["items"], [])  # nothing to fall back to


if __name__ == "__main__":
    unittest.main()
