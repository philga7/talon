
# Talon — System Overview

## What It Is
Talon is a self-hosted personal AI gateway running on a single Hostinger KVM 4 VPS
(16 GB RAM, 4 vCPU, 100 GB NVMe, Ubuntu 22.04). Inspired by OpenClaw — a Node.js/TypeScript
system. Production-quality Python/TypeScript stack built for one operator.

## Philosophy
- **Correctness first.** A wrong answer delivered reliably is worse than a correct answer
  delivered slowly.
- **Deterministic code for deterministic problems.** Use the LLM for reasoning.
  Use Python for everything else.
- **Observable by default.** Every request, every tool call, every provider failure
  is a structured JSON log entry with a correlation ID.
- **Fail gracefully, not silently.** Circuit breakers, fallback chains, and typed
  error responses ensure the system degrades predictably.

## Stack Decisions

| Concern | Choice | Rejected | Reason |
|---|---|---|---|
| Backend API | FastAPI + Uvicorn | Django, Flask | Native async, auto OpenAPI, DI system |
| LLM routing | LiteLLM | Direct provider SDKs | Single interface for all providers + fallback |
| Database | PostgreSQL 16 + pgvector | Supabase, SQLite | Full SQL control, vector search, single-server |
| ORM | SQLAlchemy 2 async | Tortoise, raw asyncpg | Mature, alembic migrations, full type support |
| Frontend | React 18 + Vite | Next.js, SvelteKit | No SSR needed; static build served by nginx |
| Styling | TailwindCSS v4 + daisyUI v5 | Custom CSS, MUI | Rapid, consistent, no JS runtime overhead |
| Streaming | Server-Sent Events (SSE) | WebSockets | Simpler, HTTP-native, no WS library needed |
| Scheduler | APScheduler | Celery, cron | In-process, no broker, persists in PostgreSQL |
| File watching | watchdog | inotifywait | Python-native, cross-platform, simple API |
| Logging | structlog | loguru, stdlib | JSON output, processor pipeline, masking |
| Package mgmt | uv | pip, poetry | 10–100x faster, lockfile, deterministic |

## SSE Event Schema

All streaming responses use this typed event envelope:

```typescript
type SSEEvent =
  | { type: "token";       delta: string }
  | { type: "tool_start";  name: string; input: Record<string, unknown> }
  | { type: "tool_result"; name: string; output: unknown; success: boolean }
  | { type: "done";        session_id: string; provider: string; tokens: number }
  | { type: "error";       message: string; recoverable: boolean }
```

## Resource Budget (16 GB VPS)

| Component | RAM | Role |
|---|---|---|
| FastAPI + Uvicorn (4 workers) | ~1.5 GB | All backend logic |
| PostgreSQL 16 | ~1.5 GB | Relational + vector store |
| SearXNG | ~256 MB | Web search (existing) |
| APScheduler + watchdog | ~80 MB | In-process |
| System + buffers | ~2 GB | Ubuntu, SSH, networking |
| **Available headroom** | **~10.5 GB** | Spikes, caching, growth |
