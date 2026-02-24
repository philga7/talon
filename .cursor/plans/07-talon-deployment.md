
# Talon — Deployment

## Deployment Model (Recommended: Hybrid)

FastAPI runs natively via systemd. Auxiliary stateful services run in Docker.

```
┌─────────────────────────────────────────────────────┐
│           Hostinger KVM 4 VPS                       │
│       Ubuntu 22.04 · 16GB RAM · 4vCPU               │
│                                                     │
│  nginx (port 80/443)                                │
│    /           → frontend/dist/ (static)            │
│    /api/*      → localhost:8088 (FastAPI)            │
│                                                     │
│  talon.service (systemd)                            │
│    uvicorn app.main:app --port 8088 --workers 4     │
│                                                     │
│  Docker Compose                                     │
│    postgres:16-pgvector  (127.0.0.1:5432)          │
│    searxng               (127.0.0.1:8080)           │
└─────────────────────────────────────────────────────┘
```

## systemd Unit File

```ini
# deploy/systemd/talon.service
[Unit]
Description=Talon AI Gateway
After=network.target docker.service
Requires=docker.service

[Service]
Type=exec
User=root
WorkingDirectory=/root/talon/backend
Environment=PYTHONPATH=/root/talon/backend
ExecStartPre=/usr/bin/docker compose -f /root/talon/docker-compose.yml up -d
ExecStart=/root/talon/.venv/bin/uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8088 \
    --workers 4 \
    --loop uvloop
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=talon

[Install]
WantedBy=multi-user.target
```

## docker-compose.yml

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    restart: always
    environment:
      POSTGRES_DB: talon
      POSTGRES_USER: talon
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    secrets:
      - db_password
    ports:
      - "127.0.0.1:5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U talon"]
      interval: 10s; timeout: 5s; retries: 5

  searxng:
    image: searxng/searxng:latest
    restart: always
    ports:
      - "127.0.0.1:8080:8080"
    volumes:
      - searxng_data:/etc/searxng

secrets:
  db_password:
    file: ./config/secrets/db_password

volumes:
  postgres_data:
  searxng_data:
```

## nginx Configuration

```nginx
server {
    listen 80;
    server_name _;
    root /root/talon/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8088;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    location /api/sse/ {
        proxy_pass http://127.0.0.1:8088;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
    }
}
```

## First-Time Setup

```bash
git clone <repo> /root/talon && cd /root/talon
curl -LsSf https://astral.sh/uv/install.sh | sh
cd backend && uv sync
cd ../frontend && npm install

mkdir -p config/secrets && chmod 700 config/secrets
echo "your_pg_password"        > config/secrets/db_password
echo '{"provider": "key"}'    > config/secrets/llm_api_keys
chmod 600 config/secrets/*
chmod 600 config/talon.toml

docker compose up -d
make migrate
make build

cp deploy/systemd/talon.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable talon.service
systemctl --user start talon.service

cp deploy/nginx.conf /etc/nginx/sites-available/talon
ln -s /etc/nginx/sites-available/talon /etc/nginx/sites-enabled/
nginx -t && nginx -s reload

make status && make health
```

## Migration Phases

| Phase | Scope | Goal |
|---|---|---|
| 1 — Foundation | FastAPI skeleton, config, logging, PostgreSQL, health endpoint | Running shell |
| 2 — LLM Gateway | LiteLLM, circuit breaker, fallback chain, SSE | Models connected |
| 3 — Memory | Core matrix, episodic store, working memory | Memories migrated |
| 4 — Skills | Port OpenClaw tools to Python BaseSkill | All tools working |
| 5 — Integrations | Discord (port), Slack (new) | Both platforms live |
| 6 — Scheduler + Sentinel | APScheduler, watchdog, hot-reload | Cron jobs + live reload |
| 7 — UI | Chat, memory viewer, log viewer, health dashboard | Full web UI |
| 8 — Hardening | Load testing, error injection, security audit | Production-ready |
