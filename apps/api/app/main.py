"""FastAPI 装配：/api 路由、/media 静态、单容器部署时托管前端 SPA。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import MEDIA_DIR, REPO_ROOT, ensure_dirs
from .db import init_db
from .routes import api_router
from .seeds import seed_all

logging.basicConfig(level=logging.INFO)

WEB_DIST = REPO_ROOT / "apps" / "web" / "dist"


class SPAStaticFiles(StaticFiles):
    """静态资源优先；前端路由（如 /problems/xxx）回落到 index.html。"""

    async def get_response(self, path: str, scope):
        if path == "api" or path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    init_db()
    seed_all()
    yield


app = FastAPI(
    title="Robustor API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8888",
        "http://127.0.0.1:8888",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ensure_dirs()
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")
app.include_router(api_router)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


# 前端构建产物存在时，同一个端口同时提供页面与接口（Docker 部署路径）。
if (WEB_DIST / "index.html").exists():
    app.mount("/", SPAStaticFiles(directory=str(WEB_DIST), html=True), name="web")
