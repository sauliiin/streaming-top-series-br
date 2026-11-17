import unittest

from streaming_top_series.infrastructure import secrets


class FakeSsmClient:
    def __init__(self):
        self.calls = 0

    def get_parameters(self, Names, WithDecryption):
        self.calls += 1
        assert WithDecryption
        return {"Parameters": [{"Name": n, "Value": f"value-of-{n}"} for n in Names]}


class ResolveSecretsTest(unittest.TestCase):
    def setUp(self):
        secrets.clear_cache()

    def test_environment_wins_and_ssm_fills_the_rest(self):
        env = {"TMDB_API_KEY": "local", "MDBLIST_API_KEY_PARAM": "/app/mdblist"}
        values = secrets.resolve_secrets(env, ["TMDB_API_KEY", "MDBLIST_API_KEY"], client=FakeSsmClient())
        self.assertEqual(values, {"TMDB_API_KEY": "local", "MDBLIST_API_KEY": "value-of-/app/mdblist"})

    def test_values_are_cached_per_container(self):
        ssm = FakeSsmClient()
        env = {"MDBLIST_API_KEY_PARAM": "/app/mdblist"}
        secrets.resolve_secrets(env, ["MDBLIST_API_KEY"], client=ssm)
        secrets.resolve_secrets(env, ["MDBLIST_API_KEY"], client=ssm)
        self.assertEqual(ssm.calls, 1)

    def test_missing_parameter_is_reported(self):
        class MissingSsm:
            def get_parameters(self, Names, WithDecryption):
                return {"Parameters": [], "InvalidParameters": Names}

        with self.assertRaisesRegex(RuntimeError, "/app/missing"):
            secrets.resolve_secrets({"TMDB_API_KEY_PARAM": "/app/missing"}, ["TMDB_API_KEY"], client=MissingSsm())


if __name__ == "__main__":
    unittest.main()
