import io
import json
import stat
import tempfile
import unittest
from pathlib import Path

from streaming_top_series.infrastructure.site_stores import FEED_CACHE_CONTROL, LocalSiteStore, S3SiteStore


class FakeS3:
    class exceptions:  # noqa: N801 - mirrors boto3's client.exceptions namespace
        class NoSuchKey(Exception):  # noqa: N818 - boto3 name
            pass

    def __init__(self):
        self.objects = {}
        self.puts = []

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise self.exceptions.NoSuchKey()
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, **kwargs):
        self.puts.append(kwargs)
        self.objects[kwargs["Key"]] = kwargs["Body"]


class SiteStoresTest(unittest.TestCase):
    def test_s3_round_trip_with_cache_headers(self):
        s3 = FakeS3()
        store = S3SiteStore("site-bucket", client=s3)
        self.assertIsNone(store.load("movies.json"))

        store.publish("movies.json", {"title": "Séries"})
        self.assertEqual(store.load("movies.json"), {"title": "Séries"})
        put = s3.puts[0]
        self.assertEqual(put["Key"], "data/movies.json")
        self.assertEqual(put["CacheControl"], FEED_CACHE_CONTROL)
        self.assertTrue(put["ContentType"].startswith("application/json"))

    def test_local_store_writes_world_readable_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalSiteStore(Path(tmp) / "data")
            self.assertIsNone(store.load("series.json"))
            store.publish("series.json", {"ok": True})
            path = Path(tmp) / "data" / "series.json"
            self.assertEqual(json.loads(path.read_text()), {"ok": True})
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(store.load("series.json"), {"ok": True})


if __name__ == "__main__":
    unittest.main()
