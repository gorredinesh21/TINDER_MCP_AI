"""Wingman AI — application entrypoint.

  Local (live Tinder allowed):   python app.py          -> http://127.0.0.1:8000
  Cloud Run (demo-only mode):    ENV=cloud uvicorn ...  -> binds $PORT, live calls refused
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from server.config import config
from server.errors import AppError
from server.routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

app = FastAPI(title=config.product_name, version=config.version, docs_url=None, redoc_url=None)
app.include_router(router)

WEB = Path(__file__).resolve().parent / "web"
app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "error", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logging.getLogger("wingman").error("unhandled: %s: %s", type(exc).__name__, str(exc)[:300])
    return JSONResponse(status_code=500, content={
        "error": {"code": "internal",
                  "message": "Something went wrong on our side. Try again — if it keeps happening, see Troubleshooting in Docs."}})


@app.get("/", include_in_schema=False)
def landing() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get("/guide", include_in_schema=False)
def guide() -> FileResponse:
    return FileResponse(WEB / "guide.html")


@app.get("/app", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(WEB / "app.html")


@app.get("/docs", include_in_schema=False)
def docs_page() -> FileResponse:
    return FileResponse(WEB / "docs.html")


if __name__ == "__main__":
    import uvicorn

    host = "127.0.0.1" if not config.is_cloud else os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    print(f"\n  {config.product_name}  ->  http://{host}:{port}   (mode: {'cloud demo' if config.is_cloud else 'local, live connections allowed'})\n")
    uvicorn.run(app, host=host, port=port, log_level="warning")
