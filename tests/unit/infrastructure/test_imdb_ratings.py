import gzip
import io
import os
import tempfile
import time
import unittest
from pathlib import Path

from streaming_top_series.infrastructure.imdb_ratings import ImdbDatasetRatings

DATASET = b"tconst\taverageRating\tnumVotes\ntt0000001\t5.7\t2241\ntt0000002\t8.4\t330\n"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class ImdbDatasetRatingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.downloads = 0

    def tearDown(self):
        self.tmp.cleanup()

    def opener(self, request, timeout):
        self.downloads += 1
        return FakeResponse(gzip.compress(DATASET))

    def test_downloads_once_and_looks_up_requested_ids(self):
        ratings = ImdbDatasetRatings(self.tmp.name, opener=self.opener)
        self.assertEqual(ratings.lookup(["tt0000002", "tt9999999"]), {"tt0000002": (8.4, 330)})
        self.assertEqual(
            ratings.lookup(["tt0000001", "tt0000002"]), {"tt0000001": (5.7, 2241), "tt0000002": (8.4, 330)}
        )
        self.assertEqual(self.downloads, 1)

    def test_reuses_a_fresh_file_and_refreshes_a_stale_one(self):
        ImdbDatasetRatings(self.tmp.name, opener=self.opener).lookup(["tt0000001"])
        path = Path(self.tmp.name) / "title.ratings.tsv.gz"

        ImdbDatasetRatings(self.tmp.name, opener=self.opener).lookup(["tt0000001"])
        self.assertEqual(self.downloads, 1)

        old = time.time() - 48 * 3600
        os.utime(path, (old, old))
        ImdbDatasetRatings(self.tmp.name, opener=self.opener).lookup(["tt0000001"])
        self.assertEqual(self.downloads, 2)

    def test_failed_download_leaves_no_partial_file(self):
        def broken(request, timeout):
            raise TimeoutError("network down")

        with self.assertRaises(TimeoutError):
            ImdbDatasetRatings(self.tmp.name, opener=broken).lookup(["tt0000001"])
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
