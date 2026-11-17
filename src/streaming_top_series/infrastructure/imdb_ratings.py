"""IMDb ratings adapter (RatingsProvider) backed by the official IMDb datasets.

https://datasets.imdbws.com/title.ratings.tsv.gz (about 9 MB, refreshed daily, no API key;
personal and non-commercial use). The file is cached on disk (Lambda: /tmp) and
re-downloaded when older than `max_age_hours`. Lookups stream the gzip once per batch
of unseen ids and keep only the requested rows in memory.
"""

from __future__ import annotations

import gzip
import os
import tempfile
import threading
import time
import urllib.request
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

IMDB_RATINGS_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"


class ImdbDatasetRatings:
    def __init__(
        self,
        cache_dir: str | Path,
        *,
        url: str = IMDB_RATINGS_URL,
        max_age_hours: float = 20,
        timeout: float = 60,
        opener: Callable[..., Any] = urllib.request.urlopen,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._path = Path(cache_dir) / "title.ratings.tsv.gz"
        self._url = url
        self._max_age = max_age_hours * 3600
        self._timeout = timeout
        self._opener = opener
        self._clock = clock
        self._known: dict[str, tuple[float, int] | None] = {}
        self._lock = threading.Lock()

    def lookup(self, imdb_ids: Iterable[str]) -> dict[str, tuple[float, int]]:
        wanted = {i for i in imdb_ids if i}
        with self._lock:
            missing = wanted - self._known.keys()
            if missing:
                self._scan(missing)
            return {i: r for i in wanted if (r := self._known.get(i)) is not None}

    def _scan(self, missing: set[str]) -> None:
        found: dict[str, tuple[float, int]] = {}
        with gzip.open(self._dataset(), "rt", encoding="utf-8") as rows:
            next(rows, None)  # header: tconst, averageRating, numVotes
            for line in rows:
                tconst, _, rest = line.partition("\t")
                if tconst in missing:
                    average, votes = rest.rstrip("\n").split("\t")
                    found[tconst] = (float(average), int(votes))
        for imdb_id in missing:
            self._known[imdb_id] = found.get(imdb_id)

    def _dataset(self) -> Path:
        fresh = self._path.exists() and self._clock() - self._path.stat().st_mtime < self._max_age
        if not fresh:
            self._download()
        return self._path

    def _download(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(self._url, headers={"User-Agent": "streaming-top-series/0.2"})
        fd, tmp_name = tempfile.mkstemp(dir=self._path.parent, suffix=".part")
        try:
            with os.fdopen(fd, "wb") as out, self._opener(request, timeout=self._timeout) as response:
                while chunk := response.read(1 << 20):
                    out.write(chunk)
            os.replace(tmp_name, self._path)  # atomic: readers never see a partial file
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
