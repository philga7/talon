# Talon

A self-hosted personal AI gateway purpose-built for a single operator on a single server. Talon routes chat through a resilient multi-provider LLM gateway, maintains long-term memory with pgvector semantic search, executes tools via a hot-reloadable skill registry, and serves a real-time streaming web UI — all from one Python/TypeScript process on a VPS.

Inspired by [OpenClaw](https://github.com/openclaw/openclaw). Licensed under [AGPL v3](LICENSE).

---

## Why Talon Exists

OpenClaw is a Node.js/TypeScript personal AI assistant designed for multi-device, multi-platform use with WebSocket-based control planes, companion apps (macOS/iOS/Android), and dozens of channel integrations. It is a powerful, broad tool.

Talon takes a different approach: a **deep, single-server system** optimized for one operator who wants full control over memory, identity, and tool execution without the operational surface of a distributed architecture. Where OpenClaw goes wide (15+ channels, companion apps, voice wake, canvas, sandbox modes), Talon goes deep (three-tier persistent memory, persona-scoped identity, circuit-breaker resilience, security hardening, scheduled automation).

### Talon vs OpenClaw

| Concern | Talon | OpenClaw |
|---|---|---|
| **Runtime** | Python 3.12 (FastAPI) + TypeScript (React) | Node.js / TypeScript |
| **Deployment** | Single VPS, systemd + Docker (aux only) | Local machine, Docker, or cloud; multi-device |
| **Streaming** | Server-Sent Events (SSE) | WebSockets |
| **Memory** | Three-tier: core matrix (Markdown compiled to JSON, 2k token budget) + episodic (pgvector cosine similarity) + working (per-session) | Session-based; workspace prompt files (AGENTS.md, SOUL.md) |
| **Database** | PostgreSQL 16 + pgvector | None (file-based sessions) |
| **Identity** | Multi-persona via `personas.yaml` — channel-bound, model-override per persona, scoped memory | Multi-agent routing — isolated sessions per agent |
| **LLM routing** | LiteLLM with circuit breaker (3-fail open, 60s recovery), fallback chain, exponential backoff | Model config with failover profiles |
| **Channels** | Discord, Slack, Telegram, Webhook (4) | WhatsApp, Telegram, Slack, Discord, Google Chat, Signal, iMessage, Teams, WebChat, Matrix, Zalo (15+) |
| **Companion apps** | Web UI only | macOS menu bar, iOS node, Android node |
| **Voice** | Not supported | Voice Wake + Talk Mode (macOS/iOS/Android) |
| **Security** | IronClaw: SSRF guard, leak scanner, prompt injection pipeline, per-skill HTTP allowlist, chained-hash audit log | DM pairing, sandbox mode (Docker) for non-main sessions |
| **Skills** | `BaseSkill` ABC, TOML manifests, hot-reload via watchdog | SKILL.md-based, managed/bundled/workspace skills |
| **Scheduling** | APScheduler (in-process, PostgreSQL jobstore) | Cron jobs via Gateway |
| **CLI** | `talon onboard/doctor/status/config` (Typer + Rich) | `openclaw onboard/doctor/gateway/agent` |
| **License** | AGPL v3 | MIT |

**Choose Talon** if you want deep memory, persona-scoped identity, security hardening, and a Python-native stack on a single VPS you fully control.

**Choose OpenClaw** if you need broad channel coverage (WhatsApp, iMessage, Teams), companion apps, voice interaction, browser control, or multi-device deployment.

---

## Features

### LLM Gateway
Multi-provider fallback chain with per-provider circuit breakers. When a provider fails 3 times in 60 seconds the breaker opens, traffic routes to the next provider, and a recovery probe fires after 60 seconds. Retry uses exponential backoff with jitter. All provider config lives in `config/providers.yaml` — no provider strings in code. Powered by [LiteLLM](https://github.com/BerriAI/litellm) for model-agnostic routing.

### Three-Tier Memory
- **Core matrix** — human-editable Markdown files in `data/memories/<persona>/` compiled to a token-bounded JSON matrix (2,000 token budget). Priority-ranked: identity rows always included, capabilities included if budget allows.
- **Episodic store** — conversation turns persisted to PostgreSQL with pgvector embeddings. Top-k cosine similarity retrieval per session. Archival job compacts entries older than 30 days.
- **Working memory** — per-session in-process dict with idle GC after 30 minutes.

The memory engine assembles all three tiers into the system prompt on every request. Introspectable via `/api/memory` and the frontend Memory tab.

### Multi-Persona System
Config-driven identity layers defined in `config/personas.yaml`. Each persona has its own core memory directory, optional model override, and channel bindings (e.g. specific Slack channels route to `analyst` while others route to `main`). Episodic memory is shared but persona-filtered. Unknown channels fall back to the default persona.

### Skills Engine
Self-contained tools implementing `BaseSkill` with TOML manifests. The `SkillRegistry` scans, loads, and namespaces tools for the LLM. The `SkillExecutor` wraps every call in `asyncio.wait_for(timeout=30s)` and returns `SkillResult` — skills never raise. `FileSentinel` (watchdog) hot-reloads skills on file change without restart.

**Ported skills:** `searxng_search`, `yahoo_finance`, `weather_enhanced`, `hostinger_email`, `bird` (X/Twitter CLI), `neuron_brief` (AI newsletter fetcher), `notify` (push notifications via ntfy).

### Real-Time Web UI
React 18 + TypeScript frontend with TailwindCSS v4 + daisyUI v5. Four tabs:
- **Chat** — streamed responses via SSE with tool-use indicators
- **Health** — per-provider circuit breaker status, memory stats
- **Memory** — core matrix viewer with category collapsing, search/filter, priority badges
- **Logs** — real-time application log stream with level filtering and auto-scroll

Memory and Log panels are lazy-loaded via `React.lazy()` for fast initial load.

### Integrations
Discord (via discord.py), Slack (via slack_bolt Socket Mode), Telegram (via python-telegram-bot long-polling), and generic webhook receiver. All route through the unified `ChatRouter`. Integrations start conditionally — if the secret file exists, the integration starts; if not, it silently skips. No crash, no error.

### Push Notifications (ntfy)
Outbound mobile/desktop push notifications via a self-hosted [ntfy](https://ntfy.sh) instance. `NtfyClient` is a thin async httpx wrapper that supports Basic auth and Bearer tokens, exposes convenience `alert()` and `info()` helpers, and never raises (fire-and-forget safe). The `notify` skill lets the LLM push alerts proactively. `POST /api/notify` is available for scheduler jobs and webhook triggers. Configured via four secrets: `ntfy_url`, `ntfy_topic`, `ntfy_username`, `ntfy_password`.

### Scheduler + Sentinel
APScheduler runs in-process with a PostgreSQL jobstore. Built-in jobs: memory recompile, LLM health sweep, log rotation, working memory GC, episodic archival, session cleanup. `FileSentinel` watches `data/memories/`, `backend/skills/`, and `config/` for file changes and dispatches events to the memory engine, skill registry, or config reloader.

### Security (IronClaw)
- **SSRF Guard** — blocks outbound requests to RFC-1918, loopback, link-local, and Docker bridge ranges before any egress. Configurable exceptions (e.g. SearXNG on localhost:8080).
- **Leak Scanner** — SHA-256 hashes of all vault secrets; scans outbound request bodies and headers before dispatch. Blocks on match.
- **Prompt Guard** — tiered severity engine (Block / Warn / Review / Sanitize) scanning user messages, tool responses, and memory retrieval for injection patterns.
- **Skill HTTP Client** — per-skill `allowed_hosts` enforcement. Skills no longer self-construct HTTP clients.
- **Audit Log** — chained-hash JSONL entries for every tool call. Inputs masked, outputs hashed. Chain provides tamper evidence.

### CLI
Typer + Rich CLI installed as `talon`:
- `talon onboard` — interactive setup wizard (QuickStart / Advanced) that can create `config/secrets/`, guide you through initial LLM provider setup (OpenAI, Anthropic, Ollama, Ollama Cloud, custom), and bootstrap per-persona memory (including prompting for the main agent's name and role)
- `talon doctor` — validates config, secrets permissions, DB connectivity, Docker services, systemd, disk space
- `talon status` — unified view: API health, Docker, systemd, disk
- `talon config show|get|validate` — config inspection (secrets redacted)

### OpenClaw Migration
Five scripts in `scripts/` for migrating from an existing OpenClaw installation:
- `migrate_memories.py` — copies workspace Markdown to per-persona layout, compiles initial core matrices
- `episodic_import.py` — parses daily memory logs and JSONL sessions into the episodic store
- `migrate_skills.py` — verifies ported skills, generates stubs for skills needing manual porting
- `migrate_config.py` — extracts secrets, generates `providers.yaml` and `personas.yaml`
- `validate_migration.py` — 12-point checklist before decommissioning OpenClaw

---

## Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI + Uvicorn (4 workers), Python 3.12 |
| LLM routing | LiteLLM, circuit breaker + fallback chain |
| Database | PostgreSQL 16 + pgvector (Docker), asyncpg |
| ORM / migrations | SQLAlchemy 2 (async) + Alembic |
| Frontend | React 18 + Vite + TypeScript |
| Styling | TailwindCSS v4 + daisyUI v5 |
| Streaming | Server-Sent Events (SSE) |
| State management | Zustand |
| Integrations | discord.py, slack_bolt, python-telegram-bot, webhook |
| Scheduler | APScheduler (AsyncIOScheduler) |
| File watching | watchdog |
| Logging | structlog (JSON lines) |
| CLI | Typer + Rich |
| Secrets | Pydantic BaseSettings + `config/secrets/` (chmod 700/600) |
| Deployment | systemd + Docker Compose (auxiliary only) + nginx |

---

## Quick Start

```bash
# Install backend
cd backend && python -m venv .venv && .venv/bin/pip install -e .

# Install frontend
cd ../frontend && npm install

# Set up secrets
mkdir -p config/secrets && chmod 700 config/secrets
echo "your_postgres_password" > config/secrets/db_password
chmod 600 config/secrets/db_password

# Configure at least one LLM provider in config/providers.yaml
# (or run `talon onboard` to generate an initial providers.yaml interactively)

# Start Postgres + SearXNG, run migrations, launch
make services-up
make migrate
make dev
```

Open **http://localhost:5173** for the web UI. Backend runs at **http://localhost:8088**.

---

## Running Locally

```bash
make dev            # backend (port 8088) + frontend (port 5173) concurrently
make dev-backend    # backend only
make dev-frontend   # frontend only
```

The Vite dev server proxies `/api/*` to the backend.

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | System health, provider circuit breakers, memory stats |
| GET | `/api/memory` | Compiled core matrix and memory stats |
| POST | `/api/chat` | Send a message (full tool-calling loop) |
| GET | `/api/sse/{session_id}?prompt=…` | SSE stream: `token`, `tool_start`, `tool_result`, `done`, `error` |
| GET | `/api/skills` | Loaded skills and tools |
| GET | `/api/scheduler/jobs` | Scheduled jobs and status |
| POST | `/api/scheduler/jobs/{id}/trigger` | Manually trigger a job |
| POST | `/api/integrations/webhook` | Webhook receiver (routes through ChatRouter) |
| POST | `/api/notify` | Send a push notification via ntfy (rate-limited: 20/min) |

`/api/chat`, `/api/sse`, and webhook payloads accept optional `persona_id` (defaults to `main`). Interactive API docs at `http://localhost:8088/docs`.

### CLI

```bash
talon onboard          # first-time setup wizard
talon doctor           # system diagnostic
talon status           # unified health view
talon config show      # display config (secrets redacted)
```

---

## Testing

```bash
make test              # backend unit + integration (240+ tests, ~2s)
make test-frontend     # Vitest component tests (23 tests)
make test-security     # IronClaw security tests (34 tests)
make test-chaos        # resilience: all-providers-down, timeout storms
make test-eval         # LLM quality tests (real providers, costs tokens)
make test-e2e          # Playwright E2E (requires make dev running)
```

CI runs on GitHub Actions: ruff + pyright + pytest (backend), ESLint + tsc + Vitest + build (frontend).

---

## Integrations

| Integration | Secrets Required | Install |
|---|---|---|
| Discord | `config/secrets/discord_bot_token` | `pip install -e .[discord]` |
| Slack | `config/secrets/slack_bot_token` + `slack_app_token` | `pip install -e .[slack]` |
| Telegram | `config/secrets/telegram_bot_token` | `pip install -e .[telegram]` |
| Webhook | Optional `config/secrets/webhook_secret` (HMAC) | Built-in |
| ntfy (push) | `ntfy_url` + `ntfy_topic` + `ntfy_username` + `ntfy_password` | Built-in |

Chat integrations start if their secrets exist and skip silently if not. ntfy is optional — Talon starts normally without it; the `notify` skill reports unconfigured and `POST /api/notify` returns 503.

---

## OpenClaw Migration

```bash
python scripts/migrate_memories.py --openclaw-dir ~/.openclaw
python scripts/episodic_import.py --openclaw-dir ~/.openclaw   # add --include-sessions for full history
python scripts/migrate_config.py --openclaw-dir ~/.openclaw
python scripts/migrate_skills.py
python scripts/validate_migration.py --skip-health
```

---

## VPS Deploy

Target: single VPS (e.g. Hostinger KVM 4 — 16 GB RAM, 4 vCPU, 100 GB NVMe, Ubuntu 22.04). Docker and nginx must be installed.

Assume Talon is checked out to `/root/talon`. If you use a different path, update the systemd unit accordingly.

### One-time install

```bash
git clone https://github.com/philga7/talon.git /root/talon

# Backend
cd /root/talon/backend
python3 -m venv .venv
./.venv/bin/pip install -e .

# Frontend
cd /root/talon/frontend
npm install
```

### Configure secrets

```bash
cd /root/talon
mkdir -p config/secrets && chmod 700 config/secrets
echo "your_postgres_password" > config/secrets/db_password
chmod 600 config/secrets/db_password
# Add LLM API keys as required by config/providers.yaml
```

### Build frontend and prepare services

```bash
cd /root/talon
make services-up     # Postgres + SearXNG (Docker)
make migrate         # Alembic migrations
make build           # frontend → frontend/dist/
```

### Run via systemd + nginx

```bash
cd /root/talon

# Backend (FastAPI + scheduler + integrations)
cp deploy/systemd/talon.service /etc/systemd/system/talon.service
systemctl daemon-reload
systemctl enable --now talon.service

# Frontend (nginx reverse proxy)
cp deploy/nginx.conf /etc/nginx/sites-available/talon
ln -sf /etc/nginx/sites-available/talon /etc/nginx/sites-enabled/talon
nginx -t && nginx -s reload
```

### Stand up (start all services on VPS)

From your Talon directory on the VPS (e.g. `/root/talon`):

```bash
cd /root/talon

# 1) Infra (Postgres + SearXNG)
make services-up

# 2) Database migrations (safe to run; no-op if up-to-date)
make migrate

# 3) Backend + scheduler + integrations
sudo systemctl restart talon.service

# 4) Frontend / reverse proxy
sudo nginx -t && sudo nginx -s reload

# 5) Optional: verify health
curl -s http://localhost:8088/api/health | python3 -m json.tool
```

### Tear down (stop services on VPS)

```bash
# Stop FastAPI backend + scheduler + integrations
sudo systemctl stop talon.service

# Stop Docker infra (keeps data)
cd /root/talon
make services-down

# Optional: remove Docker volumes (DESTROYS data)
docker compose down -v
```

---

## Logs

```bash
tail -f data/logs/talon.jsonl | jq          # structured app logs
sudo journalctl -u talon.service -f          # systemd startup/crash logs
sudo tail -f /var/log/nginx/access.log       # HTTP/proxy logs
```

Or use the **Logs** tab in the web UI for real-time filtered log viewing.

---

## Project Layout

```
talon/
├── backend/
│   ├── app/
│   │   ├── main.py              App factory + lifespan
│   │   ├── dependencies.py      FastAPI DI
│   │   ├── api/                 Route handlers
│   │   ├── llm/                 Gateway, circuit breaker, retry
│   │   ├── memory/              Compressor, episodic, working
│   │   ├── skills/              BaseSkill, registry, executor
│   │   ├── integrations/        Discord, Slack, webhook
│   │   ├── notifications/       NtfyClient (push notifications)
│   │   ├── scheduler/           APScheduler + jobs
│   │   ├── sentinel/            watchdog + event router
│   │   ├── security/            IronClaw: SSRF, leak, prompt, audit
│   │   ├── personas/            PersonaRegistry
│   │   ├── cli/                 Typer CLI
│   │   └── core/                Config, logging, middleware, errors
│   ├── skills/                  Skill directories (hot-loaded)
│   └── tests/                   pytest suite (240+ tests)
├── frontend/
│   ├── src/                     React + TypeScript
│   └── e2e/                     Playwright specs
├── data/
│   ├── memories/                Per-persona Markdown sources
│   └── logs/                    Structured JSON logs
├── config/
│   ├── providers.yaml           LLM provider definitions
│   ├── personas.yaml            Persona + channel bindings
│   └── secrets/                 chmod 700/600
├── scripts/                     Migration scripts
├── deploy/                      systemd unit, nginx config
├── docker-compose.yml           Postgres + SearXNG
└── Makefile
```

---

Copyright (c) 2026 Philip Clapper. All rights reserved. See [LICENSE](LICENSE) for terms of use.
