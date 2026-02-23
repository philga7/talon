# Talon

Self-hosted personal AI gateway for a single operator. Licensed under [AGPL v3](LICENSE). Inspired by OpenClaw (Node.js/TypeScript). Python/TypeScript stack on a single Hostinger VPS.

**Status: Phases 1–2 complete.** Foundation is implemented (FastAPI skeleton, config, logging, PostgreSQL+Alembic, health endpoint, deploy configs) and the basic LLM gateway is online (`/api/chat`, `/api/sse/{session_id}`, `config/providers.yaml`).

- **Stack:** FastAPI, PostgreSQL+pgvector, React+Vite, SSE streaming, LiteLLM, APScheduler
- **Docs:** See [AGENTS.md](AGENTS.md) for full spec and [`.cursor/plans/`](.cursor/plans/) for phased implementation roadmap (8 phases)
- **CI:** GitHub Actions runs backend lint (ruff, pyright) + tests (`make test`) on pushes to `main` and `feature/**` and on all PRs.

## Quick Start (Backend Phases 1–2)

```bash
# 1. Create virtualenv and install deps
cd backend && python -m venv .venv && .venv/bin/pip install -e .

# 2. Create secrets (see config/SECRETS_SETUP.md)
mkdir -p config/secrets && chmod 700 config/secrets
echo "your_postgres_password" > config/secrets/db_password
chmod 600 config/secrets/db_password

# 3. Start services and migrate
make services-up
make migrate

# 4. Run backend
make dev

# 5. Verify (and reuse for later phases)
curl http://localhost:8000/api/health  # status + provider circuit breaker info
make test  # backend tests for all phases (gateway, memory, skills, ...)
```

## VPS Deploy (Phase 1)

These steps assume the repo lives at `/root/projects/talon` on the VPS and Docker is installed.

```bash
# 1. Clone and install backend deps
git clone https://github.com/philga7/talon.git /root/projects/talon
cd /root/projects/talon/backend
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .

# 2. Configure secrets
cd /root/projects/talon
mkdir -p config/secrets && chmod 700 config/secrets
echo "your_postgres_password" > config/secrets/db_password
chmod 600 config/secrets/db_password

# 3. Start services and migrate
docker compose up -d
make migrate

# 4. Run Talon under systemd
cp deploy/systemd/talon.service /etc/systemd/system/talon.service
systemctl daemon-reload
systemctl enable talon.service
systemctl start talon.service

# 5. Verify
curl http://localhost:8000/api/health  # {"status":"healthy"}
```

### Stopping / Tearing Down

```bash
cd /root/projects/talon

# Stop the Talon API (systemd)
systemctl stop talon.service

# Optionally disable Talon at boot
systemctl disable talon.service

# Stop supporting services (Postgres, SearXNG) but keep data
docker compose down

# Full teardown (removes containers + volumes; **data loss**)
docker compose down -v
```

---

Copyright © 2026 Philip Clapper. All rights reserved. See [LICENSE](LICENSE) for terms of use.
