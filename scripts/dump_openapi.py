"""导出 OpenAPI 到 apps/api/openapi.json，供前端生成类型。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))

from app.main import app  # noqa: E402

out = REPO / "apps" / "api" / "openapi.json"
out.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
print(f"wrote {out}")
