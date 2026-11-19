import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from anime_vec.pages import PageFiles, forward_page


class FakePageServer(BaseHTTPRequestHandler):
    """A page server for the tests: it answers by the path, and it keeps each request."""

    requests: list = []

    def do_GET(self):
        FakePageServer.requests.append((self.path, dict(self.headers)))
        if self.path.startswith("/next/old"):
            self.send_response(308)
            self.send_header("Location", "/next/new")
            self.end_headers()
            return
        if self.path.startswith("/next/missing"):
            self.send_response(404)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"not found page")
            return
        body = f"page {self.path}".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "public, max-age=31536000, immutable" if "/_app/immutable/" in self.path else "no-cache")
        self.send_header("ETag", '"abc"')
        self.send_header("X-Private", "not for the browser")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def client(tmp_path):
    """A server with the new page at /next (passed on to the fake page server) and an old page at /ui"""
    page_server = ThreadingHTTPServer(("127.0.0.1", 0), FakePageServer)
    threading.Thread(target=page_server.serve_forever, daemon=True).start()
    FakePageServer.requests = []
    address = f"http://127.0.0.1:{page_server.server_address[1]}"
    old = tmp_path / "ui"
    old.mkdir()
    (old / "app.js").write_text("// old code", encoding="utf-8")
    app = FastAPI()

    @app.get("/api/profile")
    def profile():
        return {"total_count": 3}

    @app.get("/next")
    @app.get("/next/{path:path}")
    def new_page(request: Request, path: str = ""):
        return forward_page(address, request.url.path, request.url.query, request.headers)

    app.mount("/ui", PageFiles(directory=old), name="ui")
    yield TestClient(app, follow_redirects=False)
    page_server.shutdown()


def test_a_tab_goes_to_the_page_server_with_its_query_and_its_cookies(client):
    res = client.get("/next/ratings?tier=A&sort=title", headers={"Cookie": "rinrikun-theme=dark"})
    assert res.status_code == 200 and res.text == "page /next/ratings?tier=A&sort=title"
    path, headers = FakePageServer.requests[-1]
    assert headers.get("Cookie") == "rinrikun-theme=dark"
    # This server compresses the answer: the page server must not
    assert headers.get("Accept-Encoding") == "identity"
    # The headers for the cache come back. A header that is not for the browser does not.
    assert res.headers["cache-control"] == "no-cache" and res.headers["etag"] == '"abc"'
    assert "x-private" not in res.headers
    assert client.get("/next").text == "page /next"


def test_a_file_with_a_hash_in_its_name_keeps_its_cache_header(client):
    res = client.get("/next/_app/immutable/start.abc123.js")
    assert res.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_a_redirect_and_an_error_of_the_page_server_go_back_to_the_browser(client):
    res = client.get("/next/old")
    assert res.status_code == 308 and res.headers["location"] == "/next/new"
    res = client.get("/next/missing")
    assert res.status_code == 404 and res.text == "not found page"


def test_a_page_server_that_does_not_run_gives_502():
    app = FastAPI()

    @app.get("/next/{path:path}")
    def new_page(request: Request, path: str = ""):
        # Port 9 (discard) has no server on a test computer
        return forward_page("http://127.0.0.1:9", request.url.path, request.url.query, request.headers)

    res = TestClient(app).get("/next/ratings")
    assert res.status_code == 502 and "does not run" in res.text


def test_the_new_page_does_not_take_the_other_addresses(client):
    assert client.get("/api/profile").json() == {"total_count": 3}
    res = client.get("/ui/app.js")
    assert res.status_code == 200 and res.headers["cache-control"] == "no-cache"
    assert client.get("/ui/missing.js").status_code == 404
