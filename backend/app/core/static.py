"""Serve the built SPA from the same origin as the API in the Docker runtime."""

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse


FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"


def frontend_response(path: str) -> FileResponse:
    # Never turn an unknown API URL into a successful HTML response.
    if path == "api" or path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")

    root = FRONTEND_DIST.resolve()
    candidate = (root / path).resolve()
    if not candidate.is_relative_to(root):
        raise HTTPException(status_code=404, detail="Not Found")
    if candidate.is_file():
        return FileResponse(candidate)
    if path and (path.startswith("assets/") or "." in Path(path).name):
        raise HTTPException(status_code=404, detail="Not Found")
    index = root / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="Not Found")
    return FileResponse(index)
