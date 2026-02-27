# Phase 9 Migration Context

**Source:** Pre-Phase 9 planning conversation (Feb 26, 2026).
**Purpose:** Complete briefing for the Phase 9 execution thread. Read this before writing any migration script.

---

## OpenClaw Source Repos

- **Fork:** `https://github.com/philga7/openclaw-fork` — the OpenClaw gateway (Node.js/TypeScript)
- **Agent workspace:** `https://github.com/philga7/openclaw-agent` — memories, skills, config (currently **private**)

The agent workspace repo is private. All source data is available directly on the VPS — do not attempt to read it from GitHub.

---

## Data Locations on the VPS

| Data | Path |
|---|---|
| OpenClaw config | `~/.openclaw/openclaw.json` |
| Curated daily memory logs | `~/.openclaw/workspace/memory/YYYY-MM-DD.md` |
| Root-level memory/identity files | `~/.openclaw/workspace/` (IDENTITY.md, MEMORY.md, SOUL.md, USER.md, AGENTS.md, HEARTBEAT.md, TOOLS.md, etc.) |
| Topic-based log notes | `~/.openclaw/workspace/logs/` (ai-intel.md, fork-roadmap.md, software-issues.md) |
| Raw conversation sessions | `~/.openclaw/agents/main/sessions/*.jsonl` and `~/.openclaw/agents/analyst/sessions/*.jsonl` |
| Workspace skills (config branch) | `~/.openclaw/workspace/skills/` (all skills are present on VPS) |
| bird skill | `~/.openclaw/skills/bird/SKILL.md` |

---

## Migration Scripts — Complete Scope

### Naming Correction
The implementation plan lists `episodic_import.sql`. This **must be renamed to `episodic_import.py`**. The source data is JSONL sessions + Markdown daily logs — parsing these and generating pgvector embeddings requires Python. The script uses Talon's existing `EpisodicStore` directly. Document this deviation in the script header.

---

### 1. `migrate_memories.py`

**Sources:**
- Root-level Markdown files in `~/.openclaw/workspace/`: `IDENTITY.md`, `MEMORY.md`, `SOUL.md`, `USER.md`, `AGENTS.md`, `HEARTBEAT.md`, `TOOLS.md`
- Topic notes in `~/.openclaw/workspace/logs/`: `ai-intel.md`, `fork-roadmap.md`, `software-issues.md`

**Destination:** `data/memories/main/` — copy and rename to Talon's expected naming convention.

**Persona split:** Create `data/memories/analyst/` as a copy of the same sources. The two personas share a starting identity; they can be diverged manually over time after migration.

**Final step:** Run `MemoryCompressor` to produce the initial `data/core_matrix.json` for each persona.

---

### 2. `episodic_import.py` *(renamed from episodic_import.sql)*

**Two sources:**

**Source A — Daily memory logs (primary):**
- Path: `~/.openclaw/workspace/memory/YYYY-MM-DD.md`
- Format: Markdown files with date header and `###` section headings per event
- Import strategy: each `###` section becomes one episodic memory entry; timestamp derived from filename + section position; `source=memory_log`; `persona_id` tagged based on content (default: `main`)

**Source B — Raw conversation sessions (optional, gated):**
- Path: `~/.openclaw/agents/{agent_id}/sessions/*.jsonl`
- Format: JSONL, one JSON object per line
- Relevant message types: `{"type":"message","message":{"role":"user",...}}` and `{"type":"message","message":{"role":"assistant",...}}`
- Import strategy: extract user/assistant pairs; tag with `persona_id` from the `agent_id` directory name (`main` or `analyst`); `source=session`
- **Gate this behind a `--include-sessions` CLI flag** — it is voluminous

**Embeddings:** Generate via Talon's embedding pipeline on insert (same path as `EpisodicStore.save_turn`).

