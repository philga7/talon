# Secrets Setup

Create `config/secrets/` and add secret files before running Talon.

## Directory Setup

```bash
mkdir -p config/secrets
chmod 700 config/secrets
```

## Required Files (Phase 1+)

| File | Purpose | Format |
|------|---------|--------|
| db_password | PostgreSQL password | Plain text, single line |
| llm_api_keys | LLM provider keys (Phase 2) | JSON: `{"provider": "key"}` |

## Create db_password

```bash
echo "your_secure_postgres_password" > config/secrets/db_password
chmod 600 config/secrets/db_password
```

The password must match what Docker Compose uses (see `docker-compose.yml`).

## Local Development / Tests

Set `TALON_DB_PASSWORD=test` in the environment to override for tests, or use the same password in `db_password` for local dev.
