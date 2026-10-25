.PHONY: install migrate fixture api web test client compose
install:
	uv sync --locked
	pnpm install --frozen-lockfile
migrate:
	uv run alembic upgrade head
fixture:
	PYTHONPATH=apps/api uv run python -m atlas.cli import tests/fixtures/synthetic.json
	PYTHONPATH=apps/api uv run python -m atlas.cli publish synthetic-v1
api:
	PYTHONPATH=apps/api uv run python scripts/serve-real.py
web:
	pnpm dev
test:
	uv run pytest
	pnpm test
	pnpm typecheck
	pnpm test:e2e
client:
	PYTHONPATH=apps/api uv run python scripts/export-openapi.py
	python3 scripts/generate-client.py
compose:
	docker compose --env-file .env -f infra/compose.yaml up --build -d