**Session JSONL structure (reference):**
```jsonl
{"type":"session","version":3,"id":"<uuid>","timestamp":"...","cwd":"..."}
{"type":"model_change","id":"...","provider":"ollama","modelId":"qwen3.5:397b-cloud"}
{"type":"message","id":"...","message":{"role":"user","content":[{"type":"text","text":"..."}]}}
{"type":"message","id":"...","message":{"role":"assistant","content":[{"type":"text","text":"..."},{"type":"toolCall",...}]}}
{"type":"message","id":"...","message":{"role":"toolResult","toolCallId":"...","content":[{"type":"text","text":"..."}]}}
```

---

### 3. `migrate_skills.py`

**OpenClaw agent definitions (from `openclaw.json`):**

| Persona | Model | Extra skills vs main |
|---|---|---|
| `main` | `ollama/qwen3.5:397b-cloud` (primary), `ollama/glm-5:cloud` (fallback) | — |
| `analyst` | `ollama/glm-4.7:cloud` | `neuron-brief-tool`, `system-guardian` |

**Skill disposition table:**

| OpenClaw skill | Talon action |
|---|---|
| `skill:bird` | **Port** as Talon `BaseSkill` using `asyncio.create_subprocess_exec`; manifest declares `requires_binary: bird`; binary must be installed on VPS |
| `skill:neuron-brief-tool` | **Port** as Talon `BaseSkill`; `execute()` returns formatted briefing as `SkillResult`; Slack posting handled by integration layer or APScheduler job — skill does NOT post directly. Also a natural APScheduler daily job candidate. |
| `skill:hostinger-email` | Already ported (Phase 7) — verify presence only |
| `skill:yahoo-finance` | Already ported (Phase 4) — verify presence only |
| `weather-enhanced` | Already ported (Phase 7) — verify presence only |
| `searxng-enhanced` / `searxng-search` | Already ported (Phase 4) — verify presence only |
| `news-sentinel` | Already ported (Phase 7) — verify presence only |
| `yahoo-finance-batch` | Already ported (Phase 7) — verify presence only |
| `portfolio-sma200`, `portfolio-sma200-reporter` | Generate stubs; depend on yahoo-finance; flag `PARTIAL_PORT` |
| `linkedin-monitor`, `security-monitor`, `newsletter-fetcher`, `software-update-checker` | Generate stubs; flag `MANUAL_PORT_REQUIRED` — depend on OpenClaw exec/session tools |
| `foundry-openclaw`, `group:fs`, `group:runtime`, `group:sessions` | **Skip** — OpenClaw built-ins, no Talon equivalent |
| `read-safe`, `sessions-safe`, `system-guardian` | **Skip** — OpenClaw hook/plugin system |
| `journal-personal`, `journal-work`, `journal`, `phil-home`, `reminder` | **Skip** — OpenClaw prompt-injection skills that rely on `group:fs` and `group:runtime` |
| `chrome-browser`, `cloudflare-markdown`, `docker-status-safe`, `cron-placement-guide`, `supercronic-update`, `test-hook-trigger`, `session-maintenance`, `foundry-backup`, `gog`, `link-format-reference`, `valley-it-competitors` | **Skip** — infrastructure or too environment-specific |

**`bird` SKILL.md (for reference when writing the Talon port):**
```
name: bird
description: X/Twitter CLI for reading, searching, and posting via cookies or Sweetistics.
Commands: bird whoami, bird read <url>, bird thread <url>, bird search "query" -n 5
Posting: bird tweet "text", bird reply <id> "text"
Auth: browser cookies (Firefox/Chrome) or Sweetistics API (SWEETISTICS_API_KEY env var)
```

**`neuron-brief-tool` SKILL.md summary:**
- Fetches "The Neuron" AI newsletter from Hostinger IMAP using `hostinger-email`
- If no newsletter found in the specified timeframe, exits silently (returns empty `SkillResult`)
- Formats output in Slack-specific syntax (`*bold*`, `_italic_`, `<URL|text>` links)
- In OpenClaw it posted directly to Slack channel `C0AGF1X1G5P` (`#ai-news`) — in Talon the skill returns the formatted content; the caller (scheduler or chat) handles delivery
- Analyst persona only

---

### 4. `migrate_config.py`

**Source:** `~/.openclaw/openclaw.json`

