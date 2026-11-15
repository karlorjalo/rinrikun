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
        "defining_shows": engine.defining_shows(15),
        "tag_summary": engine.owned_tag_summary(20),
        "owned_count": len(engine.owned_idx),
        "total_count": len(engine.rows),
    }


@app.get("/api/similar")
def similar(id: str, k: int = Query(12, le=50, ge=1)):
    if id not in engine.by_id:
        raise HTTPException(404, "unknown id")
    return engine.similar_to(id, k=k)


@app.get("/api/recommend")
def recommend(k: int = Query(20, le=100, ge=1), seed: str | None = None):
    if seed and seed not in engine.by_id:
        raise HTTPException(404, "unknown seed")
    return engine.recommend(k=k, seed_id=seed)


@app.get("/api/shows")
def shows():
    return [{"id": r["id"], "title": r["title"], "title_native": r["title_native"],
             "owned": r["owned"]} for r in engine.rows]


@app.get("/")
def index():
    return FileResponse(ROOT / "ui" / "index.html")


app.mount("/ui", StaticFiles(directory=ROOT / "ui"), name="ui")

if __name__ == "__main__":
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8765
    threading.Timer(1.0, webbrowser.open, args=[f"http://localhost:{port}"]).start()
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=port)
