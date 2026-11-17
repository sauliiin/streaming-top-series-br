import unittest

from streaming_top_series.domain import PROVIDERS, SelectionCriteria
from streaming_top_series.infrastructure.tmdb_catalog import TmdbShowCatalog, show_from_details
from tests.support.fakes import TODAY, FakeHttp


def tv_details(tmdb_id, name, air_date="2026-11-15", vote=8.1):
    return {
        "id": tmdb_id,
        "name": name,
        "original_name": name,
        "genres": [{"id": 18, "name": "Drama"}],
        "vote_average": vote,
        "vote_count": 321,
        "status": "Returning Series",
        "last_episode_to_air": {"air_date": air_date, "season_number": 2, "episode_number": 5},
        "next_episode_to_air": {"air_date": "2026-11-22"},
    }


class TmdbShowCatalogTest(unittest.TestCase):
    def test_discover_params_pagination_and_early_exclusion(self):
        pages = {
            1: {"total_pages": 2, "results": [{"id": 1, "name": "Kept"}, {"id": 2, "name": "Chicago P.D."}]},
            2: {"total_pages": 2, "results": [{"id": 3, "name": "Other"}, {"id": 1, "name": "Kept"}]},
        }
        http = FakeHttp(
            {
                ("GET", "/discover/tv"): lambda params: pages[params["page"]],
                ("GET", "/tv/1"): tv_details(1, "Kept"),
                ("GET", "/tv/3"): tv_details(3, "Other"),
            }
        )
        shows = TmdbShowCatalog(http).recent_shows(PROVIDERS["hbo"], SelectionCriteria(), TODAY)

        self.assertEqual(sorted(s.tmdb_id for s in shows), [1, 3])
        discover = next(call[2] for call in http.calls if call[1] == "/discover/tv")
        self.assertEqual(discover["with_watch_providers"], 1899)
        self.assertEqual(discover["watch_region"], "BR")
        self.assertEqual(discover["air_date.gte"], "2026-11-03")
        self.assertEqual(discover["without_genres"], "10764")
        self.assertFalse([c for c in http.calls if c[1] == "/tv/2"], "excluded shows must not be fetched")

    def test_maps_details_to_domain(self):
        show = show_from_details(tv_details(42, "DOC"))
        self.assertEqual(show.last_episode.code, "S02E05")
        self.assertEqual(show.next_episode_date.isoformat(), "2026-11-22")
        self.assertEqual(show.genre_ids, {18})

    def test_show_without_aired_episode(self):
        self.assertIsNone(show_from_details({"id": 1, "name": "X", "last_episode_to_air": None}).last_episode)

    def test_details_are_fetched_once_across_widening_windows(self):
        http = FakeHttp(
            {
                ("GET", "/discover/tv"): {"total_pages": 1, "results": [{"id": 1, "name": "Kept"}]},
                ("GET", "/tv/1"): tv_details(1, "Kept"),
            }
        )
        catalog = TmdbShowCatalog(http)
        for days in (14, 21, 30):
            catalog.recent_shows(PROVIDERS["prime"], SelectionCriteria(window_days=days), TODAY)
        self.assertEqual(len([c for c in http.calls if c[1] == "/tv/1"]), 1)
        self.assertEqual(len([c for c in http.calls if c[1] == "/discover/tv"]), 3)


if __name__ == "__main__":
    unittest.main()
