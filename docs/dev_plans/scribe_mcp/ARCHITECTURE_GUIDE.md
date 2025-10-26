# 🏗️ Scribe MCP Architecture Guide
**Project:** Scribe MCP Server  
**Author:** CortaLabs (Codex)  
**Version:** Draft v0.3  
**Last Updated:** 2025-10-22 08:45 UTC

---

## System Overview
Scribe exposes a Model Context Protocol (MCP) server that lets AI agents manage structured progress logs and supporting docs with near-zero setup. The stack is intentionally lean:

- **Server Core (`MCP_SPINE/MCP_SPINE/scribe_mcp/server.py`):** boots the stdio MCP server, wires lifecycle hooks, and shares a `StateManager`.
- **Tool Suite (`MCP_SPINE/scribe_mcp/tools/`):** atomic MCP tools for project selection, log append/rotation, recent readouts, documentation scaffolding, GitHub sync stub, and reminder-aware responses.
- **Storage Layer (`MCP_SPINE/scribe_mcp/db/`, `MCP_SPINE/scribe_mcp/utils/`):** async-friendly helpers for file IO, DB schemas, and (soon) backend-specific persistence.
- **Reminder Engine (`MCP_SPINE/scribe_mcp/reminders.py`):** centralises freshness checks and emits contextual nags that ship with every tool response.
- **Templates (`scribe_mcp/templates/` + `docs/dev_plans/1_templates`):** markdown scaffolds for architecture guides, phase plans, and logs.
- **State Cache (`scribe_mcp/state/`):** JSON-backed memo of the current project, known configs, and recent tool history for reminder context.

---

## Directory Structure (2025-10-22)
```
scribe_mcp/
  __init__.py
  server.py
  config/
    settings.py
  db/
    __init__.py
    init.sql
    ops.py
    pool.py
  state/
    __init__.py
    manager.py
  templates/
    __init__.py
  reminders.py
  storage/
    __init__.py
    base.py
    models.py
    postgres.py
    sqlite.py
  tools/
    __init__.py
    append_entry.py
    constants.py
    generate_doc_templates.py
    get_project.py
    list_projects.py
    project_utils.py
    query_entries.py
    read_recent.py
    rotate_log.py
    set_project.py
    sync_to_github.py
  utils/
    __init__.py
    files.py
    logs.py
    search.py
    time.py
docs/
  dev_plans/
    1_templates/
      ARCHITECTURE_GUIDE_TEMPLATE.md
      CHECKLIST_TEMPLATE.md
      PHASE_PLAN_TEMPLATE.md
      PROGRESS_LOG_TEMPLATE.md
    scribe_mcp/
      ARCHITECTURE_GUIDE.md
      PHASE_PLAN.md
      CHECKLIST.md
      PROGRESS_LOG.md
scripts/
  scribe.py
tests/
  conftest.py
  test_tools.py
```

---

## Request Flow
1. **Tool Invocation:** MCP client calls a tool such as `append_entry`.
2. **State Resolution:** The tool pulls project metadata from `StateManager`, falling back to the per-project configs in `config/projects/*.json`.
3. **IO Operations:**  
   - Progress entries append to Markdown via async file helpers.  
   - When a DB backend is active, the line is mirrored into persistence and metrics are updated.
4. **Response:** Tool returns lightweight JSON with the written line/path plus reminder metadata describing overdue docs, stale logs, or project context.

---

## Reminder Engine
Every MCP tool now routes through the reminder engine before responding. The flow:

1. `state/manager.py` records the tool invocation with timestamps, session start markers, and a rolling history of the last 10 calls.
2. `reminders.get_reminders` gathers context: log frequency, document completeness, hashed doc snapshots vs. the prior audit, phase status, and stale file mtimes.
3. Weighted severity (score 1–10) is assigned per reminder. Warm-up logic downgrades alerts when a session has just resumed; thresholds are overrideable per project.
4. Tone is configurable (`defaults.reminder.tone`) so the same engine can deliver neutral, friendly, direct, or branded messaging without code changes.
5. Doc hygiene checks ensure architecture → phase plan → checklist remain aligned and flag semantic drift, not just timestamps.
6. Every response includes a project context line (`🎯 Project …`) so auditors always know where work is happening, how many entries exist, and how long the session has been running.

