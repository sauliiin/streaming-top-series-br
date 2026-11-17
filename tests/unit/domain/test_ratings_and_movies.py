import datetime as dt
import unittest

from streaming_top_series.domain import (
    COMEDY_GENRE_ID,
    MovieCriteria,
    Rating,
    RejectionReason,
    SelectionCriteria,
    effective_rating,
    movie_rejection_reason,
    rejection_reason,
    select_latest_movies,
)
from tests.support.fakes import TODAY, make_movie, make_show

WINDOW_START = TODAY - dt.timedelta(days=30)


class EffectiveRatingTest(unittest.TestCase):
    def test_imdb_takes_precedence_over_tmdb(self):
        self.assertEqual(effective_rating(6.1, 500, 8.0, 40), Rating(6.1, 500, "imdb"))

    def test_tmdb_is_the_fallback(self):
        self.assertEqual(effective_rating(None, 0, 7.4, 12), Rating(7.4, 12, "tmdb"))

    def test_no_score_anywhere(self):
        self.assertIsNone(effective_rating(None, 0, 0.0, 0))

    def test_series_cut_uses_imdb_score(self):
        criteria = SelectionCriteria()
        show = make_show(1, vote=9.0)  # TMDB says 9.0 ...
        imdb_low = show.__class__(**{**show.__dict__, "imdb_rating": 5.8, "imdb_votes": 900})  # ... IMDb says 5.8
        self.assertEqual(rejection_reason(imdb_low, criteria, TODAY), RejectionReason.LOW_SCORE)


class MovieSelectionTest(unittest.TestCase):
    def setUp(self):
        self.criteria = MovieCriteria(top_n=3)

    def reason(self, movie):
        return movie_rejection_reason(movie, self.criteria, WINDOW_START, TODAY)

    def test_rules(self):
        self.assertIsNone(self.reason(make_movie(1, vote=5.0)))
        self.assertEqual(self.reason(make_movie(2, vote=4.9)), RejectionReason.LOW_SCORE)
        self.assertEqual(self.reason(make_movie(3, vote=0.0)), RejectionReason.NO_RATING)
        self.assertEqual(self.reason(make_movie(4, genres=[COMEDY_GENRE_ID])), RejectionReason.EXCLUDED_GENRE)
        self.assertEqual(self.reason(make_movie(5, days_ago=90)), RejectionReason.OUTSIDE_WINDOW)

    def test_digital_release_brings_an_old_premiere_into_the_window(self):
        movie = make_movie(1, days_ago=200, digital_days_ago=3)
        self.assertEqual(movie.release_in(WINDOW_START, TODAY), (TODAY - dt.timedelta(days=3), "digital"))
        self.assertIsNone(self.reason(movie))

    def test_ranks_by_availability_date_then_score_and_truncates(self):
        movies = [make_movie(1, days_ago=5), make_movie(2, days_ago=1, vote=5.5), make_movie(3, days_ago=1, vote=7.0)]
        movies.append(make_movie(4, days_ago=10))
        selection = select_latest_movies(movies, self.criteria, WINDOW_START, TODAY)
        self.assertEqual([m.tmdb_id for m in selection.selected], [3, 2, 1])


if __name__ == "__main__":
    unittest.main()
