# Talon

Self-hosted personal AI gateway for a single operator. Licensed under [AGPL v3](LICENSE). Inspired by OpenClaw (Node.js/TypeScript). Python/TypeScript stack on a single Hostinger VPS.

**Status: Phase 1 complete.** Foundation is implemented: FastAPI skeleton, config, logging, PostgreSQL+Alembic, health endpoint, deploy configs.

- **Stack:** FastAPI, PostgreSQL+pgvector, React+Vite, SSE streaming, LiteLLM, APScheduler
- **Docs:** See [AGENTS.md](AGENTS.md) for full spec and [`.cursor/plans/`](.cursor/plans/) for phased implementation roadmap (8 phases)
- **CI:** GitHub Actions runs backend lint (ruff, pyright) + tests (`make test`) on pushes to `main` and `feature/**` and on all PRs.

## Quick Start (Phase 1)

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

# 5. Verify
curl http://localhost:8000/api/health  # {"status":"healthy"}
make test  # runs pytest
```

---

Copyright © 2026 Philip Clapper. All rights reserved. See [LICENSE](LICENSE) for terms of use.
