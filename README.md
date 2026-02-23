# Talon

Self-hosted personal AI gateway for a single operator. Replaces OpenClaw (Node.js/TypeScript) with a Python/TypeScript stack on a single Hostinger VPS.

**Status: Planning.** Architecture and implementation strategy are defined; development has not started.

- **Stack:** FastAPI, PostgreSQL+pgvector, React+Vite, SSE streaming, LiteLLM, APScheduler
- **Docs:** See [AGENTS.md](AGENTS.md) for full spec and [`.cursor/plans/`](.cursor/plans/) for phased implementation roadmap (8 phases)
- **Next step:** Phase 1 — Foundation (FastAPI skeleton, config, logging, PostgreSQL, health endpoint, deploy configs)
