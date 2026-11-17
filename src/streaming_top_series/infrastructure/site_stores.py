"""SiteStore adapters: where the website's JSON feeds are written."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

# Feeds change once a day; a short TTL keeps CloudFront and browsers fresh without invalidations.
FEED_CACHE_CONTROL = "public, max-age=300, stale-while-revalidate=3600"


def _encode(document: dict[str, Any]) -> bytes:
    return json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class S3SiteStore:
    def __init__(self, bucket: str, prefix: str = "data/", client: Any = None) -> None:
        if client is None:
            import boto3  # bundled with the Lambda runtime

            client = boto3.client("s3")
        self._client = client
        self._bucket = bucket
        self._prefix = prefix

    def load(self, name: str) -> dict[str, Any] | None:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=f"{self._prefix}{name}")
        except self._client.exceptions.NoSuchKey:
            return None
        loaded: dict[str, Any] = json.loads(response["Body"].read())
        return loaded

    def publish(self, name: str, document: dict[str, Any]) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=f"{self._prefix}{name}",
            Body=_encode(document),
            ContentType="application/json; charset=utf-8",
            CacheControl=FEED_CACHE_CONTROL,
        )


class LocalSiteStore:
    """Writes feeds next to the static site for local preview (python -m http.server -d web)."""

    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)

    def load(self, name: str) -> dict[str, Any] | None:
        path = self._directory / name
        if not path.exists():
            return None
        loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return loaded

    def publish(self, name: str, document: dict[str, Any]) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self._directory, suffix=".part")
        with os.fdopen(fd, "wb") as out:
            out.write(_encode(document))
        os.chmod(tmp, 0o644)  # public feed; mkstemp defaults to 0600
        os.replace(tmp, self._directory / name)
