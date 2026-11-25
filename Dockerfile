# syntax=docker/dockerfile:1
# 单镜像部署：前端 dist 由 FastAPI 托管，一个端口（默认 8888）同时提供页面、/api 与 /media。

# ---------- 1. 构建前端 ----------
FROM node:20-alpine AS web
WORKDIR /build
COPY apps/web/package.json apps/web/package-lock.json ./
# 国内构建走 npmmirror，避免从 registry.npmjs.org 拉包超时
RUN npm config set registry https://registry.npmmirror.com && npm ci --ignore-scripts
COPY apps/web/ ./
RUN npm run build

# ---------- 2. 运行时 ----------
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/apps/api \
    RB_PORT=8888 \
    RB_DATA_DIR=/app/data
WORKDIR /app

# opencv(headless) 仍需要 libGL/libglib；apt 与 pip 均切到腾讯云内网镜像加速构建
RUN sed -i 's|deb.debian.org|mirrors.cloud.tencent.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -i https://mirrors.cloud.tencent.com/pypi/simple -r /tmp/requirements.txt

COPY apps/api /app/apps/api
COPY scripts /app/scripts
COPY --from=web /build/dist /app/apps/web/dist

RUN mkdir -p /app/data
VOLUME ["/app/data"]
EXPOSE 8888

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${RB_PORT}/api/health" || exit 1

# 工作目录是 /app，config.py 通过 __file__ 推导 REPO_ROOT=/app，dist 与 data 路径自动对齐。
# mock provider 依赖 fixtures/canned.json（不进镜像），首次启动时按需生成。
CMD ["sh", "-c", "if [ ! -f /app/apps/api/app/fixtures/canned.json ]; then python /app/scripts/gen_fixtures.py; fi; uvicorn app.main:app --host 0.0.0.0 --port ${RB_PORT:-8888}"]
