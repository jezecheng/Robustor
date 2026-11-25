#!/usr/bin/env bash
# 本地开发：API(8888) + Vite(5173，代理 /api 与 /media 到 8888)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${RB_PORT:-8888}"

cd "$ROOT/apps/api"
RB_PORT="$PORT" .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --reload &
API_PID=$!

cd "$ROOT/apps/web"
RB_PORT="$PORT" npm run dev -- --port 5173 --strictPort &
WEB_PID=$!

cleanup() {
  kill "$API_PID" "$WEB_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM

echo "API  → http://localhost:${PORT}/api/docs"
echo "Web  → http://localhost:5173"
wait
