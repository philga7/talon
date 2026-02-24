# Talon Security Hardening: Principles Borrowed from IronClaw

> **Document Version:** 1.0.0  
> **Date:** 2026-02-24  
> **Applies To:** Talon (philga7/talon) — Python/FastAPI AI Agent Framework  
> **Reference Architecture:** [nearai/ironclaw](https://github.com/nearai/ironclaw) v0.1.3  

---

## Overview

This document catalogs the security patterns identified in IronClaw's architecture that
should be backported into Talon. Each principle is adapted for Talon's Python/FastAPI stack
rather than direct Rust/WASM translation. Implement in priority order — highest risk first.

---

## 1. AES-256-GCM Credential Vault

### Problem
Talon currently uses Pydantic `BaseSettings` with `secrets_dir` and `chmod 600/700`
filesystem permissions. While an improvement over OpenClaw's `${VAR}` expansion, secrets
still exist as plaintext files on disk. A compromised process or misconfigured bind mount
exposes all credentials directly.

### IronClaw's Approach
Secrets are encrypted at rest with AES-256-GCM. The vault is decrypted in-process at
startup using a master key (derived from a passphrase via Argon2id). The LLM context and
tool execution environment **never receive raw secret values** — only opaque references.
Injection happens exclusively at the host network boundary just before an HTTP call is
dispatched.

### Talon Implementation Plan

```python
# config/vault.py
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
import os, json, base64

class CredentialVault:
    def __init__(self, vault_path: str, passphrase: bytes):
        kdf = Argon2id(salt=self._load_salt(vault_path), length=32,
                       iterations=3, lanes=4, memory_cost=65536)
        self._key = kdf.derive(passphrase)
        self._aesgcm = AESGCM(self._key)
        self._secrets: dict[str, str] = self._decrypt_vault(vault_path)

    def get(self, name: str) -> str:
        if name not in self._secrets:
            raise KeyError(f"Secret '{name}' not found in vault")
        return self._secrets[name]

    def inject(self, headers: dict, secret_refs: list[str]) -> dict:
        """Inject resolved secrets into headers at call boundary only."""
        return {k: self.get(v) if v in secret_refs else v for k, v in headers.items()}
```

**Key rules:**
- Master passphrase loaded from environment variable only (never written to disk)
- Vault file stored at `config/secrets/vault.enc` (chmod 600)
- Salt stored separately at `config/secrets/vault.salt` (chmod 600)
- Secret names (not values) are what tools receive — resolved at HTTP dispatch time
- Rotate vault on any suspected compromise by re-encrypting with a new passphrase

---

## 2. Per-Tool Outbound Leak Detection

### Problem
Any tool that makes an HTTP call could — through prompt injection or a malicious skill —
exfiltrate credentials or PII in request bodies, query params, or headers. OpenClaw had no
outbound scan. Talon inherits this gap.

### IronClaw's Approach
All outbound HTTP traffic passes through a leak scanner before dispatch. The scanner
maintains a compiled pattern set of known-secret signatures and blocks/redacts any request
where a match is found.

### Talon Implementation Plan

```python
# tools/security/leak_scanner.py
import re, hashlib
from dataclasses import dataclass
from enum import Enum

class LeakAction(Enum):
    BLOCK = "block"
    REDACT = "redact"
    WARN = "warn"

@dataclass
class LeakScanResult:
    clean: bool
    action: LeakAction | None
    matched_pattern: str | None

class OutboundLeakScanner:
    def __init__(self, vault: "CredentialVault"):
        # Build pattern set from secret digests — never store raw values in scanner
        self._patterns = self._compile_patterns(vault)
        self._generic_patterns = [
            re.compile(r"sk-[a-zA-Z0-9]{32,}"),          # OpenAI-style keys
            re.compile(r"Bearer\s+[a-zA-Z0-9\-_]{20,}"), # Bearer tokens
            re.compile(r"[a-zA-Z0-9]{40}"),               # Generic API keys (40-char hex)
        ]

    def scan(self, payload: str) -> LeakScanResult:
        for pattern in self._patterns:
            if pattern.search(payload):
                return LeakScanResult(clean=False, action=LeakAction.BLOCK,
                                       matched_pattern="vault_secret")
        for pattern in self._generic_patterns:
            if pattern.search(payload):
                return LeakScanResult(clean=False, action=LeakAction.WARN,
                                       matched_pattern=pattern.pattern)
        return LeakScanResult(clean=True, action=None, matched_pattern=None)
```

**Integration point:** Wrap the `httpx.AsyncClient` used by tool execution with a
pre-dispatch hook that calls `LeakScanner.scan()` on the serialized request body + headers.
Block on `LeakAction.BLOCK`, log + alert on `LeakAction.WARN`.

---

## 3. Per-Skill Endpoint Allowlist

### Problem
Without sandboxing, a malicious or compromised skill can make arbitrary HTTP calls to
any host — internal VPS services, metadata endpoints (169.254.169.254), or exfil servers.

### IronClaw's Approach
Each tool/skill declares an explicit list of allowed hostnames. The WASM capability system
enforces this at the sandbox boundary. No declaration = no network access.

### Talon Implementation Plan

Add an `allowed_hosts` field to skill manifests:

```yaml
# skills/yahoo-finance/skill.yaml
name: yahoo-finance
version: 1.0.0
description: Fetch stock quotes and financial data
allowed_hosts:
  - query1.finance.yahoo.com
  - query2.finance.yahoo.com
timeout_seconds: 10
```

```python
# tools/skill_loader.py
class SkillHTTPClient:
    def __init__(self, skill_manifest: SkillManifest):
        self._allowed = set(skill_manifest.allowed_hosts)

    async def get(self, url: str, **kwargs):
        host = urllib.parse.urlparse(url).hostname
        if host not in self._allowed:
            raise PermissionError(
                f"Skill '{self._skill_name}' attempted request to disallowed host: {host}"
            )
        async with httpx.AsyncClient() as client:
            return await client.get(url, **kwargs)
```

**Bonus:** Block RFC-1918 ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16) and
link-local (169.254.0.0/16) globally across all skills to prevent SSRF against VPS-internal
services.

