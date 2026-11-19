import datetime
import os
import socket
import sys
import threading
import urllib.request
import webbrowser

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from anime_vec import frames
from anime_vec.engine import Engine
from anime_vec.store import Store

ROOT = Path(__file__).resolve().parent
app = FastAPI()
# The map data of the full catalog is about 8 MB. It is about 5 times smaller when compressed.
app.add_middleware(GZipMiddleware, minimum_size=2000)
store = Store(ROOT / "anime_vec.db")
engine = Engine(store)
# The largest number of shows in one request for pictures
FRAMES_MAX = 50


@app.get("/api/profile")
def profile():
    return {
        "tier_summary": engine.tier_summary(),
        "owned_count": len(engine.owned_idx),
        # The shows of the user that are in the Jellyfin library. The other shows of the user are
        # the shows that the user marked as watched by hand.
        "library_count": sum(1 for i in engine.owned_idx if engine.rows[i]["source"] == "library"),
        "manual_count": len(store.get_manual_watched_ids()),
        "total_count": len(engine.rows),
    }


@app.get("/api/vector-map")
def vector_map():
    return engine.get_vector_map()


@app.get("/api/weights")
def get_weights():
    return store.get_weights()


@app.post("/api/weights")
def post_weights(payload: dict):
    show_id = payload.get("id")
    if not show_id or show_id not in engine.by_id:
        raise HTTPException(404, "unknown show id")
    tier = payload.get("tier")
    with engine.lock:
        return engine.set_show_tier(show_id, tier)


@app.delete("/api/weights")
def delete_weights(id: str = Query(...)):
    if not id or id not in engine.by_id:
        raise HTTPException(404, "unknown show id")
    with engine.lock:
        return engine.set_show_tier(id, None)


# The formula of a list of recommendations: see Engine.recommend
KINDS = Query("all", pattern="^(all|usual)$")
# False gives the formula without the crowd links: the recommendations of AniList users
LINKS = Query(True)


@app.get("/api/vector-map/match")
def vector_map_match():
    """Return the match of each point of the map, in the order of the points of /api/vector-map."""
    return engine.map_match()


@app.get("/api/review-queue")
def review_queue(unrated_only: bool = False):
    return engine.review_queue(unrated_only=unrated_only)


@app.get("/api/ratings")
def get_ratings():
    return engine.rated_shows()


@app.get("/api/watched")
def get_watched():
    return engine.with_match(engine.manual_shows())


@app.post("/api/watched")
def post_watched(payload: dict):
    show_id = payload.get("id")
    if not show_id or show_id not in engine.by_id:
        raise HTTPException(404, "unknown show id")
    watched = bool(payload.get("watched", True))
    with engine.lock:
        engine.set_watched(show_id, watched)
    return {"id": show_id, "watched": watched, "owned": engine.by_id[show_id]["owned"]}


@app.get("/api/dismissed")
def get_dismissed():
    return engine.with_match(engine.dismissed_shows())


@app.post("/api/dismissed")
def post_dismissed(payload: dict):
    show_id = payload.get("id")
    if not show_id or show_id not in engine.by_id:
        raise HTTPException(404, "unknown show id")
    dismissed = bool(payload.get("dismissed", True))
    with engine.lock:
        engine.set_dismissed(show_id, dismissed)
    return {"id": show_id, "dismissed": dismissed}


@app.get("/api/discover")
def discover(count: int = Query(12, le=50, ge=1)):
    """Return random shows for the Discover deck, and the numbers of the answers of the user."""
    return {"cards": engine.discover(count), "counts": engine.interest_counts()}


@app.get("/api/interest")
def get_interest():
    """Return the shows that the user is interested in: the watch list."""
    return engine.interest_shows()


@app.post("/api/interest")
def post_interest(payload: dict):
    """Record the answer of the user for a show: true = interested, false = not interested, null = no answer."""
    show_id = payload.get("id")
    if not show_id or show_id not in engine.by_id:
        raise HTTPException(404, "unknown show id")
    value = payload.get("value")
    source = "deck" if payload.get("source") == "deck" else "page"
    with engine.lock:
        try:
            engine.set_interest(show_id, None if value is None else bool(value), source)
        except ValueError as error:
            raise HTTPException(400, str(error))
    row = engine.by_id[show_id]
    return {"id": show_id, "interest": row.get("interest"), "dismissed": row.get("dismissed", 0),
            "counts": engine.interest_counts()}


@app.get("/api/interest/results")
def interest_results():
    """Return the answers of the Discover deck by the match of the shows."""
    return engine.interest_results()


@app.get("/api/frames")
def get_frames(ids: str = Query(..., max_length=2000)):
    """Return pictures of some shows, by the id of the show: frames of the episodes and of the trailer.

    `ids` has the ids of the shows, with a comma between two ids. The server asks AniList for
    the pictures of a show one time, and keeps the answer in a file: see anime_vec/frames.py.
    A show is not in the result if it has no AniList entry, or if AniList gave no answer.
    """
    wanted: dict[str, int] = {}
    for show_id in ids.split(","):
        if show_id in engine.by_id:
            anilist_id = engine.public_row(engine.pos[show_id]).get("anilist_id")
            if anilist_id is not None:
                wanted[show_id] = int(anilist_id)
    if len(wanted) > FRAMES_MAX:
        raise HTTPException(400, f"too many shows: the limit is {FRAMES_MAX}")
    found = frames.get_pictures(wanted.values()) if wanted else {}
    return {show_id: found[i] for show_id, i in wanted.items() if i in found}


