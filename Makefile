.PHONY: install dev up down migrate migration-current format lint typecheck test build check

install:
	pnpm install --frozen-lockfile
	uv sync --frozen --all-packages

dev:
	docker compose up --build

up:
	docker compose up --build -d

down:
	docker compose down

migrate:
	uv run alembic -c apps/api/alembic.ini upgrade head

migration-current:
	uv run alembic -c apps/api/alembic.ini current

format:
	pnpm format

lint:
	pnpm lint

typecheck:
	pnpm typecheck

test:
	pnpm test

build:
	pnpm build

check:
	pnpm format:check
	pnpm lint
	pnpm typecheck
	pnpm test
	pnpm build
	docker compose config --quiet
