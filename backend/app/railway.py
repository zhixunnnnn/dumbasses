"""Railway entrypoint.

Railway runs one web process for this repo. The FastAPI app serves the API and,
after the Nixpacks build, the compiled Vite frontend from ``frontend/dist``.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .main import app

ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
ASSETS_DIR = FRONTEND_DIST / "assets"
INDEX_HTML = FRONTEND_DIST / "index.html"

if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


@app.get("/", include_in_schema=False)
def serve_index() -> FileResponse:
    if not INDEX_HTML.exists():
        raise HTTPException(status_code=503, detail="Frontend build not found.")
    return FileResponse(INDEX_HTML)


@app.get("/{path:path}", include_in_schema=False)
def serve_spa(path: str) -> FileResponse:
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found.")

    candidate = (FRONTEND_DIST / path).resolve()
    if (
        FRONTEND_DIST in candidate.parents
        and candidate.is_file()
        and candidate != INDEX_HTML
    ):
        return FileResponse(candidate)
    return serve_index()
