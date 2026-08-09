# GridIron — dev on the M4, deploy to the iMac over the tailnet.
# One-time iMac setup: deploy/setup-imac.sh (see README).

IMAC_HOST ?= imac            # tailnet hostname or MagicDNS name of the iMac
IMAC_DIR  ?= ~/gridiron      # checkout location on the iMac

.PHONY: dev backend frontend lint test build deploy migrate

## dev: run backend (uvicorn --reload :8000) + frontend (vite :5173) together
dev:
	$(MAKE) -j2 backend frontend

backend:
	uv run alembic upgrade head
	uv run uvicorn backend.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

## lint: ruff + black --check + eslint + prettier --check
lint:
	uv run ruff check backend tests
	uv run black --check backend tests
	cd frontend && npm run lint

## test: backend pytest + frontend vitest
test:
	uv run pytest
	cd frontend && npm test -- --run

## build: production frontend bundle into frontend/dist (served by FastAPI)
build:
	cd frontend && npm ci && npm run build

## migrate: apply alembic migrations locally
migrate:
	uv run alembic upgrade head

## deploy: ship current git HEAD to the iMac and restart the LaunchAgent
deploy:
	ssh $(IMAC_HOST) 'cd $(IMAC_DIR) && ./deploy/deploy.sh'
