import io
import unittest
import urllib.error

from streaming_top_series.infrastructure.http_client import HttpError, JsonHttpClient

SECRET = "s3cr3t-api-key"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def http_error(url, code, body):
    return urllib.error.HTTPError(url, code, "error", {}, io.BytesIO(body))


def client_with(opener):
    return JsonHttpClient("https://api.example", default_params={"apikey": SECRET}, opener=opener, sleep=lambda s: None)


class JsonHttpClientTest(unittest.TestCase):
    def test_retries_on_rate_limit_then_succeeds(self):
        attempts = []

        def opener(request, timeout):
            attempts.append(request.full_url)
            if len(attempts) == 1:
                raise http_error(request.full_url, 429, b"slow down")
            return FakeResponse(b'{"ok": true}')

        self.assertEqual(client_with(opener).get("/x"), {"ok": True})
        self.assertEqual(len(attempts), 2)

    def test_does_not_retry_client_errors(self):
        attempts = []

        def opener(request, timeout):
            attempts.append(1)
            raise http_error(request.full_url, 404, b"not found")

        with self.assertRaises(HttpError) as ctx:
            client_with(opener).get("/missing")
        self.assertEqual((ctx.exception.status, len(attempts)), (404, 1))

    def test_errors_never_leak_the_api_key(self):
        def opener(request, timeout):
            raise http_error(request.full_url, 401, b"invalid key")

        with self.assertRaises(HttpError) as ctx:
            client_with(opener).get("/lists/user")
        self.assertNotIn(SECRET, str(ctx.exception))
        self.assertIsNone(ctx.exception.__cause__)
        self.assertTrue(ctx.exception.__suppress_context__)

    def test_observer_reports_retries_and_slow_requests_without_secrets(self):
        events = []
        ticks = iter([0.0, 10.0, 17.5])  # 1st attempt fails (HTTP 503), 2nd succeeds after 7.5 s

        def opener(request, timeout):
            if len(events) == 0:
                raise http_error(request.full_url, 503, b"busy")
            return FakeResponse(b"{}")

        client = JsonHttpClient(
            "https://api.example",
            default_params={"apikey": SECRET},
            opener=opener,
            sleep=lambda s: None,
            clock=lambda: next(ticks),
            observer=lambda *event: events.append(event),
        )
        client.get("/lists/user")
        self.assertEqual([e[0] for e in events], ["http_retry", "http_slow"])
        self.assertEqual(events[0][3]["status"], 503)
        self.assertEqual(events[1][3]["seconds"], 7.5)
        self.assertNotIn(SECRET, repr(events))


if __name__ == "__main__":
    unittest.main()
