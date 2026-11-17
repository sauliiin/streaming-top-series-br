import unittest

from streaming_top_series.application import ListRef
from streaming_top_series.infrastructure.mdblist_repository import MdblistListRepository, slugify
from tests.support.fakes import FakeHttp

LIST_NAME = "Top 20 Séries Recentes · Netflix BR"
LIST_SLUG = "top-20-series-recentes-netflix-br"


class MdblistListRepositoryTest(unittest.TestCase):
    def test_prefers_existing_static_list(self):
        http = FakeHttp(
            {
                ("GET", "/lists/user"): [
                    {"id": 9, "name": LIST_NAME, "slug": LIST_SLUG, "type": "dynamic"},
                    {"id": 10, "name": LIST_NAME, "slug": LIST_SLUG, "type": "static"},
                ]
            }
        )
        ref = MdblistListRepository(http).ensure_list(LIST_NAME, dry_run=False)
        self.assertEqual((ref.id, ref.created), (10, False))

    def test_creates_public_list_when_missing(self):
        http = FakeHttp({("GET", "/lists/user"): [], ("POST", "/lists/user/add"): {"id": 77, "slug": "new"}})
        ref = MdblistListRepository(http).ensure_list("New", dry_run=False)
        self.assertEqual((ref.id, ref.created), (77, True))
        self.assertIn(("POST", "/lists/user/add", {"name": "New", "private": False}), http.calls)

    def test_dry_run_never_creates(self):
        http = FakeHttp({("GET", "/lists/user"): []})
        ref = MdblistListRepository(http).ensure_list("New", dry_run=True)
        self.assertIsNone(ref.id)
        self.assertFalse([c for c in http.calls if c[0] == "POST"])

    def test_reads_only_shows_across_pages(self):
        page1 = {"movies": [{"ids": {"tmdb": 999}}], "shows": [{"ids": {"tmdb": i}} for i in (1, 2)]}
        page2 = {"shows": [{"tmdb_id": 3}]}
        http = FakeHttp({("GET", "/lists/5/items"): lambda p: page1 if p["offset"] == 0 else page2})
        self.assertEqual(MdblistListRepository(http, page_size=2).current_items(ListRef(5, "x")), {1, 2, 3})

    def test_add_and_remove_send_shows_payload_in_batches(self):
        http = FakeHttp({})
        repository = MdblistListRepository(http, batch_size=2)
        repository.add(ListRef(5, "x"), [3, 1, 2])
        repository.remove(ListRef(5, "x"), [9])
        self.assertEqual(
            http.calls,
            [
                ("POST", "/lists/5/items/add", {"shows": [{"tmdb": 1}, {"tmdb": 2}]}),
                ("POST", "/lists/5/items/add", {"shows": [{"tmdb": 3}]}),
                ("POST", "/lists/5/items/remove", {"shows": [{"tmdb": 9}]}),
            ],
        )

    def test_movie_repository_reads_and_writes_movies(self):
        page = {"movies": [{"ids": {"tmdb": 7}}], "shows": [{"ids": {"tmdb": 8}}]}
        http = FakeHttp({("GET", "/lists/5/items"): page})
        repository = MdblistListRepository(http, "movies")
        self.assertEqual(repository.current_items(ListRef(5, "StreammyMovies")), {7})
        repository.add(ListRef(5, "StreammyMovies"), [1])
        self.assertEqual(http.calls[-1], ("POST", "/lists/5/items/add", {"movies": [{"tmdb": 1}]}))

    def test_slugify_strips_accents_and_symbols(self):
        self.assertEqual(slugify(LIST_NAME), LIST_SLUG)


if __name__ == "__main__":
    unittest.main()
