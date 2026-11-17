"""SnapshotStore adapters: daily audit trail of what entered and left each list."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _encode(document: dict[str, Any]) -> bytes:
    return json.dumps(document, ensure_ascii=False, indent=2, default=str).encode("utf-8")


class S3SnapshotStore:
    def __init__(self, bucket: str, prefix: str = "snapshots/", client: Any = None) -> None:
        if client is None:
            import boto3  # bundled with the Lambda runtime; lazy import keeps local runs dependency-free

            client = boto3.client("s3")
        self._client = client
        self._bucket = bucket
        self._prefix = prefix

    def save(self, key: str, document: dict[str, Any]) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=f"{self._prefix}{key}",
            Body=_encode(document),
            ContentType="application/json",
        )


class LocalSnapshotStore:
    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)

    def save(self, key: str, document: dict[str, Any]) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        (self._directory / key).write_bytes(_encode(document))


class NullSnapshotStore:
    def save(self, key: str, document: dict[str, Any]) -> None:
        return None
