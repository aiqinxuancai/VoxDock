"""VoxDock FastAPI application."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import APP_NAME, APP_VERSION, get_settings
from .db import dispose_db, init_db
from .providers import ProviderError
from .routers import providers, system, tts, voices
from .services.http import close_client

STATIC_DIR = Path(__file__).parent / "static"
log = logging.getLogger("voxdock")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()
    settings.resolved_secret()
    await init_db()
    if not settings.admin_password:
        log.warning("VOXDOCK_ADMIN_PASSWORD 未设置：Web 与 API 无需鉴权，请勿直接暴露到公网")
    yield
    await close_client()
    await dispose_db()


app = FastAPI(
    title=f"{APP_NAME} API",
    version=APP_VERSION,
    description=(
        "多平台声音克隆聚合服务：火山引擎 / 阿里云百炼（CosyVoice · 千问）/ MiniMax / 智谱。\n\n"
        "鉴权：`Authorization: Bearer <API Key>`（或 `X-API-Key` 头 / `?api_key=` 参数）。"
    ),
    lifespan=lifespan,
)


@app.exception_handler(ProviderError)
async def provider_error_handler(_: Request, exc: ProviderError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(httpx.TimeoutException)
async def timeout_handler(_: Request, exc: httpx.TimeoutException):
    return JSONResponse(status_code=504, content={"detail": f"请求平台超时：{exc.__class__.__name__}"})


@app.exception_handler(httpx.HTTPError)
async def http_error_handler(_: Request, exc: httpx.HTTPError):
    return JSONResponse(status_code=502, content={"detail": f"连接平台失败：{exc}"})


@app.middleware("http")
async def static_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/"):
        # ES modules are not fingerprinted; always revalidate (ETag makes this cheap)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable" if "/vendor/" in path else "no-cache"
    return response


app.include_router(system.router)
app.include_router(providers.router)
app.include_router(voices.router)
app.include_router(tts.router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/healthz", include_in_schema=False)
async def healthz():
    return {"status": "ok", "version": APP_VERSION}


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@app.exception_handler(404)
async def not_found(request: Request, exc: HTTPException):
    if request.url.path.startswith(("/api", "/v1", "/static")):
        return JSONResponse(status_code=404, content={"detail": getattr(exc, "detail", "Not Found")})
    return FileResponse(STATIC_DIR / "index.html")


def run() -> None:  # pragma: no cover
    import uvicorn

    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":  # pragma: no cover
    run()