**Secret file mappings** (`config/secrets/`, chmod 600 each):

| openclaw.json field | Talon secret file |
|---|---|
| `env.ANTHROPIC_API_KEY` | `anthropic_api_key` |
| `env.OPENROUTER_API_KEY` | `openrouter_api_key` |
| `channels.slack.botToken` | `slack_bot_token` |
| `channels.slack.appToken` | `slack_app_token` |
| `channels.telegram.botToken` | `telegram_bot_token` |

**Provider mappings** (`config/providers.yaml`):

The `ollama` provider in OpenClaw is NOT local Ollama — it is an OpenAI-compatible cloud API at `https://ollama.com/v1`. Map as:
- LiteLLM provider type: `openai`
- `api_base`: `https://ollama.com/v1`
- Primary model: `qwen3.5:397b-cloud` (main agent default)
- Fallback model: `glm-5:cloud`
- Analyst override model: `glm-4.7:cloud`

Also map OpenRouter as a provider using `env.OPENROUTER_API_KEY`.
Anthropic maps directly via `env.ANTHROPIC_API_KEY`.

**Persona bindings** (`config/personas.yaml` — see also `multi-persona_support_9d17f6c4.plan.md`):

`main` persona Slack channel IDs: `C0AGF1Z4FDF`, `C0AFYCWEV2R`

`analyst` persona Slack channel IDs: `C0AGF0REYBT`, `C0AGWBB0648`, `C0AFVM42G4B`, `C0AGF1EETA5`, `C0AGWC921TJ`, `C0AG5N5KVDJ`, `C0AGF1X1G5P`, `C0AG5NA3U7N`, `C0AFVN490N7`, `C0AG24C1GFL`, `C0AGWCQ1ZDE`, `C0AFVNG7JHZ`, `C0AG5NR42RJ`, `C0AG5NSKVCL`

**Other config to migrate:**
- Slack channel allowlist (`channels.slack.channels`) → Talon Slack integration config
- Session reset rules (idle 120m DM, 60m group) → `config/talon.toml`
- SearXNG base URL (`http://localhost:8080`) → existing skill config

---

### 5. `validate_migration.py`

Checks (all must pass before OpenClaw decommission):

1. `data/memories/main/` exists and contains at least the core identity files
2. `data/memories/analyst/` exists
3. `MemoryCompressor` compiles both memory dirs without error
4. `data/core_matrix.json` exists and has non-zero `token_count`
5. `episodic_memory` table has > 0 rows for both `main` and `analyst` persona tags
6. All ported skills load cleanly via `SkillRegistry` (no import errors)
7. `bird` skill stub present and `requires_binary` flag set
8. `neuron-brief-tool` skill present and loadable
9. All secret files exist in `config/secrets/` with correct permissions (600)
10. `config/providers.yaml` parses without error and has at least 2 providers
11. `config/personas.yaml` parses and contains `main` and `analyst` with valid channel binding arrays
12. Health endpoint (`/api/health`) returns 200 after migration

---

## Key Decisions & Notes

- **`episodic_import.sql` is renamed to `episodic_import.py`** — document this in the script header
- **`bird` requires the `bird` CLI binary on the VPS** — the migration script flags this; operator must verify installation separately
- **`neuron-brief-tool` does not post to Slack directly in Talon** — it returns `SkillResult`; the integration or scheduler handles delivery. Consider wiring it as a daily APScheduler job posting to `#ai-news` (`C0AGF1X1G5P`)
- **OpenClaw's `ollama` provider is a cloud API, not local Ollama** — base URL is `https://ollama.com/v1`, OpenAI-compatible
- **The `openclaw-agent` repo is private** — read all source data from the VPS directly, never from GitHub
- **Embeddings are regenerated fresh** — do not attempt to preserve OpenClaw vectors; Talon's embedding pipeline re-embeds everything on import
- **Multi-persona architecture** is fully implemented in Phase 7 — see `multi-persona_support_9d17f6c4.plan.md` for the `PersonaRegistry`, persona-scoped memory, and channel-binding resolution details
