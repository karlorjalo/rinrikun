import datetime
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

from anime_vec.engine import Engine
from anime_vec.store import Store

ROOT = Path(__file__).resolve().parent
app = FastAPI()
# The map data of the full catalog is about 8 MB. It is about 5 times smaller when compressed.
app.add_middleware(GZipMiddleware, minimum_size=2000)
store = Store(ROOT / "anime_vec.db")
engine = Engine(store)


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
    return engine.set_show_tier(show_id, tier)


@app.delete("/api/weights")
def delete_weights(id: str = Query(...)):
    if not id or id not in engine.by_id:
        raise HTTPException(404, "unknown show id")
    return engine.set_show_tier(id, None)


# The formula of the match of a show: see Engine.match_percent
KINDS = Query("all", pattern="^(all|usual)$")


@app.get("/api/review-queue")
def review_queue(unrated_only: bool = False, kinds: str = KINDS):
    return engine.review_queue(unrated_only=unrated_only, kinds=kinds)


@app.get("/api/ratings")
def get_ratings(kinds: str = KINDS):
    return engine.rated_shows(kinds=kinds)


@app.get("/api/watched")
def get_watched(kinds: str = KINDS):
    return engine.with_match(engine.manual_shows(), kinds)


@app.post("/api/watched")
def post_watched(payload: dict):
    show_id = payload.get("id")
    if not show_id or show_id not in engine.by_id:
        raise HTTPException(404, "unknown show id")
    watched = bool(payload.get("watched", True))
    engine.set_watched(show_id, watched)
    return {"id": show_id, "watched": watched, "owned": engine.by_id[show_id]["owned"]}


@app.get("/api/dismissed")
def get_dismissed(kinds: str = KINDS):
    return engine.with_match(engine.dismissed_shows(), kinds)


@app.post("/api/dismissed")
def post_dismissed(payload: dict):
    show_id = payload.get("id")
    if not show_id or show_id not in engine.by_id:
        raise HTTPException(404, "unknown show id")
    dismissed = bool(payload.get("dismissed", True))
    engine.set_dismissed(show_id, dismissed)
    return {"id": show_id, "dismissed": dismissed}


@app.get("/api/similar")
def similar(id: str, k: int = Query(24, le=100, ge=1), kinds: str = KINDS):
    if id not in engine.by_id:
        raise HTTPException(404, "unknown id")
    return engine.with_match(engine.similar_to(id, k=k), kinds)


@app.get("/api/show/{id:path}")
def show(id: str, kinds: str = KINDS):
    if id not in engine.by_id:
        raise HTTPException(404, "unknown id")
    return engine.with_match([engine.public_row(engine.pos[id])], kinds)[0]


@app.get("/api/recommend")
def recommend(
    k: int = Query(20, le=100, ge=1),
    seed: str | None = None,
    mode: str = Query("hybrid", pattern="^(hybrid|diverse)$"),
    new_only: bool = False,
    kinds: str = Query("all", pattern="^(all|usual)$"),
):
    if seed and seed not in engine.by_id:
        raise HTTPException(404, "unknown seed")
    results = engine.recommend(k=k, seed_id=seed, mode=mode, new_only=new_only, kinds=kinds)
    if not seed:
        # The log of the results: the shows of new franchises that the list gave, with their places
        store.log_recommendations([(r["id"], place) for place, r in enumerate(results) if not r.get("franchise_owned")],
                                  kinds, datetime.date.today().isoformat())
    return engine.with_match(results, kinds)


@app.get("/api/rec-log")
def rec_log():
    """Return what the user did with the shows that the lists of recommendations gave."""
    return engine.recommendation_results()


@app.get("/api/shows")
def shows():
    return [{"id": r["id"], "title": r["title"], "title_native": r["title_native"],
             "year": r["year"], "poster": engine.poster_of(i), "owned": r["owned"],
             "manual_watched": r.get("manual_watched", 0),
             "tier": r.get("tier"), "weight": r.get("weight", 1.0)} for i, r in enumerate(engine.rows)]


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

if __name__ == "__main__":
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8765
    # The default host accepts connections only from this computer. The API has no login.
    host = sys.argv[sys.argv.index("--host") + 1] if "--host" in sys.argv else "127.0.0.1"
    threading.Timer(1.0, webbrowser.open, args=[f"http://localhost:{port}"]).start()
    import uvicorn
    uvicorn.run(app, host=host, port=port)
