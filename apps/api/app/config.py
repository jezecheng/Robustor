"""运行期配置：路径与 provider 开关。全部可被环境变量覆盖，便于测试隔离。"""

from __future__ import annotations

import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent          # apps/api/app
API_DIR = APP_DIR.parent                           # apps/api
REPO_ROOT = API_DIR.parents[1]                     # Robustor

DATA_DIR = Path(os.environ.get("RB_DATA_DIR", REPO_ROOT / "data")).resolve()
MEDIA_DIR = DATA_DIR / "media"
UPLOAD_DIR = MEDIA_DIR / "uploads"
PAGE_DIR = MEDIA_DIR / "pages"
CROP_DIR = MEDIA_DIR / "crops"
DEBUG_DIR = DATA_DIR / "debug"
DB_PATH = Path(os.environ.get("RB_DB_PATH", DATA_DIR / "app.db")).resolve()

FIXTURE_DIR = APP_DIR / "fixtures"
FIXTURE_DEMO_DIR = FIXTURE_DIR / "demo"
CANNED_PATH = FIXTURE_DIR / "canned.json"

MAX_EDGE = int(os.environ.get("RB_MAX_EDGE", "2000"))

# 默认对外端口（容器与生产一致；dev 模式下 vite 代理也指向它）
APP_PORT = int(os.environ.get("RB_PORT", "8888"))

LAYOUT_PROVIDER = os.environ.get("LAYOUT_PROVIDER", "mock")
OCR_PROVIDER = os.environ.get("OCR_PROVIDER", "mock")

PAGE_STATUS = ("pending", "ready", "failed")


def ensure_dirs() -> None:
    for path in (DATA_DIR, MEDIA_DIR, UPLOAD_DIR, PAGE_DIR, CROP_DIR, DEBUG_DIR):
        path.mkdir(parents=True, exist_ok=True)
