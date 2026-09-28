.PHONY: install up down dev worker migrate revision lint fmt type test check openapi

install:   ; uv sync
up:        ; docker compose up -d
down:      ; docker compose down
dev:       ; uv run uvicorn app.main:app --reload --port 8000
worker:    ; uv run arq app.workers.settings.WorkerSettings
migrate:   ; uv run alembic upgrade head
revision:  ; uv run alembic revision --autogenerate -m "$(m)"
lint:      ; uv run ruff check .
fmt:       ; uv run ruff format . && uv run ruff check --fix .
type:      ; uv run mypy app
test:      ; uv run pytest
openapi:   ; uv run python scripts/export_openapi.py openapi.json

check: lint type test
