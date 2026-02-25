# Talon

Self-hosted personal AI gateway for a single operator. Licensed under [AGPL v3](LICENSE). Inspired by OpenClaw (Node.js/TypeScript). Python/TypeScript stack on a single Hostinger VPS.

**Status: Phases 1–5 complete.** Foundation, LLM gateway, three-tier memory, Skills + Chat Router, and **Frontend MVP** are implemented. The web UI streams chat responses via SSE, shows tool-use indicators, and includes a health dashboard with per-provider circuit breaker status. Light/dark theme support.

- **Stack:** FastAPI, PostgreSQL+pgvector, React+Vite+TypeScript, TailwindCSS v4+daisyUI v5, SSE streaming, LiteLLM, Zustand
- **Docs:** See [AGENTS.md](AGENTS.md) for full spec and [`.cursor/plans/`](.cursor/plans/) for phased implementation roadmap
- **CI:** GitHub Actions runs backend lint (ruff, pyright) + tests, and frontend lint (ESLint) + type-check (tsc) + tests (Vitest) + build on all PRs.

## Quick Start

```bash
# 1. Create virtualenv and install deps
cd backend && python -m venv .venv && .venv/bin/pip install -e .

# 2. Install frontend deps
cd ../frontend && npm install

# 3. Create secrets (see config/SECRETS_SETUP.md)
mkdir -p config/secrets && chmod 700 config/secrets
echo "your_postgres_password" > config/secrets/db_password
chmod 600 config/secrets/db_password

# 4. Configure at least one LLM provider (config/providers.yaml)
#    and set the API key env var(s) it references (e.g. OPENAI_API_KEY).

# 5. Start services (Postgres + SearXNG) and migrate
make services-up
make migrate

# 6. Run backend + frontend (see "Running locally" below)
make dev

# 7. Verify
make test           # backend tests
make test-frontend  # frontend tests (Vitest)
```

## Running locally

From the **project root** (the directory that contains `backend/`, `frontend/`, and `Makefile`):

1. **Start both backend and frontend** (one command; runs two processes):
   ```bash
   make dev
   ```
   This starts:
   - **Backend**: Uvicorn on **http://localhost:8088**
   - **Frontend**: Vite dev server on **http://localhost:5173** (proxies `/api/*` to the backend)

2. **Open the UI** in your browser:
   - **http://localhost:5173**
   You’ll see the Talon chat UI (Chat tab) and a Health tab. All API requests from the UI go through the frontend dev server, which forwards them to the backend.

To run backend and frontend in **separate terminals** instead:
- Terminal 1: `make dev-backend` → backend at http://localhost:8088
- Terminal 2: `make dev-frontend` → frontend at http://localhost:5173  
Still open the UI at **http://localhost:5173**.

### Available endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health status, provider circuit breakers, memory stats |
| GET | `/api/memory` | Compiled core matrix JSON and memory stats (debug) |
| POST | `/api/chat` | Send a message; full tool-calling loop, context from memory |
| GET | `/api/sse/{session_id}?prompt=…` | SSE stream: `token`, `tool_start`, `tool_result`, `done`, `error` |
| GET | `/api/skills` | Loaded skills and tools (registry inspection) |

Interactive API docs when the server is running: `http://localhost:8088/docs`.

## VPS Deploy

These steps assume the repo lives at `/root/projects/talon` on the VPS and Docker is installed.

```bash
# 1. Clone and install deps
git clone https://github.com/philga7/talon.git /root/projects/talon
cd /root/projects/talon/backend
python3 -m venv .venv && . .venv/bin/activate && pip install -e .
cd ../frontend && npm install

# 2. Configure secrets
cd /root/projects/talon
mkdir -p config/secrets && chmod 700 config/secrets
echo "your_postgres_password" > config/secrets/db_password
chmod 600 config/secrets/db_password

# 3. Start services, migrate, build frontend
docker compose up -d
make migrate
make build   # builds frontend/dist/

# 4. Install nginx config + systemd
cp deploy/nginx.conf /etc/nginx/sites-available/talon
ln -sf /etc/nginx/sites-available/talon /etc/nginx/sites-enabled/talon
nginx -t && nginx -s reload
cp deploy/systemd/talon.service /etc/systemd/system/talon.service
systemctl daemon-reload
systemctl enable talon.service
systemctl start talon.service

# 5. Verify
curl http://localhost:8088/api/health  # {"status":"healthy"}
# Browser: http://your-domain/ shows chat UI
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
