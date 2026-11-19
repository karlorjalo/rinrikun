import json
import threading
import time
import urllib.request

import pytest

pytest.importorskip("fastapi")
uvicorn = pytest.importorskip("uvicorn")
from fastapi import FastAPI


def test_parse_address():
    import serve
    assert serve.parse_address("0.0.0.0:8771") == ("0.0.0.0", 8771)
    assert serve.parse_address("[::1]:8765") == ("::1", 8765)
    for text in ("8771", "localhost", "localhost:http", ":8771"):
        with pytest.raises(ValueError):
            serve.parse_address(text)


def test_one_server_process_has_one_state_for_two_addresses():
    import serve
    small = FastAPI()
    state = {"count": 0}

    @small.get("/count")
    def count():
        state["count"] += 1
        return state

    # Port 0 gives a free port
    sockets = [serve.listen("127.0.0.1", 0) for _ in range(2)]
    ports = [sock.getsockname()[1] for sock in sockets]
    assert ports[0] != ports[1]
    server = uvicorn.Server(uvicorn.Config(small, log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": sockets}, daemon=True)
    thread.start()
    try:
        limit = time.monotonic() + 20
        while not server.started and time.monotonic() < limit:
            time.sleep(0.05)
        assert server.started
        answers = []
        for port in ports:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/count", timeout=10) as res:
                answers.append(json.loads(res.read()))
        # The second address sees the change that came through the first address
        assert answers == [{"count": 1}, {"count": 2}]
    finally:
        server.should_exit = True
        thread.join(20)
    assert not thread.is_alive()


def test_the_browser_asks_again_for_the_files_of_the_page():
    from fastapi.testclient import TestClient
    import serve
    client = TestClient(serve.app)
    for path in ("/", "/ui/app.js", "/ui/styles.css"):
        res = client.get(path)
        assert res.status_code == 200 and res.headers["cache-control"] == "no-cache", path
    # A file that did not change gets a short answer, and this answer has the header too
    first = client.get("/ui/app.js")
    again = client.get("/ui/app.js", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304 and again.headers["cache-control"] == "no-cache"
