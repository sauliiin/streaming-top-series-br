import io
import os
import unittest
from unittest import mock

from streaming_top_series.bootstrap import Services
from streaming_top_series.entrypoints import lambda_handler
from tests.support.fakes import (
    FakeCatalog,
    FakeMovieCatalog,
    InMemoryListRepository,
    make_movie,
    make_shows,
    movie_service,
    series_service,
)


class LambdaHandlerTest(unittest.TestCase):
    def invoke(self, event, catalog=None, movie_catalog=None):
        lists = InMemoryListRepository()

        def build(settings, env, *, dry_run, log):
            return Services(
                series=series_service(catalog or FakeCatalog(), lists, criteria=settings.criteria),
                movies=movie_service(
                    movie_catalog or FakeMovieCatalog(), lists, criteria=settings.movie_criteria, safety_min_selected=1
                ),
            )

        with (
            mock.patch.object(lambda_handler, "build_services", build),
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("sys.stdout", new_callable=io.StringIO),
        ):
            return lambda_handler.handler(event, None), lists

    def test_series_job(self):
        summary, lists = self.invoke(
            {"job": "series", "providers": ["netflix"]}, catalog=FakeCatalog({"netflix": make_shows(range(1, 21))})
        )
        self.assertEqual(summary["series"]["list"], "StreammySeries")
        self.assertEqual(summary["series"]["added"], 20)
        self.assertEqual(summary["series"]["per_provider"], {"netflix": 20})
        self.assertNotIn("movies", summary)
        self.assertEqual(len(lists.items_of("StreammySeries")), 20)

    def test_movies_job(self):
        summary, lists = self.invoke(
            {"job": "movies", "providers": ["prime"]}, movie_catalog=FakeMovieCatalog({"prime": [make_movie(1)]})
        )
        self.assertEqual(summary["movies"]["list"], "StreammyMovies")
        self.assertEqual(lists.items_of("StreammyMovies"), {1})

    def test_event_can_force_dry_run(self):
        summary, lists = self.invoke(
            {"providers": ["netflix"], "dry_run": True},
            catalog=FakeCatalog({"netflix": make_shows([1])}),
            movie_catalog=FakeMovieCatalog({"netflix": [make_movie(1)]}),
        )
        self.assertTrue(summary["dry_run"])
        self.assertEqual(lists.writes, [])

    def test_raises_when_a_job_fails_so_the_alarm_fires(self):
        with self.assertRaisesRegex(lambda_handler.SyncFailedError, "movies:hbo"):
            self.invoke({"job": "movies", "providers": ["hbo"]}, movie_catalog=FakeMovieCatalog(failing={"hbo"}))

    def test_rejects_unknown_job(self):
        with self.assertRaises(ValueError):
            self.invoke({"job": "music"})


if __name__ == "__main__":
    unittest.main()
