import json
import tempfile
import unittest
from pathlib import Path

from streaming_top_series.infrastructure.snapshot_stores import LocalSnapshotStore, S3SnapshotStore


class SnapshotStoresTest(unittest.TestCase):
    def test_local_store_writes_utf8_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            LocalSnapshotStore(Path(tmp) / "nested").save("2026-11-17.json", {"name": "Séries"})
            content = (Path(tmp) / "nested" / "2026-11-17.json").read_text(encoding="utf-8")
        self.assertEqual(json.loads(content), {"name": "Séries"})

    def test_s3_store_puts_object_under_prefix(self):
        calls = []

        class FakeS3:
            def put_object(self, **kwargs):
                calls.append(kwargs)

        S3SnapshotStore("bucket", client=FakeS3()).save("2026-11-17.json", {"ok": True})
        self.assertEqual(calls[0]["Bucket"], "bucket")
        self.assertEqual(calls[0]["Key"], "snapshots/2026-11-17.json")
        self.assertEqual(json.loads(calls[0]["Body"]), {"ok": True})


if __name__ == "__main__":
    unittest.main()
