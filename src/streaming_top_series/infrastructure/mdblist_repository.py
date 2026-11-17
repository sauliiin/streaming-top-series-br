"""MDBList adapter implementing the ListRepository port (static lists of shows or movies).

Endpoints (api.mdblist.com, `apikey` query parameter):
  GET  /lists/user                      user's lists
  POST /lists/user/add                  create a static list
  GET  /lists/{id}/items?unified=false  items, movies and shows split
  POST /lists/{id}/items/add|remove     {"shows" | "movies": [{"tmdb": 123}, ...]}
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any, Literal, Protocol

from ..application.ports import ListRef

MDBLIST_BASE_URL = "https://api.mdblist.com"
MDBLIST_WEB_URL = "https://mdblist.com"
MediaType = Literal["shows", "movies"]


class HttpClient(Protocol):
    def get(self, path: str, params: dict[str, Any] | None = None) -> Any: ...

    def post(self, path: str, payload: dict[str, Any]) -> Any: ...


def slugify(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")


def list_url(data: dict[str, Any]) -> str | None:
    user, slug = data.get("user_name"), data.get("slug")
    return f"{MDBLIST_WEB_URL}/lists/{user}/{slug}" if user and slug else None


def tmdb_id_of(item: dict[str, Any]) -> int | None:
    ids = item.get("ids") or {}
    value = ids.get("tmdb") or ids.get("tmdbid") or item.get("tmdb_id") or item.get("tmdb")
    try:
        return int(value) if value else None
    except (TypeError, ValueError):
        return None


class MdblistListRepository:
    def __init__(
        self, http: HttpClient, media_type: MediaType = "shows", *, batch_size: int = 100, page_size: int = 100
    ) -> None:
        self._http = http
        self._media_type = media_type
        self._batch_size = batch_size
        self._page_size = page_size

    def find_list(self, name: str) -> dict[str, Any] | None:
        slug = slugify(name)
        user_lists = self._http.get("/lists/user") or []
        matches = [
            lst
            for lst in user_lists
            if lst.get("slug") == slug or (lst.get("name") or "").casefold() == name.casefold()
        ]
        # Prefer the static list: dynamic lists reject items/add.
        matches.sort(key=lambda lst: lst.get("type") != "static")
        return matches[0] if matches else None

    def ensure_list(self, name: str, *, dry_run: bool) -> ListRef:
        existing = self.find_list(name)
        if existing:
            return ListRef(
                id=int(existing["id"]),
                name=existing.get("name") or name,
                slug=existing.get("slug") or "",
                url=list_url(existing),
            )
        if dry_run:
            return ListRef(id=None, name=name, slug=slugify(name), created=True)
        created = self._http.post("/lists/user/add", {"name": name, "private": False}) or {}
        if "id" not in created:
            # Some API versions only return a status payload; read the list back to get its id.
            created = self.find_list(name) or {}
        if "id" not in created:
            raise RuntimeError(f"MDBList did not return an id when creating list {name!r}")
        return ListRef(
            id=int(created["id"]),
            name=name,
            slug=created.get("slug") or slugify(name),
            created=True,
            url=list_url(created) or list_url(self.find_list(name) or {}),
        )

    def current_items(self, ref: ListRef) -> set[int]:
        ids: set[int] = set()
        offset = 0
        while True:
            data = self._http.get(
                f"/lists/{ref.id}/items",
                {"unified": "false", "limit": self._page_size, "offset": offset},
            )
            payload = data if isinstance(data, dict) else {}
            batch = payload.get(self._media_type) or []
            ids.update(i for i in map(tmdb_id_of, batch) if i is not None)
            page_len = max((len(v) for v in payload.values() if isinstance(v, list)), default=0)
            if page_len < self._page_size:
                return ids
            offset += self._page_size

    def add(self, ref: ListRef, tmdb_ids: Iterable[int]) -> None:
        self._send(ref, "add", tmdb_ids)

    def remove(self, ref: ListRef, tmdb_ids: Iterable[int]) -> None:
        self._send(ref, "remove", tmdb_ids)

    def _send(self, ref: ListRef, action: str, tmdb_ids: Iterable[int]) -> None:
        payload = [{"tmdb": i} for i in sorted(tmdb_ids)]
        for start in range(0, len(payload), self._batch_size):
            self._http.post(
                f"/lists/{ref.id}/items/{action}", {self._media_type: payload[start : start + self._batch_size]}
            )


class OfflineListRepository:
    """Local dry-run without MDBLIST_API_KEY: behaves as an empty, not-yet-created list."""

    def ensure_list(self, name: str, *, dry_run: bool) -> ListRef:
        return ListRef(id=None, name=name, slug=slugify(name), created=True)

    def current_items(self, ref: ListRef) -> set[int]:
        return set()

    def add(self, ref: ListRef, tmdb_ids: Iterable[int]) -> None:
        raise RuntimeError("OfflineListRepository only supports dry-run")

    def remove(self, ref: ListRef, tmdb_ids: Iterable[int]) -> None:
        raise RuntimeError("OfflineListRepository only supports dry-run")
