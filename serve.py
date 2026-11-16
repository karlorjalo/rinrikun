import sys
import threading
import webbrowser

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from anime_vec.engine import Engine
from anime_vec.store import Store

ROOT = Path(__file__).resolve().parent
app = FastAPI()
store = Store(ROOT / "anime_vec.db")
engine = Engine(store)


@app.get("/api/profile")
def profile():
    return {
        "tier_summary": engine.tier_summary(),
        "owned_count": len(engine.owned_idx),
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


@app.get("/api/review-queue")
def review_queue(unrated_only: bool = False):
    return engine.review_queue(unrated_only=unrated_only)


@app.get("/api/ratings")
def get_ratings():
    return engine.rated_shows()


@app.get("/api/watched")
def get_watched():
    return engine.manual_shows()


@app.post("/api/watched")
def post_watched(payload: dict):
    show_id = payload.get("id")
    if not show_id or show_id not in engine.by_id:
        raise HTTPException(404, "unknown show id")
    watched = bool(payload.get("watched", True))
    engine.set_watched(show_id, watched)
    return {"id": show_id, "watched": watched, "owned": engine.by_id[show_id]["owned"]}


@app.get("/api/dismissed")
def get_dismissed():
    return engine.dismissed_shows()


@app.post("/api/dismissed")
def post_dismissed(payload: dict):
    show_id = payload.get("id")
    if not show_id or show_id not in engine.by_id:
        raise HTTPException(404, "unknown show id")
    dismissed = bool(payload.get("dismissed", True))
    engine.set_dismissed(show_id, dismissed)
    return {"id": show_id, "dismissed": dismissed}


@app.get("/api/similar")
def similar(id: str, k: int = Query(24, le=100, ge=1)):
    if id not in engine.by_id:
        raise HTTPException(404, "unknown id")
    return engine.similar_to(id, k=k)


@app.get("/api/show/{id:path}")
def show(id: str):
    if id not in engine.by_id:
        raise HTTPException(404, "unknown id")
    r = dict(engine.by_id[id])
    r.pop("text_hash", None)
    return r


@app.get("/api/recommend")
def recommend(
    k: int = Query(20, le=100, ge=1),
    seed: str | None = None,
    mode: str = Query("hybrid", pattern="^(hybrid|diverse)$"),
    new_only: bool = False,
):
    if seed and seed not in engine.by_id:
        raise HTTPException(404, "unknown seed")
    return engine.recommend(k=k, seed_id=seed, mode=mode, new_only=new_only)


@app.get("/api/shows")
def shows():
    return [{"id": r["id"], "title": r["title"], "title_native": r["title_native"],
             "year": r["year"], "poster": r["poster"], "owned": r["owned"],
             "manual_watched": r.get("manual_watched", 0),
             "tier": r.get("tier"), "weight": r.get("weight", 1.0)} for r in engine.rows]


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
