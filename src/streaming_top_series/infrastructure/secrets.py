"""Secret resolution: environment variables locally, SSM Parameter Store in AWS.

In Lambda the environment holds only the parameter NAME (e.g. TMDB_API_KEY_PARAM);
the SecureString value is fetched at runtime and cached for the container lifetime.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_cache: dict[str, str] = {}


def fetch_ssm_parameters(names: list[str], client: Any = None) -> dict[str, str]:
    missing = [n for n in names if n not in _cache]
    if missing:
        if client is None:
            import boto3

            client = boto3.client("ssm")
        response = client.get_parameters(Names=missing, WithDecryption=True)
        invalid = response.get("InvalidParameters") or []
        if invalid:
            raise RuntimeError(f"SSM parameters not found: {', '.join(invalid)}")
        for parameter in response.get("Parameters", []):
            _cache[parameter["Name"]] = parameter["Value"]
    return {n: _cache[n] for n in names}


def resolve_secrets(env: Mapping[str, str], names: list[str], client: Any = None) -> dict[str, str]:
    """For each NAME return env[NAME] or, when absent, the SSM parameter referenced by env[NAME_PARAM]."""
    values = {n: env[n] for n in names if env.get(n)}
    pending = {n: env[f"{n}_PARAM"] for n in names if n not in values and env.get(f"{n}_PARAM")}
    if pending:
        fetched = fetch_ssm_parameters(list(pending.values()), client)
        values.update({n: fetched[parameter] for n, parameter in pending.items()})
    return values


def clear_cache() -> None:
    _cache.clear()
