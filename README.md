# Talon

Self-hosted personal AI gateway for a single operator. Licensed under [AGPL v3](LICENSE). Inspired by OpenClaw (Node.js/TypeScript). Python/TypeScript stack on a single Hostinger VPS.

**Status: Phases 1–8 complete.** Foundation, LLM gateway, three-tier memory, Skills + Chat Router, Frontend MVP, Scheduler + Sentinel, Integrations + remaining skills, and **CLI + Onboarding** are implemented. The `talon` CLI provides `onboard` (setup wizard), `doctor` (diagnostics), `config` (inspection), and `status` (unified health view).

- **Stack:** FastAPI, PostgreSQL+pgvector, React+Vite+TypeScript, TailwindCSS v4+daisyUI v5, SSE streaming, LiteLLM, Zustand, APScheduler, watchdog, discord.py, slack_bolt, Typer+Rich CLI
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
| GET | `/api/scheduler/jobs` | Registered scheduled jobs and status |
| POST | `/api/scheduler/jobs/{id}/trigger` | Manually trigger a scheduled job |
| POST | `/api/integrations/webhook` | Generic webhook receiver (routes through ChatRouter) |

**curl examples** (backend on port 8088; add `-H 'X-API-Key: your-key'` if auth is enabled):

```bash
curl http://localhost:8088/api/health | jq
curl http://localhost:8088/api/memory | jq
curl http://localhost:8088/api/skills | jq
curl http://localhost:8088/api/scheduler/jobs | jq
curl -X POST http://localhost:8088/api/chat -H 'Content-Type: application/json' -d '{"message":"What is AAPL stock price?","session_id":"test"}'
curl 'http://localhost:8088/api/sse/test-session?prompt=hello'
curl -X POST http://localhost:8088/api/scheduler/jobs/{job_id}/trigger
curl -X POST http://localhost:8088/api/integrations/webhook -H 'Content-Type: application/json' -d '{"message":"hello","session_id":"webhook-test"}'
```

Interactive API docs when the server is running: `http://localhost:8088/docs`.

### CLI Commands

After `pip install -e .` in `backend/`, the `talon` CLI is available:

| Command | Description |
|---------|-------------|
| `talon onboard` | Interactive first-time setup wizard (QuickStart/Advanced) |
| `talon doctor` | Diagnostic validator: config, secrets, DB, Docker, systemd, disk |
| `talon status` | Unified status: API health, Docker, systemd, disk space |
| `talon config show` | Display all config values (secrets redacted) |
| `talon config get <key>` | Get a single config value |
| `talon config validate` | Validate config parses without errors |

### Integrations (Discord, Slack, Webhook)

Integrations connect external platforms to the ChatRouter. They start automatically at boot if their secrets are present and skip silently if not.

| Integration | Secrets needed | Install |
|---|---|---|
| Discord | `config/secrets/discord_bot_token` | `pip install discord.py` (or `pip install -e .[discord]`) |
| Slack | `config/secrets/slack_bot_token` + `config/secrets/slack_app_token` | `pip install slack-bolt` (or `pip install -e .[slack]`) |
| Webhook | Optional `config/secrets/webhook_secret` for HMAC auth | Built-in |

Integration status appears in `GET /api/health` under the `integrations` key.

## Logs

- **HTTP I/O (nginx)** – see browser requests, SSE, and proxy errors:
  ```bash
  sudo tail -f /var/log/nginx/access.log
  sudo tail -f /var/log/nginx/error.log
  ```

- **Talon app logs** – structured JSON for chat, skills, memory:
  ```bash
  cd /root/talon
  tail -f data/logs/talon.jsonl | jq
  ```

- **Service startup/crashes** – systemd journal:
  ```bash
  sudo journalctl -u talon.service -f
  ```

## VPS Deploy

These steps assume the repo lives at `/root/talon` on the VPS (so nginx can serve `frontend/dist` from the path in `deploy/nginx.conf`). Docker and nginx must be installed.

### 1. Clone and install

```bash
git clone https://github.com/philga7/talon.git /root/talon
cd /root/talon/backend
python3 -m venv .venv && . .venv/bin/activate && pip install -e .
cd /root/talon/frontend && npm install
```

### 2. Configure secrets

```bash
cd /root/talon
mkdir -p config/secrets && chmod 700 config/secrets
echo "your_postgres_password" > config/secrets/db_password
chmod 600 config/secrets/db_password
# Add LLM API keys etc. as required by config/providers.yaml
```

### 3. Start services, migrate, build frontend

```bash
cd /root/talon
docker compose up -d
make migrate
make build
```

This starts Postgres (and SearXNG). The frontend is built to `frontend/dist/` (static files only; no dev server on the VPS).

### 4. Run the backend and serve the UI

**Backend** runs under systemd (Uvicorn on port 8088):

```bash
cp /root/talon/deploy/systemd/talon.service /etc/systemd/system/talon.service
systemctl daemon-reload
systemctl enable talon.service
systemctl start talon.service
```

**UI** is served by nginx (static files from `frontend/dist/`; `/api/*` proxied to the backend):

```bash
cp /root/talon/deploy/nginx.conf /etc/nginx/sites-available/talon
ln -sf /etc/nginx/sites-available/talon /etc/nginx/sites-enabled/talon
nginx -t && nginx -s reload
```

If you cloned the repo somewhere other than `/root/talon`, edit `root` in `/etc/nginx/sites-available/talon` to point at `.../frontend/dist`.

### 5. Access the UI

You can reach the UI in two ways. **You do not need to expose the app on the public internet** unless you want to.

**Option A — SSH tunnel (recommended for a single operator, same idea as OpenClaw)**  
No public HTTP/HTTPS needed. From your **local machine**:

```bash
ssh -L 8080:localhost:80 root@<your-vps-ip>
```

Leave that session open (or use `-f -N` to background the tunnel). Then in your browser open **http://localhost:8080**. Your browser talks to your machine’s port 8080, which is forwarded over SSH to nginx (port 80) on the VPS. The UI and all `/api/*` requests go through the tunnel; nothing is exposed to the internet.

**Option B — Public access**  
If you want to open the UI from anywhere without an SSH tunnel, open port 80 (and optionally 443 for HTTPS) in your firewall and use **http://&lt;your-vps-ip&gt;/** or **http://&lt;your-domain&gt;/** in the browser. For production you’d typically add HTTPS (e.g. Let’s Encrypt).

In both cases you get the same Talon chat UI (Chat and Health tabs). Nginx serves the frontend and proxies `/api/*` to the backend.

**Verify backend** (on the VPS):

```bash
curl http://localhost:8088/api/health
# Expect: {"status":"healthy", ...}
```

### Stopping / Tearing Down

```bash
cd /root/talon

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