Reminder generation remains non-blocking: tools still succeed but agents receive contextual nudges in the `reminders` array. The same module powers `set_project` warnings, `generate_doc_templates` follow-ups, GitHub sync messaging, and the upcoming compliance/audit surface.

---

## Storage Strategy (Hybrid)
- **Default:** SQLite (no external deps, tuned for local-first append workflows).  
- **Optional:** PostgreSQL (multi-user metrics, dashboards, remote installs).  
- **Adapter Layer:** `StorageBackend` abstraction drives a single tool surface while delegating to the configured engine.

Both backends now implement:
- Project upsert/listing APIs to keep DB mirrors aligned with file roots.
- Insert paths that capture SHA256 integrity, meta payloads, and timestamp variants.
- Metrics counters for success/warn/error tallies.
- Recent-fetch helpers for quick dashboards.
- **Advanced queries** that support date ranges, multi-emoji/agent filters, and meta equality checks.

The backend factory in `storage/__init__.py` inspects `settings.storage_backend`, falling back to SQLite when Postgres is unconfigured. Queries cap at 500 results and over-fetch to honour downstream message/regex filters consistently across engines.

### Advanced Query Pipeline
1. `tools/query_entries.py` normalises filters (timestamps, emoji/status, regex validation).
2. Available backend executes `StorageBackend.query_entries`, returning structured rows.
3. File-only installs fall back to parsing Markdown logs (`utils/logs.py`) and reuse shared matching helpers (`utils/search.py`).
4. Responses include raw lines to maintain compatibility with legacy tooling while surfacing structured fields for MCP clients.

### Rate & Safety Guards
- Regex validation happens at the tool layer; invalid patterns short-circuit with descriptive errors.
- Backend queries enforce absolute limits and filter meta keys using a conservative allowlist (`[A-Za-z0-9_.:-]`).
- File fallback centralises parsing logic to avoid drift from append formatting rules.

## Configuration Guardrails
The `set_project` tool now validates inputs before mutating disk or state:
- Rejects re-use of progress log or docs directories already claimed by another project (state or config-backed).
- Warns on overlapping repository roots to surface potential boundary conflicts.
- Verifies write permissions for root/docs/log parents before scaffolding.
- Surfaces warnings in the response payload so agents can notify operators or prompt remediation.

Validation runs prior to doc bootstrap and DB upserts, preventing partially-initialised projects from polluting state.

---

## Documentation Contract
- Update this guide whenever system architecture, tool surface, or directory structure changes.
- Ensure the phase plan and checklist remain aligned with the sections above; discrepancies should trigger a planning retro.
- Progress log entries must reference affected components (e.g., `meta: component=storage_backend`) so future audits map work back to design intent.

---

## Error Handling & Observability
- Tools never raise raw exceptions to the client; they return structured `{"ok": False, "error": ...}` payloads.
- File operations use thread executors to avoid blocking the event loop.
- Future upgrades will add structured logging around DB failures, plus optional GitHub sync events.

---

## Open Questions
1. Storage backend resiliency (connection pooling, retry policies) for Postgres under load.  
2. SQLite schema migrations/versioning strategy when fields evolve.  
3. Long-running MCP usage: per-agent rate limiting (roadmapped) and batching strategies.  
4. GitHub integration toggles (auth, network gating).  
5. Optional summarisation/LLM enrichment once baseline workflow is rock solid.

---

## Next Steps
- Harden storage tests across both backends (including advanced query coverage).  
- Expand docs generation tool to support overwrite prompts or versioning.  
- Add structured config documentation for MCP clients (env vars, state paths).  
- Harden tests (Austin-run) for concurrent append, validation guardrails, and backend parity.  
- Draft GitHub sync design doc once network allowances are green-lit.
