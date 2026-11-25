PYTHON ?= $(shell command -v python3.12 2>/dev/null || command -v python3.11 2>/dev/null || command -v python3)
VENV := apps/api/.venv
PY := $(VENV)/bin/python

.PHONY: install install-api install-web dev seed test types demo serve

install: install-api install-web

install-api:
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(PY) -m pip install -q --upgrade pip
	cd apps/api && .venv/bin/pip install -q -e ".[dev]"

install-web:
	cd apps/web && npm install --silent

seed:
	cd apps/api && .venv/bin/python ../../scripts/gen_fixtures.py
	cd apps/api && .venv/bin/python -c "from app.seeds import seed_all; seed_all(); print('seeded')"

dev:
	bash scripts/dev.sh

# 单端口预览（与容器一致）：构建前端后由 FastAPI 一起托管
serve:
	cd apps/web && npm run build
	cd apps/api && RB_PORT=$${RB_PORT:-8888} .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port $${RB_PORT:-8888}

test:
	cd apps/api && .venv/bin/python -m pytest -q
	cd apps/web && npm run test -- --run

types:
	cd apps/api && .venv/bin/python ../../scripts/dump_openapi.py
	cd apps/web && npx openapi-typescript ../api/openapi.json -o src/api/types.ts

demo:
	bash scripts/demo.sh
