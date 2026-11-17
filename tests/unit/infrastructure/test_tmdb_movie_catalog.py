import datetime as dt
import unittest

from streaming_top_series.domain import PROVIDERS, MovieCriteria
from streaming_top_series.infrastructure.tmdb_catalog import TmdbMovieCatalog, movie_from_details, show_from_details
from tests.support.fakes import TODAY, FakeHttp

START = TODAY - dt.timedelta(days=30)


def movie_details(tmdb_id, *, release="2025-12-01", br_digital=("2026-11-10",), imdb="tt0000042"):
    return {
        "id": tmdb_id,
        "title": f"Movie {tmdb_id}",
        "release_date": release,
        "imdb_id": imdb,
        "genres": [{"id": 28}],
        "vote_average": 6.5,
        "vote_count": 99,
        "release_dates": {
            "results": [
                {"iso_3166_1": "US", "release_dates": [{"type": 4, "release_date": "2026-01-01T00:00:00.000Z"}]},
                {
                    "iso_3166_1": "BR",
                    "release_dates": [{"type": 4, "release_date": f"{d}T00:00:00.000Z"} for d in br_digital]
                    + [{"type": 3, "release_date": "2026-11-15T00:00:00.000Z"}],
                },
            ]
        },
    }


class TmdbMovieCatalogTest(unittest.TestCase):
    def test_maps_regional_digital_release_and_imdb_id(self):
        movie = movie_from_details(movie_details(7, br_digital=("2026-03-01", "2026-11-10")), "BR")
        self.assertEqual(movie.digital_release_date, dt.date(2026, 11, 10))
        self.assertEqual(movie.primary_release_date, dt.date(2025, 12, 1))
        self.assertEqual(movie.imdb_id, "tt0000042")

    def test_queries_digital_and_premiere_windows_and_caches_details(self):
        http = FakeHttp(
            {
                ("GET", "/discover/movie"): lambda p: {
                    "total_pages": 1,
                    "results": [{"id": 1, "genre_ids": [28]}, {"id": 2, "genre_ids": [35]}],
                },
                ("GET", "/movie/1"): movie_details(1),
            }
        )
        catalog = TmdbMovieCatalog(http)
        criteria = MovieCriteria()
        first = catalog.recent_movies(PROVIDERS["netflix"], criteria, START, TODAY)
        catalog.recent_movies(PROVIDERS["netflix"], criteria, START - dt.timedelta(days=30), TODAY)

        self.assertEqual([m.tmdb_id for m in first], [1])
        discover = [c[2] for c in http.calls if c[1] == "/discover/movie"]
        self.assertEqual(discover[0]["with_release_type"], 4)
        self.assertEqual(discover[0]["region"], "BR")
        self.assertEqual(discover[0]["without_genres"], "35")
        self.assertIn("primary_release_date.gte", discover[1])
        self.assertEqual(len([c for c in http.calls if c[1] == "/movie/1"]), 1, "details must be cached")
        self.assertFalse([c for c in http.calls if c[1] == "/movie/2"], "comedies must not be fetched")

    def test_show_imdb_id_comes_from_external_ids(self):
        show = show_from_details({"id": 1, "name": "X", "external_ids": {"imdb_id": "tt123"}})
        self.assertEqual(show.imdb_id, "tt123")


if __name__ == "__main__":
    unittest.main()
