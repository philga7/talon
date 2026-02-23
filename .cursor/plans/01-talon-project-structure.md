
# Talon — Project Structure

```
/root/talon/
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI app factory + lifespan context manager
│   │   ├── dependencies.py      get_db, get_gateway, get_memory, get_registry, get_scheduler
│   │   ├── models/              SQLAlchemy ORM models (episodic_memory, sessions, jobs)
│   │   ├── schemas/             Pydantic request/response models
│   │   ├── api/
│   │   │   ├── chat.py          POST /api/chat — main chat endpoint
│   │   │   ├── sse.py           GET /api/sse/{session_id} — streaming
│   │   │   ├── health.py        GET /api/health — provider + service status
│   │   │   ├── skills.py        GET /api/skills — skill registry
│   │   │   ├── memory.py        GET/POST /api/memory — memory inspection
│   │   │   └── scheduler.py     GET/POST /api/scheduler/jobs
│   │   ├── llm/
│   │   │   ├── gateway.py       LiteLLM wrapper, fallback chain, circuit breakers
│   │   │   ├── circuit_breaker.py  Per-provider circuit breaker (CLOSED/OPEN/HALF_OPEN)
│   │   │   ├── retry.py         Exponential backoff with jitter
│   │   │   └── models.py        LLMResponse, LLMRequest Pydantic models
│   │   ├── memory/
│   │   │   ├── engine.py        MemoryEngine — orchestrates all three tiers
│   │   │   ├── compressor.py    Markdown → JSON matrix compiler
│   │   │   ├── episodic.py      pgvector similarity search + save
│   │   │   └── working.py       Per-session in-memory dict store
│   │   ├── skills/
│   │   │   ├── base.py          BaseSkill ABC, ToolDefinition, SkillResult
│   │   │   ├── registry.py      Dynamic skill loader + hot-reload
│   │   │   ├── executor.py      asyncio.wait_for wrapper + error handling
│   │   │   └── builtin/         search, finance, weather, email, news
│   │   ├── integrations/
│   │   │   ├── base.py          BaseIntegration ABC
│   │   │   ├── discord.py       discord.py client (Socket Mode equivalent)
│   │   │   ├── slack.py         slack_bolt AsyncApp (Socket Mode)
│   │   │   └── webhook.py       Generic inbound webhook receiver
│   │   ├── scheduler/
│   │   │   ├── engine.py        TalonScheduler wrapping AsyncIOScheduler
│   │   │   └── jobs.py          Built-in jobs: memory recompile, log rotate, GC
│   │   ├── sentinel/
│   │   │   ├── watcher.py       watchdog Observer + EventRouter
│   │   │   └── tree.py          DirectoryTree builder with cache
│   │   └── core/
│   │       ├── config.py        Pydantic BaseSettings, secrets_dir loader
│   │       ├── logging.py       structlog configure, SecretMasker processor
│   │       ├── middleware.py    CorrelationID + RateLimit middleware
│   │       ├── security.py      API key auth, session token helpers
│   │       └── errors.py        Exception hierarchy + global handlers
│   ├── skills/                  User skill directories (hot-loaded by Sentinel)
│   │   ├── searxng_search/      skill.toml + main.py + SKILL.md
│   │   └── yahoo_finance/
│   ├── tests/
│   │   ├── conftest.py          db_session, mock_gateway, client fixtures
│   │   ├── test_api/
│   │   ├── test_llm/
│   │   ├── test_memory/
│   │   ├── test_skills/
│   │   └── test_core/
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── alembic.ini
│   └── pyproject.toml           uv-managed dependencies + ruff + pyright config
├── frontend/
│   ├── src/
│   │   ├── components/          Feature-colocated React components + __tests__/
│   │   │   ├── chat/
│   │   │   ├── health/
│   │   │   ├── memory/
│   │   │   └── shared/
│   │   ├── hooks/               useSSE, useChat, useHealth, useSkills
│   │   ├── stores/              Zustand: chatStore, healthStore, memoryStore
│   │   ├── api/                 client.ts — all fetch calls
│   │   └── types/               api.ts, sse.ts, shared.ts
│   ├── e2e/                     Playwright test specs
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   └── package.json
├── data/
│   ├── memories/                Markdown source files → compiled to core_matrix.json
│   │   ├── identity.md
│   │   ├── user_preferences.md
│   │   ├── long_term.md
│   │   └── capabilities.md
│   └── logs/                    talon.jsonl (structured, rotated daily)
├── config/
│   ├── talon.toml               Main config (chmod 600)
│   ├── providers.yaml           LLM provider list and routing config
│   └── secrets/                 chmod 700; each file chmod 600
│       ├── db_password
│       ├── llm_api_keys         JSON: {"provider_name": "key"}
│       ├── discord_token
│       ├── slack_bot_token
│       └── slack_app_token
├── scripts/                     Migration + utility scripts
├── deploy/
│   ├── systemd/talon.service
│   ├── nginx.conf
│   └── Dockerfile               Optional full-container build
├── docker-compose.yml           PostgreSQL + SearXNG only
└── Makefile
```
