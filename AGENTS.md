
# AGENTS.md — Talon

This file is the authoritative entry point for any AI agent or assistant working
on this codebase. Read it fully before writing any code.

---

## What This Project Is

**Talon** is a self-hosted personal AI gateway running on a single Hostinger
KVM 4 VPS (16 GB RAM, 4 vCPU, 100 GB NVMe, Ubuntu 22.04). It replaces OpenClaw
(a Node.js/TypeScript system) with a production-quality Python/TypeScript stack
purpose-built for one operator.

Core responsibilities:
- Route chat messages through a resilient multi-provider LLM gateway
- Maintain a three-tier memory system (core matrix, episodic, working)
- Execute skills (tools) via a dynamic hot-reload registry
- Serve a real-time web UI over SSE
- Bridge Discord, Slack, and webhook integrations through a unified chat router
- Run scheduled jobs and watch the filesystem for live config/skill changes

---

## Stack at a Glance

| Layer | Technology | Notes |
|---|---|---|
| Backend API | FastAPI + Uvicorn (4 workers) | Python 3.12, `uvloop` |
| LLM routing | LiteLLM | Circuit breaker + fallback chain |
| Database | PostgreSQL 16 + pgvector | Docker container, `asyncpg` driver |
| ORM / migrations | SQLAlchemy 2 (async) + Alembic | All models in `backend/app/models/` |
| Memory | Custom compressor → JSON matrix | Markdown source → compiled binary |
| Scheduler | APScheduler (AsyncIOScheduler) | Jobs persist in PostgreSQL |
| File watching | watchdog | Hot-reload for skills + config |
| Frontend | React 18 + Vite + TypeScript | `frontend/` directory |
| Styling | TailwindCSS v4 + daisyUI v5 | No custom CSS unless unavoidable |
| Realtime | Server-Sent Events (SSE) | `/api/sse/{session_id}` |
| Logging | structlog (JSON lines) | `data/logs/talon.jsonl` |
| Deployment | systemd (`talon.service`) + Docker Compose | Auxiliary services only in Docker |
| Secrets | Pydantic `BaseSettings` with `secrets_dir` | `config/secrets/` chmod 700/600 |

---

## Project Layout

```
/root/talon/
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI app factory + lifespan
│   │   ├── dependencies.py      FastAPI DI: get_db, get_gateway, get_memory, etc.
│   │   ├── models/              SQLAlchemy ORM models
│   │   ├── api/                 Route handlers (chat.py, sse.py, health.py, ...)
│   │   ├── llm/                 LLM gateway, circuit breaker, providers
│   │   ├── memory/              Compressor, episodic store, working memory
│   │   ├── skills/              BaseSkill, registry, executor
│   │   ├── integrations/        Discord, Slack, webhook
│   │   ├── scheduler/           APScheduler engine + built-in jobs
│   │   ├── sentinel/            watchdog watcher + directory tree
│   │   └── core/                Config, logging, middleware, security, errors
│   ├── skills/                  User skill directories (hot-loaded)
│   ├── tests/
│   ├── alembic/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── components/          React components (feature-collocated)
│   │   ├── hooks/               Custom React hooks
│   │   ├── stores/              Zustand state stores
│   │   ├── api/                 API client functions
│   │   └── types/               Shared TypeScript types
│   ├── e2e/                     Playwright tests
│   └── package.json
├── data/
│   ├── memories/                Markdown source files for core matrix
│   └── logs/                    Structured JSON log files
├── config/
│   ├── talon.toml               Main config (chmod 600)
│   ├── providers.yaml           LLM provider definitions
│   └── secrets/                 Secrets directory (chmod 700, files chmod 600)
├── scripts/                     Migration + utility scripts
├── deploy/                      systemd unit, nginx config, Dockerfile
├── docker-compose.yml
└── Makefile
```

---

## Architecture Documents

These files in `.cursor/rules/` contain the full technical spec.
Always consult them before making architectural decisions:

| Document | Covers |
|---|---|
| `00-talon-overview.md` | Philosophy, SSE event schema, full stack decision rationale |
| `01-talon-project-structure.md` | Annotated directory tree, Makefile targets |
| `02-talon-llm-gateway.md` | Circuit breaker, fallback chain, retry, provider config |
| `03-talon-memory-engine.md` | Three-tier memory, compressor, prompt assembly |
| `04-talon-skills-engine.md` | BaseSkill contract, registry, executor, tool calling loop |
| `05-talon-integrations-scheduler-sentinel.md` | Discord, Slack, APScheduler, watchdog |
| `06-talon-logging-security.md` | structlog pipeline, error taxonomy, secrets, rate limiting |
| `07-talon-deployment.md` | systemd, Docker Compose, nginx, migration phases |
| `08-talon-testing-strategy.md` | Test pyramid, fixtures, LLM quality tests, Playwright |
| `09-talon-migration-from-openclaw.md` | OpenClaw → Talon migration guide |

---

## Non-Negotiable Rules

1. **Secrets never appear in code.** Read from `config/secrets/` via Pydantic
   `BaseSettings`. If a secret ends up in a log, a test, or a string literal,
   that is a security defect.

2. **No string interpolation in SQL.** Use SQLAlchemy ORM or parameterized queries.

3. **Every public function has a type signature.** Python: full type hints.
   TypeScript: no `any` except at explicit external API boundaries.

4. **Errors are structured, not strings.** Raise typed exceptions. Log with
   structlog fields, not f-strings. The `SecretMasker` processor runs on every
   log entry — do not work around it.

5. **Tests mock the LLM gateway.** Never call a real provider in the unit or
   integration suite. Use `mock_gateway` fixture. Real provider calls belong
   in `@pytest.mark.llm_eval` only.

6. **Skills are self-contained.** A skill must not import from another skill.
   Shared utilities go in `app/skills/utils/`.

7. **Resource limits are real.** The VPS has 16 GB RAM. Max 4 Uvicorn workers.
   Do not suggest horizontal scaling solutions.

8. **`chmod 600` on secrets, `chmod 700` on the secrets directory.** Every script
   that writes to `config/secrets/` must set these permissions explicitly.

---

## LLM Provider Priority

```
Primary:    configured in config/providers.yaml (highest priority)
Fallback:   second provider in priority order
Additional: further providers in priority order
```

Circuit breaker opens after **3 failures** within 60 seconds.
Recovery timeout: **60 seconds** (HALF_OPEN probe).
All provider config lives in `config/providers.yaml`.

---

## Key Invariants

- SSE is the only streaming mechanism. WebSockets are not used.
- APScheduler runs **inside** the FastAPI process, not as a separate service.
- watchdog runs **inside** the FastAPI process lifespan.
- PostgreSQL is accessed **only** via SQLAlchemy async sessions.
- The frontend is a **pure static build** served by nginx.
- All chat, regardless of platform, routes through `ChatRouter`.

---

## Running Locally

```bash
docker compose up -d
cd backend && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
# or: make dev
```

Health check: `curl http://localhost:8000/api/health | jq`
