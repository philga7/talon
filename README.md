# Talon

Self-hosted personal AI gateway for a single operator. Licensed under [AGPL v3](LICENSE). Inspired by OpenClaw (Node.js/TypeScript). Python/TypeScript stack on a single Hostinger VPS.

**Status: Phases 1–4 complete.** Foundation, LLM gateway, three-tier memory, and **Skills + Chat Router** are implemented. The chat pipeline runs a full tool-calling loop (context from memory → LLM with tools → skill execution → final response). Built-in skills: `searxng_search`, `yahoo_finance`. Registry inspection: `GET /api/skills`.

- **Stack:** FastAPI, PostgreSQL+pgvector, React+Vite, SSE streaming, LiteLLM, APScheduler
- **Docs:** See [AGENTS.md](AGENTS.md) for full spec and [`.cursor/plans/`](.cursor/plans/) for phased implementation roadmap (8 phases)
- **CI:** GitHub Actions runs backend lint (ruff, pyright) + tests (`make test`) on pushes to `main` and `feature/**` and on all PRs.

## Quick Start (Backend Phases 1–4)

```bash
# 1. Create virtualenv and install deps
cd backend && python -m venv .venv && .venv/bin/pip install -e .

# 2. Create secrets (see config/SECRETS_SETUP.md)
mkdir -p config/secrets && chmod 700 config/secrets
echo "your_postgres_password" > config/secrets/db_password
chmod 600 config/secrets/db_password

# 3. Configure at least one LLM provider (config/providers.yaml)
#    and set the API key env var(s) it references (e.g. OPENAI_API_KEY).

# 4. Start services (Postgres + SearXNG) and migrate
make services-up
make migrate

# 5. Run backend
make dev

# 6. Verify
curl http://localhost:8088/api/health   # status, providers, memory stats
curl http://localhost:8088/api/skills  # loaded skills (searxng_search, yahoo_finance)
curl -X POST http://localhost:8088/api/chat -H 'Content-Type: application/json' \
  -d '{"message":"What is AAPL stock price?","session_id":"quickstart"}'
make test  # backend tests (gateway, memory, skills, chat, ...)
```

### Available endpoints (Phases 1–4)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health status, provider circuit breakers, memory stats |
| GET | `/api/memory` | Compiled core matrix JSON and memory stats (debug) |
| POST | `/api/chat` | Send a message; full tool-calling loop, context from memory |
| GET | `/api/sse/{session_id}?prompt=…` | SSE stream: `token`, `tool_start`, `tool_result`, `done`, `error` |
| GET | `/api/skills` | Loaded skills and tools (registry inspection) |

Interactive API docs when the server is running: `http://localhost:8088/docs`.

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
curl http://localhost:8088/api/health  # {"status":"healthy"}
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
