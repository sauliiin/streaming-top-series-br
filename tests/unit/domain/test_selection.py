import unittest

from streaming_top_series.domain import (
    REALITY_GENRE_ID,
    RejectionReason,
    SelectionCriteria,
    compute_diff,
    rejection_reason,
    select_top,
)
from tests.support.fakes import TODAY, make_show


class RejectionReasonTest(unittest.TestCase):
    def setUp(self) -> None:
        self.criteria = SelectionCriteria()

    def reason(self, show):
        return rejection_reason(show, self.criteria, TODAY)

    def test_eligible_show_has_no_reason(self):
        self.assertIsNone(self.reason(make_show(1)))

    def test_excluded_terms_match_localized_or_original_name_case_insensitively(self):
        self.assertEqual(self.reason(make_show(1, name="Chicago Fire")), RejectionReason.EXCLUDED_TERM)
        self.assertEqual(self.reason(make_show(2, name="Lei & Ordem: SVU")), RejectionReason.EXCLUDED_TERM)
        self.assertEqual(
            self.reason(make_show(3, name="X", original_name="NCIS: Origins")), RejectionReason.EXCLUDED_TERM
        )

    def test_reality_genre_is_excluded(self):
        self.assertEqual(self.reason(make_show(1, genres=[REALITY_GENRE_ID])), RejectionReason.EXCLUDED_GENRE)

    def test_score_below_minimum_or_missing_is_rejected(self):
        self.assertEqual(self.reason(make_show(1, vote=5.9)), RejectionReason.LOW_SCORE)
        self.assertEqual(self.reason(make_show(2, vote=0.0)), RejectionReason.NO_RATING)
        self.assertIsNone(self.reason(make_show(3, vote=6.0)))

    def test_episode_must_fall_inside_the_window(self):
        self.assertEqual(self.reason(make_show(1, days_ago=15)), RejectionReason.OUTSIDE_WINDOW)
        self.assertEqual(self.reason(make_show(2, days_ago=-1)), RejectionReason.OUTSIDE_WINDOW)
        self.assertIsNone(self.reason(make_show(3, days_ago=14)))

    def test_min_vote_count_is_opt_in(self):
        strict = SelectionCriteria(min_vote_count=10)
        self.assertEqual(rejection_reason(make_show(1, vote=10.0, votes=3), strict, TODAY), RejectionReason.FEW_VOTES)


class SelectTopTest(unittest.TestCase):
    def test_ranks_by_latest_episode_then_score_and_truncates(self):
        shows = [make_show(i, days_ago=i % 5, vote=7.0 + (i % 3)) for i in range(1, 31)]
        result = select_top(shows, SelectionCriteria(top_n=20), TODAY)
        self.assertEqual(len(result.selected), 20)
        keys = [(s.last_episode.air_date, s.vote_average) for s in result.selected]
        self.assertEqual(keys, sorted(keys, reverse=True))

    def test_ordering_is_deterministic_on_ties(self):
        shows = [make_show(i) for i in (5, 3, 9)]
        first = [s.tmdb_id for s in select_top(shows, SelectionCriteria(), TODAY).selected]
        second = [s.tmdb_id for s in select_top(list(reversed(shows)), SelectionCriteria(), TODAY).selected]
        self.assertEqual(first, second)

    def test_duplicates_are_collapsed_and_rejections_counted(self):
        result = select_top([make_show(1), make_show(1), make_show(2, vote=5)], SelectionCriteria(), TODAY)
        self.assertEqual([s.tmdb_id for s in result.selected], [1])
        self.assertEqual(result.rejection_counts(), {"low_score": 1})


class ComputeDiffTest(unittest.TestCase):
    def test_diff(self):
        diff = compute_diff({1, 2, 3}, [2, 3, 4])
        self.assertEqual(diff.to_add, {4})
        self.assertEqual(diff.to_remove, {1})
        self.assertTrue(compute_diff({1}, [1]).is_noop)
        self.assertEqual(diff.without_removals().to_remove, frozenset())


if __name__ == "__main__":
    unittest.main()
