import unittest

from streaming_top_series.domain import SelectionCriteria
from streaming_top_series.settings import Settings


class SettingsTest(unittest.TestCase):
    def test_defaults_encode_the_agreed_criteria(self):
        settings = Settings.from_env({})
        self.assertEqual([p.key for p in settings.providers], ["netflix", "hbo", "prime"])
        self.assertEqual(settings.criteria, SelectionCriteria())
        self.assertFalse(settings.dry_run)

    def test_environment_overrides(self):
        settings = Settings.from_env(
            {
                "PROVIDERS": "prime",
                "TOP_N": "10",
                "MIN_VOTE": "7.5",
                "DRY_RUN": "true",
                "EXCLUDED_TERMS": "foo, bar",
                "EXCLUDED_GENRES": "",
            }
        )
        self.assertEqual([p.tmdb_id for p in settings.providers], [119])
        self.assertEqual((settings.criteria.top_n, settings.criteria.min_vote), (10, 7.5))
        self.assertEqual(settings.criteria.excluded_terms, ("foo", "bar"))
        self.assertEqual(settings.criteria.excluded_genres, frozenset())
        self.assertTrue(settings.dry_run)

    def test_unknown_provider_is_rejected(self):
        with self.assertRaises(ValueError):
            Settings.from_env({"PROVIDERS": "disney"})


if __name__ == "__main__":
    unittest.main()
