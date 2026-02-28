.DEFAULT_GOAL := help

.PHONY: help dev dev-backend dev-frontend build services-up services-down \
        migrate test test-frontend test-eval test-chaos test-security test-e2e \
        health status logs deploy

BACKEND  := backend
FRONTEND := frontend

help: ## Show this help
	@printf "\nUsage: make <target>\n\n"
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""

dev: ## Start backend + frontend dev servers
	$(MAKE) dev-backend &
	$(MAKE) dev-frontend &
	wait

dev-backend: ## Start backend only (uvicorn --reload)
	cd $(BACKEND) && .venv/bin/python -m uvicorn app.main:app --reload --port 8088

dev-frontend: ## Start frontend only (vite dev)
	cd $(FRONTEND) && npm run dev

build: ## Build frontend for production (frontend/dist/)
	cd $(FRONTEND) && npm run build

services-up: ## Start Docker services (Postgres, SearXNG)
	docker compose up -d

services-down: ## Stop Docker services
	docker compose down

migrate: ## Run Alembic migrations
	cd $(BACKEND) && .venv/bin/python -m alembic upgrade head

test: ## Run backend tests (pytest, no llm_eval/chaos)
	cd $(BACKEND) && .venv/bin/python -m pytest tests -m "not llm_eval" -v -q

test-frontend: ## Run frontend tests (Vitest)
	cd $(FRONTEND) && npm test

test-eval: ## Run LLM quality tests (real providers, costs tokens)
	cd $(BACKEND) && .venv/bin/python -m pytest tests -m "llm_eval" -v -q

test-chaos: ## Run chaos/resilience tests
	cd $(BACKEND) && .venv/bin/python -m pytest tests/test_llm/test_chaos.py -v -q

test-security: ## Run security hardening tests
	cd $(BACKEND) && .venv/bin/python -m pytest tests/test_security/ -v -q

test-e2e: ## Run Playwright E2E tests (requires make dev)
	cd $(FRONTEND) && npx playwright test

deploy: ## Build + restart systemd service + reload nginx
	$(MAKE) build
	systemctl restart talon.service
	nginx -t && nginx -s reload

health: ## Curl /api/health and pretty-print
	@curl -s http://localhost:8088/api/health | python3 -m json.tool

status: ## Show Docker + systemd service status
	@docker compose ps
	@echo ""
	@systemctl is-active talon.service 2>/dev/null || echo "talon.service not installed"

logs: ## Tail structured log file
	@tail -f data/logs/talon.jsonl | python3 -m json.tool