@app.get("/api/similar")
def similar(id: str, k: int = Query(24, le=100, ge=1)):
    if id not in engine.by_id:
        raise HTTPException(404, "unknown id")
    return engine.with_match(engine.similar_to(id, k=k))


@app.get("/api/show/{id:path}")
def show(id: str):
    if id not in engine.by_id:
        raise HTTPException(404, "unknown id")
    return engine.with_match([engine.public_row(engine.pos[id])])[0]


@app.get("/api/recommend")
def recommend(
    k: int = Query(20, le=100, ge=1),
    seed: str | None = None,
    mode: str = Query("hybrid", pattern="^(hybrid|diverse)$"),
    new_only: bool = False,
    kinds: str = KINDS,
    links: bool = LINKS,
):
    if seed and seed not in engine.by_id:
        raise HTTPException(404, "unknown seed")
    results = engine.recommend(k=k, seed_id=seed, mode=mode, new_only=new_only, kinds=kinds, links=links)
    if not seed:
        # The log of the results: the shows of new franchises that the list gave, with their places.
        # The log also keeps the formula, thus it can compare the lists with and without the crowd links.
        store.log_recommendations([(r["id"], place) for place, r in enumerate(results) if not r.get("franchise_owned")],
                                  kinds if links else f"{kinds}, no links", datetime.date.today().isoformat())
    return engine.with_match(results)


@app.get("/api/recommend/steps")
def recommend_steps(k: int = Query(40, le=100, ge=1), new_only: bool = True, kinds: str = KINDS, links: bool = LINKS):
    """Return the steps from the catalog to the list, for the animation of the Recommendations map."""
    return engine.recommendation_steps(k=k, kinds=kinds, links=links, new_only=new_only)


@app.get("/api/rec-log")
def rec_log():
    """Return what the user did with the shows that the lists of recommendations gave."""
    return engine.recommendation_results()


@app.get("/api/shows")
def shows():
    return [{"id": r["id"], "title": r["title"], "title_native": r["title_native"],
             "year": r["year"], "poster": engine.poster_of(i), "owned": r["owned"],
             "manual_watched": r.get("manual_watched", 0),
             "tier": r.get("tier"), "weight": r.get("weight", 1.0),
             # The other titles of the show, for the search
             "aka": engine.other_titles(i)} for i, r in enumerate(engine.rows)]


@app.get("/api/poster/{id:path}")
def poster(id: str):
    """Pass the poster of a library show on from Jellyfin.

    The address of a poster of the library is on the Jellyfin server. A browser on a different
    computer frequently cannot reach that server, but this server can. Only a library show
    without an AniList entry uses this address: the other shows use the poster from AniList.
    """
    r = engine.by_id.get(id)
    if r is None or r.get("source") != "library" or not r.get("poster"):
        raise HTTPException(404, "no poster")
    # A poster in the interface is small, thus ask Jellyfin for a small picture
    url = r["poster"] + ("&" if "?" in r["poster"] else "?") + "maxWidth=400&quality=90"
    try:
        with urllib.request.urlopen(url, timeout=15) as res:
            data, media_type = res.read(), res.headers.get_content_type()
    except Exception:
        raise HTTPException(502, "the library server did not give the poster")
    return Response(content=data, media_type=media_type, headers={"Cache-Control": "max-age=86400"})


@app.get("/favicon.ico")
def favicon():
    return FileResponse(ROOT / "ui" / "favicon.svg")


@app.get("/")
def index():
    return FileResponse(ROOT / "ui" / "index.html")


app.mount("/ui", StaticFiles(directory=ROOT / "ui"), name="ui")


def parse_address(text: str) -> tuple[str, int]:
    """Return the host and the port of an address in the form "host:port"."""
    host, _, port = text.rpartition(":")
    if not host or not port.isdigit():
        raise ValueError(f"{text!r} is not an address. Use host:port, for example 0.0.0.0:8771")
    return host.strip("[]"), int(port)


def listen(host: str, port: int) -> socket.socket:
    """Return a socket that is bound to the address. Port 0 gives a free port."""
    sock = socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET)
    if os.name != "nt":
        # A new server can use the address immediately after the old server stopped. Windows
        # permits this without the option. With the option, Windows also permits a second
        # process on the same address at the same time.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    return sock


def run_server(addresses: list[tuple[str, int]]):
    """Serve the interface on each address, in this one process.

    The engine keeps the data of the user in memory, and it reads the database only when it
    starts. Thus two server processes do not agree after the user changed a tier or gave an
    answer through one of them. One process with two addresses has one engine.
    """
    import uvicorn
    sockets = [listen(host, port) for host, port in addresses]
    uvicorn.Server(uvicorn.Config(app)).run(sockets=sockets)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Serve the rinrikun interface.")
    # The default host accepts connections only from this computer. The API has no login.
    parser.add_argument("--host", default="127.0.0.1", help="the address of the server (default: only this computer)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--also", action="append", default=[], metavar="HOST:PORT",
                        help="one more address for the same server process, for example 0.0.0.0:8771. "
                             "You can give this option more than one time.")
    parser.add_argument("--no-browser", action="store_true", help="do not open the page in a browser")
    args = parser.parse_args()
    try:
        addresses = [(args.host, args.port)] + [parse_address(text) for text in args.also]
    except ValueError as error:
        parser.error(str(error))
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, args=[f"http://localhost:{args.port}"]).start()
    run_server(addresses)