---

## 4. Prompt Injection Defense Pipeline

### Problem
Any user message or tool response that contains injected instructions can hijack the
agent's next action. Talon's current architecture has no formalized defense layer.
IronClaw rates this as single highest-severity threat.

### IronClaw's Approach
A tiered policy engine evaluates every inbound message through a severity pipeline:
**Block → Warn → Review → Sanitize**, applied in order.

### Talon Implementation Plan

```python
# security/prompt_guard.py
from enum import Enum
import re

class Severity(Enum):
    BLOCK = 4      # Halt execution, log, alert operator
    WARN = 3       # Log, pass with flag
    REVIEW = 2     # Queue for operator review before acting
    SANITIZE = 1   # Strip pattern, continue

RULES: list[tuple[re.Pattern, Severity, str]] = [
    # Block: direct instruction override attempts
    (re.compile(r"ignore (all )?previous instructions", re.I), Severity.BLOCK, "instruction_override"),
    (re.compile(r"you are now (a|an|the)", re.I),              Severity.BLOCK, "persona_hijack"),
    (re.compile(r"system prompt", re.I),                       Severity.WARN,  "system_prompt_probe"),
    (re.compile(r"</?system>", re.I),                          Severity.BLOCK, "xml_injection"),
    (re.compile(r"\[INST\]|<<SYS>>",re.I),                   Severity.BLOCK, "llama_injection"),
    # Sanitize: exfil patterns
    (re.compile(r"curl\s+http", re.I),                        Severity.SANITIZE, "curl_exfil"),
    (re.compile(r"wget\s+http", re.I),                        Severity.SANITIZE, "wget_exfil"),
]

class PromptGuard:
    def evaluate(self, content: str) -> tuple[Severity | None, str]:
        highest = None
        for pattern, severity, label in RULES:
            if pattern.search(content):
                if highest is None or severity.value > highest[0].value:
                    highest = (severity, label)
        return highest if highest else (None, "clean")

    def sanitize(self, content: str) -> str:
        for pattern, severity, _ in RULES:
            if severity == Severity.SANITIZE:
                content = pattern.sub("[REDACTED]", content)
        return content
```

