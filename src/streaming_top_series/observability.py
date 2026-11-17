"""Structured logging: one JSON object per line, queryable with CloudWatch Logs Insights."""

from __future__ import annotations

import json
import sys
import time
from typing import Any, Protocol, TextIO


class Logger(Protocol):
    def __call__(self, event: str, level: str = "INFO", **fields: Any) -> None: ...


def json_logger(stream: TextIO | None = None, **context: Any) -> Logger:
    def log(event: str, level: str = "INFO", **fields: Any) -> None:
        record = {"ts": round(time.time(), 3), "level": level, "event": event, **context, **fields}
        out = stream or sys.stdout
        out.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        out.flush()

    return log


def null_logger(event: str, level: str = "INFO", **fields: Any) -> None:
    return None
