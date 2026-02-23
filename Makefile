.PHONY: dev services-up services-down migrate test health status

BACKEND := backend

dev:
	cd $(BACKEND) && .venv/bin/python -m uvicorn app.main:app --reload --port 8000

services-up:
	docker compose up -d

services-down:
	docker compose down

migrate:
	cd $(BACKEND) && .venv/bin/python -m alembic upgrade head

test:
	cd $(BACKEND) && .venv/bin/python -m pytest tests -m "not llm_eval" -v -q

health:
	@curl -s http://localhost:8000/api/health | python3 -m json.tool

status:
	@docker compose ps
	@echo ""
	@systemctl is-active talon.service 2>/dev/null || echo "talon.service not installed"
