"""Minimal JSON-over-HTTP client (stdlib only) with exponential backoff.

No third-party dependencies, so the Lambda artifact is just the source tree.
API keys travel in the query string, therefore the full URL is NEVER included
in exceptions or logs - only the method and path.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
MAX_BACKOFF_SECONDS = 30.0


class HttpError(RuntimeError):
    def __init__(self, method: str, path: str, status: int | None, detail: str) -> None:
        super().__init__(f"{method} {path} failed (status={status}): {detail}")
        self.status = status


class JsonHttpClient:
    def __init__(
        self,
        base_url: str,
        *,
        default_params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
        max_retries: int = 4,
        backoff: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_params = dict(default_params or {})
        self._headers = {"Accept": "application/json", "User-Agent": "streaming-top-series/0.2", **(headers or {})}
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff = backoff
        self._sleep = sleep
        self._opener = opener

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self.request("GET", path, params=params)

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        return self.request("POST", path, payload=payload)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        query = urllib.parse.urlencode({**self._default_params, **(params or {})}, doseq=True)
        url = f"{self._base_url}{path}" + (f"?{query}" if query else "")
        headers = dict(self._headers)
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        delay = self._backoff
        for attempt in range(self._max_retries + 1):
            request = urllib.request.Request(url, data=body, headers=headers, method=method)
            try:
                with self._opener(request, timeout=self._timeout) as response:
                    raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else None
            except urllib.error.HTTPError as exc:
                with exc:
                    detail = exc.read().decode("utf-8", errors="replace")[:300]
                if exc.code in RETRYABLE_STATUS and attempt < self._max_retries:
                    self._sleep(delay)
                    delay = min(delay * 2, MAX_BACKOFF_SECONDS)
                    continue
                raise HttpError(method, path, exc.code, detail) from None
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt < self._max_retries:
                    self._sleep(delay)
                    delay = min(delay * 2, MAX_BACKOFF_SECONDS)
                    continue
                reason = getattr(exc, "reason", exc)
                raise HttpError(method, path, None, f"{type(exc).__name__}: {reason}") from None
            except json.JSONDecodeError:
                raise HttpError(method, path, None, "response is not valid JSON") from None
        raise AssertionError("unreachable")