**Apply at:** (1) inbound user messages, (2) tool response bodies before injecting into
LLM context, (3) memory retrieval results before context assembly.

---

## 5. Full Tool-Call Audit Log

### Problem
When something goes wrong — a skill misbehaves, a prompt injection succeeds partially,
or a credential leaks — you need a forensic record. Currently Talon logs at the
application level but tool inputs/outputs are not structured for audit.

### IronClaw's Approach
Every tool call is logged with a cryptographically sequenced audit record: tool name,
inputs (with secrets redacted), outputs (leak-scanned), duration, session ID, and outcome.

### Talon Implementation Plan

```python
# security/audit_log.py
import hashlib, time, json
from structlog import get_logger

logger = get_logger("talon.audit")

class AuditLog:
    def __init__(self, secret_masker: "SecretMasker"):
        self._masker = secret_masker
        self._chain_hash = "genesis"

    def record(self, session_id: str, tool: str,
               inputs: dict, output: str, duration_ms: int, outcome: str):
        # Chain hash for tamper evidence (not cryptographic proof, but useful signal)
        entry_data = json.dumps({
            "session": session_id, "tool": tool,
            "inputs": self._masker.mask(str(inputs)),
            "output_hash": hashlib.sha256(output.encode()).hexdigest(),
            "duration_ms": duration_ms, "outcome": outcome,
            "ts": time.time(), "prev": self._chain_hash
        }, sort_keys=True)
        self._chain_hash = hashlib.sha256(entry_data.encode()).hexdigest()
        logger.info("tool_audit", **json.loads(entry_data), entry_hash=self._chain_hash)
```

**Store audit logs separately** from application logs — write to `logs/audit/` with
log rotation. Never purge audit logs on session reset.

---

## 6. SSRF / Internal Network Protection

### Problem
On your Hostinger VPS, services like SearXNG (`:8080`) and the gateway (`:18789`) are
bound to localhost. A SSRF vulnerability in any skill could pivot to these internal
services. This is especially dangerous if a skill can make requests to
`http://localhost:8080` or the Docker bridge network (`172.18.0.0/16`).

### Talon Implementation Plan

Add a global network egress filter applied before every outbound HTTP request, regardless
of skill:

```python
# security/ssrf_guard.py
import ipaddress, socket

BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local / AWS metadata
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

def is_ssrf_blocked(hostname: str) -> bool:
    try:
        resolved = ipaddress.ip_address(socket.gethostbyname(hostname))
        return any(resolved in net for net in BLOCKED_NETWORKS)
    except Exception:
        return True  # Fail closed on resolution errors
```

**Apply in** `SkillHTTPClient` before the allowlist check — deny internal IPs even if
somehow added to a skill's allowed_hosts.

---

## Implementation Priority

| Priority | Principle | Talon Phase Target | Risk Without It |
|---|---|---|---|
| 🔴 1 | Outbound Leak Detection | Phase 4 (tools) | Credential exfil via any HTTP skill |
| 🔴 2 | SSRF / Internal Network Guard | Phase 4 (tools) | Pivot to SearXNG/gateway/Docker |
| 🟠 3 | Prompt Injection Pipeline | Phase 6 (security) | Agent hijacking via tool responses |
| 🟠 4 | Per-Skill Endpoint Allowlist | Phase 4 (tools) | Unrestricted outbound from skills |
| 🟡 5 | AES-256-GCM Credential Vault | Phase 5 (hardening) | Plaintext secrets on disk |
| 🟡 6 | Full Tool-Call Audit Log | Phase 5 (hardening) | No forensic trail post-incident |

---

## Notes

- All code samples are **illustrative starting points**, not drop-in production code.
  Adapt to Talon's actual service/dependency injection patterns.
- The `SecretMasker` structlog processor already in Talon covers log-level masking;
  the vault and leak scanner extend this to runtime and network layers.
- Reassess the sandbox story (Phase 4+) — Docker process isolation per skill execution
  is a reasonable Talon-native alternative to IronClaw's WASM sandboxing.
- This document should be revisited when IronClaw reaches v1.0 for any new patterns
  worth adopting.

---

*Generated 2026-02-24 | OpenClaw Architect Space | Talon Security Reference*
