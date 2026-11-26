"""路由汇总。WP0 一次性 include 全部模块，后续 WP 不得修改本文件。"""

from fastapi import APIRouter

from . import ai_usage, documents, jobs, problems, regions, settings, stats, tags, taxonomy

api_router = APIRouter(prefix="/api")

for module in (documents, jobs, regions, problems, tags, stats, settings, taxonomy, ai_usage):
    api_router.include_router(module.router)

__all__ = ["api_router"]
