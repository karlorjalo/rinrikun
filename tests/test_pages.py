import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from anime_vec.pages import NewPage, PageFiles


@pytest.fixture
def client(tmp_path):
    """A server with a small copy of the build of the new page at /next, and an old page at /ui."""
    build = tmp_path / "build"
    (build / "_app" / "immutable").mkdir(parents=True)
    (build / "index.html").write_text("<!doctype html><title>the new page</title>", encoding="utf-8")
    (build / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (build / "_app" / "immutable" / "start.abc123.js").write_text("// code", encoding="utf-8")
    (build / "_app" / "version.json").write_text("{}", encoding="utf-8")
    old = tmp_path / "ui"
    old.mkdir()
    (old / "app.js").write_text("// old code", encoding="utf-8")
    app = FastAPI()

    @app.get("/api/profile")
    def profile():
        return {"total_count": 3}

    app.mount("/next", NewPage(directory=build), name="next")
    app.mount("/ui", PageFiles(directory=old), name="ui")
    return TestClient(app)


def test_the_address_of_a_tab_gives_the_page(client):
    for path in ("/next/", "/next/ratings", "/next/recommendations", "/next/a/deeper/address"):
        res = client.get(path)
        assert res.status_code == 200 and "the new page" in res.text, path
        # The browser asks again for the page file each time: a new build changes it
        assert res.headers["cache-control"] == "no-cache", path


def test_a_file_with_a_hash_in_its_name_stays_in_the_browser(client):
    res = client.get("/next/_app/immutable/start.abc123.js")
    assert res.status_code == 200 and res.text == "// code"
    assert res.headers["cache-control"] == "public, max-age=31536000, immutable"
    # The other files of the build have no hash in their names
    for path in ("/next/favicon.svg", "/next/_app/version.json"):
        res = client.get(path)
        assert res.status_code == 200 and res.headers["cache-control"] == "no-cache", path


def test_a_missing_file_is_not_the_page(client):
    # After a new build an old page can ask for a file that is not there. The answer must be an
    # error: the page file as the answer would be code that the browser cannot run.
    for path in ("/next/_app/immutable/old.ffff.js", "/next/missing.css"):
        res = client.get(path)
        assert res.status_code == 404, path
        assert "immutable" not in res.headers.get("cache-control", ""), path


def test_the_new_page_does_not_take_the_other_addresses(client):
    assert client.get("/api/profile").json() == {"total_count": 3}
    res = client.get("/ui/app.js")
    assert res.status_code == 200 and res.headers["cache-control"] == "no-cache"
    assert client.get("/ui/missing.js").status_code == 404
