import io
import json
import unittest
from unittest import mock

from streaming_top_series.bootstrap import Services
from streaming_top_series.entrypoints import cli
from tests.support.fakes import (
    FakeCatalog,
    FakeMovieCatalog,
    make_movie,
    make_shows,
    movie_service,
    series_service,
)


def fake_builder(catalog, movie_catalog):
    def build(settings, env, *, dry_run, log):
        return Services(
            series=series_service(catalog, criteria=settings.criteria),
            movies=movie_service(movie_catalog, criteria=settings.movie_criteria),
        )

    return build


class CliTest(unittest.TestCase):
    def run_cli(self, argv, catalog=None, movie_catalog=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        builder = fake_builder(catalog or FakeCatalog(), movie_catalog or FakeMovieCatalog())
        with (
            mock.patch.object(cli, "build_services", builder),
            mock.patch.dict("os.environ", {}, clear=True),
            mock.patch("sys.stdout", stdout),
            mock.patch("sys.stderr", stderr),
        ):
            code = cli.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_human_readable_output_for_both_jobs(self):
        code, out, _ = self.run_cli(
            ["--dry-run", "--providers", "netflix"],
            FakeCatalog({"netflix": make_shows([1])}),
            FakeMovieCatalog({"netflix": [make_movie(7)]}),
        )
        self.assertEqual(code, 0)
        for expected in ("StreammySeries", "Show 1", "StreammyMovies", "Movie 7", "JustWatch"):
            self.assertIn(expected, out)

    def test_json_output_and_failure_exit_code(self):
        code, out, err = self.run_cli(["--job", "series", "--json", "--providers", "hbo"], FakeCatalog(failing={"hbo"}))
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["series"]["providers"][0]["status"], "error")
        self.assertIn("series:hbo", err)

    def test_configuration_error_exit_code(self):
        def broken(*args, **kwargs):
            raise cli.ConfigurationError("missing key")

        stderr = io.StringIO()
        with mock.patch.object(cli, "build_services", broken), mock.patch("sys.stderr", stderr):
            self.assertEqual(cli.main([]), 2)
        self.assertIn("missing key", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
