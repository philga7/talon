"""Security hardening package (IronClaw spec).

Modules:
  leak_scanner    — Pre-dispatch outbound request scanning
  ssrf_guard      — RFC-1918 / loopback / link-local egress filter
  skill_http_client — Per-skill allowed_hosts enforcement
  prompt_guard    — Tiered prompt injection detection
  audit_log       — Chained-hash tool-call audit trail
"""
