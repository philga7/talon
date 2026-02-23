
# Talon — Memory Engine

## Three-Tier Architecture

| Tier | What | Storage | Included When | Token Budget |
|---|---|---|---|---|
| **Core Matrix** | Identity, personality, capabilities, preferences | JSON file (`core_matrix.json`) | Every prompt, always | 2,000 max |
| **Episodic** | Past conversations, daily logs, events | PostgreSQL + pgvector | Similarity search, top-5 retrieved | ~500 per retrieval |
| **Working** | Current session context, in-flight data | Python dict (in-process) | Current session only | ~1,000 soft cap |

## Memory Source Format

Core memory is authored as human-readable Markdown and compiled to a JSON matrix.

### Markdown source (`data/memories/identity.md`)
```markdown
# identity
- name: Talon
- purpose: personal AI gateway for a single operator
- personality: direct, concise, technically precise

# behavior
- always cite sources when answering factual questions
- prefer code examples over prose explanations
- ask clarifying questions before long tasks
```

### Compiled matrix (`data/core_matrix.json`)
```json
{
  "schema": ["category", "key", "value", "priority"],
  "rows": [
    ["identity", "name", "Talon", 1],
    ["identity", "purpose", "personal AI gateway", 1],
    ["identity", "personality", "direct, concise, technically precise", 1],
    ["behavior", "citations", "always cite sources for factual answers", 1],
    ["behavior", "format", "prefer code examples over prose", 2]
  ],
  "compiled_at": "2026-02-22T06:00:00Z",
  "token_count": 312
}
```

The matrix format saves ~35% tokens vs. equivalent Markdown by eliminating
repeated category headers and narrative structure.

## compressor.py

```python
import json
import re
from pathlib import Path
from dataclasses import dataclass

@dataclass
class MemoryCompressor:
    max_tokens: int = 2000

    def compile(self, memories_dir: Path) -> dict:
        rows = []
        for md_file in sorted(memories_dir.glob("*.md")):
            category = md_file.stem
            content = md_file.read_text(encoding="utf-8")
            rows.extend(self._parse_file(content, category))

        rows = self._deduplicate(rows)
        rows = self._enforce_budget(rows)

        return {
            "schema": ["category", "key", "value", "priority"],
            "rows": rows,
            "compiled_at": datetime.now(UTC).isoformat(),
            "token_count": self._count_tokens(rows),
        }

    def _parse_file(self, content: str, default_category: str) -> list:
        rows = []
        current_category = default_category
        priority = 2  # default

        for line in content.splitlines():
            # ## heading changes category
            if m := re.match(r'^#{1,2}\s+(.+)', line):
                current_category = m.group(1).strip().lower().replace(" ", "_")
                continue
            # <!-- priority:N --> sets priority for following entries
            if m := re.match(r'<!--\s*priority:(\d+)\s*-->', line):
                priority = int(m.group(1))
                continue
            # - key: value
            if m := re.match(r'^-\s+([^:]+):\s*(.+)', line):
                rows.append([current_category, m.group(1).strip(),
                             m.group(2).strip(), priority])
        return rows

    def _deduplicate(self, rows: list) -> list:
        seen = set()
        unique = []
        for row in rows:
            key = (row[0], row[1])  # category + key
            if key not in seen:
                seen.add(key)
                unique.append(row)
        return unique

    def _enforce_budget(self, rows: list) -> list:
        # Sort: priority 1 first, then 2, then 3
        rows.sort(key=lambda r: r[3])
        result, total = [], 0
        for row in rows:
            tokens = len(json.dumps(row)) // 4
            if total + tokens > self.max_tokens:
                break
            result.append(row)
            total += tokens
        return result

    def _count_tokens(self, rows: list) -> int:
        return len(json.dumps(rows)) // 4

    def compile_text(self, text: str, category: str, max_tokens: int = None) -> dict:
        rows = self._parse_file(text, category)
        rows = self._deduplicate(rows)
        if max_tokens:
            self.max_tokens = max_tokens
        rows = self._enforce_budget(rows)
        return {
            "schema": ["category", "key", "value", "priority"],
            "rows": rows,
            "token_count": self._count_tokens(rows),
        }
```

## Prompt Assembly Order

```python
def build_system_prompt(core_matrix, episodic, working) -> str:
    parts = []

    # 1. Core matrix — always first, always complete
    parts.append(format_matrix(core_matrix))

    # 2. Episodic — top-k by similarity, oldest first for narrative flow
    if episodic:
        parts.append("## Relevant past context")
        for e in sorted(episodic, key=lambda x: x.created_at):
            parts.append(f"[{e.role}]: {e.content}")

    # 3. Working memory — current session state
    if working:
        parts.append("## Current session context")
        for k, v in working.items():
            parts.append(f"{k}: {v}")

    return "\n\n".join(parts)
```

## Scheduled Memory Jobs

| Job | Schedule | What It Does |
|---|---|---|
| `memory_recompile` | Every hour | Re-reads `data/memories/*.md`, rebuilds `core_matrix.json` |
| `episodic_archive` | Daily 3am | Summarizes entries >30 days old, soft-deletes originals |
| `working_memory_gc` | Every 15min | Clears sessions idle >30 minutes |
