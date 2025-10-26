# Scribe MCP Whitepaper

## Executive Summary
Scribe MCP is a Model Context Protocol (MCP) server designed to give Codex and other agentic systems a disciplined, auditable workflow for documenting software projects. It extends the traditional “append-only progress log” into a full documentation governance layer: every meaningful action is captured, cross‑referenced with architecture/phase plans, and fed through a configurable reminder engine that nudges teams to keep implementation and planning in sync. Scribe now lives inside the `MCP_SPINE` package, providing a reusable backbone for hosting multiple MCP servers—Scribe is the first resident of this ecosystem.

Key capabilities:
- **Structured logging** via `append_entry`, including optional database mirroring.
- **Project coordination** with `set_project`, `list_projects`, and `get_project`.
- **Inline documentation tooling** (`generate_doc_templates`, reminder engine) that enforces architecture/phase/checklist hygiene.
- **Advanced log analytics** (`query_entries`, `read_recent`) with flexible filtering and metadata search.
- **Reminder governance** that computes severity scores, tracks document drift, and keeps cadence with project activity.
- **Seamless Codex integration** through the MCP standard, allowing Codex CLI/IDE to mount Scribe as a native tool.

This whitepaper maps out the high-level architecture, workflow, configuration surfaces, and extension points that underpin the project.

---

## Architectural Overview

```
MCP_SPINE/
  └── scribe_mcp/
        server.py
        config/settings.py
        state/manager.py
        storage/{base.py, sqlite.py, postgres.py}
        reminders.py
        tools/*.py
        utils/*.py
        templates/
```

### MCP Server Core (`MCP_SPINE/scribe_mcp/server.py`)
- Boots a stdio-based MCP server using the official `mcp` Python SDK when available (falls back to a permissive stub if the SDK is missing for local testing).
- Registers all tools under a single `Server` instance. During import it dynamically adds `@app.tool` support if the SDK version lacks the helper decorators (maintaining compatibility with older SDKs).
- Manages server lifecycle hooks (`setup`, `close`), delegating to the active storage backend.
- Exposes global singletons:
  - `state_manager`: orchestrates persistent state.
  - `storage_backend`: chosen at startup (SQLite by default, Postgres when configured).

### Configuration Layer (`config/settings.py`)
- Parses environment variables with fallbacks for repository discovery (`SCRIBE_ROOT`, `SCRIBE_STATE_PATH`).
- Determines storage backend selection (`SCRIBE_STORAGE_BACKEND`, `SCRIBE_DB_URL`).
- Sets operational limits (log rotation size, rate limiting, reminder defaults).
- Exposes reminder tuning knobs (tone, severity weights, idle reset thresholds) via `Settings.reminder_defaults`.

### State Manager (`state/manager.py`)
- Reliable JSON-backed state file supporting:
  - Current project selection and metadata cache (`config/projects/*.json`).
  - Rolling history of the last 10 tool invocations, each with timestamp—feeds reminder cadence.
  - Session tracking (`session_started_at`, `last_activity_at`) to detect restarts and idle thresholds.
  - Atomic updates (`record_tool`, `set_current_project`, `update_project_metadata`) guarded by an `asyncio.Lock` for safe concurrent access.
- Normalizes tool history entries to ensure backwards compatibility as state evolves.

### Storage Backends (`storage/`)
- **SQLite backend** (`sqlite.py`): 
  - On-demand connections with busy timeout.
  - Mirrored schema (projects, entries, metrics) for local-first deployments.
  - JSON meta storage and timestamp indexes for fast queries.
- **Postgres backend** (`postgres.py`): 
  - Asyncpg pool management.
  - Utilizes SQL helpers in `db/ops.py` for upsert, insert, and query operations.
- Both backends implement the `StorageBackend` interface defined in `storage/base.py` to keep tool logic backend-agnostic.

### Reminder Engine (`reminders.py`)
- Central governance unit producing structured reminders for every tool response.
- Features:
  - **Severity scoring**: default weight mapping (info/warning/urgent) promoted to dynamic scoring (1–10). Sessions in “warmup” mode downgrade warnings to informational until the team settles back in.
  - **Tone customization**: `defaults.reminder.tone` allows neutral, friendly, direct, or custom voices without code changes.
  - **Doc drift detection**: stores SHA-1 hashes per doc; diffs highlight changed artifacts and outdated content (e.g., architecture guide, phase plan).
  - **Staleness checks**: timezone-aware comparisons guard against missing UTC offsets.
  - **Workflow enforcement**: warns when development proceeds before architecture/phase/checklist are in acceptable states.
  - **Context reminder**: ensures every reply identifies the active project, log counts, and session age.

### Tool Suite (`tools/`)
- **Project Selection**:
  - `set_project`: validates root, docs directory, progress log paths, generates templates if missing, and registers the project with storage and state.
  - `get_project`, `list_projects`: surface current state and known projects.
  - `generate_doc_templates`: renders markdown scaffolds (architecture guide, phase plan, checklist, log) with reminder feedback.
- **Logging & Analytics**:
  - `append_entry`: writes canonical log lines, enforces rate limiting, mirrors entries to storage, returns metadata + reminders.
  - `read_recent`: tail-based view with optional agent/emoji filtering; relies on storage when available.
  - `query_entries`: advanced search (date ranges, regex, meta filters) across both storage and file backends.
  - `rotate_log`: archive + fresh log creation.
- **Utilities**:
  - `sync_to_github`: current stub alerting users that GitHub integration is planned (flagged by reminders).

### Utilities (`utils/`)
- `time.py`: canonical UTC formatting/parsing and range boundaries.
- `files.py`: async-safe file operations (`append_line`, `read_tail`, `rotate_file`).
- `logs.py`: log line parsing and file reading helpers.
- `search.py`: reusable text/regex filter functions.

---

## Operational Workflow

1. **Bootstrap**:
   - `set_project` is invoked (via MCP or CLI script) to register the project, generate missing docs, and prime state/storage.
   - Templates produce `ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, `CHECKLIST.md`, `PROGRESS_LOG.md`; reminders prompt follow-up if placeholders remain.

2. **Daily Logging**:
   - After meaningful work, agents call `append_entry` with message, status, metadata, and optional timestamp overrides.
   - Log line is appended to disk, mirrored to DB, and reminders return any action items (e.g., “phase plan incomplete”, “no log in 20 minutes”).

3. **Analysis & Governance**:
   - `read_recent` supplies tail views for quick checks.
   - `query_entries` offers full search, powering dashboards or compliance scripts.
   - Reminders (included in every response) build a feedback loop for doc hygiene, coverage, and cadence.

4. **Rotation & Audits**:
   - `rotate_log` archives large logs into timestamped copies, reinitializes fresh log files.
   - Future `audit_project` (roadmap) will convert reminder signals into a compliance score for dashboards.

---

## Configuration & Deployment

### Environment Variables
- `SCRIBE_ROOT`: Absolute path to `MCP_SPINE` directory (critical for Codex integration).
- `SCRIBE_STORAGE_BACKEND`: `sqlite` (default) or `postgres`.
- `SCRIBE_DB_URL`: Postgres connection string when needed.
- `SCRIBE_LOG_*`: Rate limits and file rotation settings.
- `SCRIBE_REMINDER_*`: Idle and warmup thresholds, JSON defaults (severity weights, tone, etc.).

### MCP Integration
- `MCP_SPINE/config/mcp_config.json` demonstrates stdio configuration with environment overrides.
- Codex CLI registration example:
  ```bash
  codex mcp add scribe \
    --env SCRIBE_ROOT=/home/austin/projects/Scribe/MCP_SPINE \
    --env SCRIBE_STORAGE_BACKEND=sqlite \
    -- python -m MCP_SPINE.scribe_mcp.server
  ```
- `MCP_SPINE/scripts/test_mcp_server.py` performs a `tools/list` handshake to validate server readiness before wiring into Codex.

### CLI Utility (`scripts/scribe.py`)
- Standalone script for local append operations. Reads `config/projects/*.json`, falls back to environment defaults, supports dry-run mode, and respects `SCRIBE_ROOT`.

---

## Reminder Governance Model

### Inputs
- Tool history (name + timestamp) from `StateManager`.
- Document status map (missing/incomplete/complete) with per-doc hashes.
- Sessions tracked via `session_started_at` and `last_activity_at`.
- Configurable thresholds and tone per project or global defaults.

### Outputs
- Structured reminders: `{"level", "score", "emoji", "message", "context", "category", "tone"}`.
- Logging prompts (info/warning/urgent) based on minutes since last entry, with session warmup smoothing.
- Doc hygiene alerts for missing or template-filled docs.
- Drift notifications when doc hashes change since last scan.
- Staleness warnings based on mtime + configurable days.
- Workflow escalations if coding proceeds without architectural sign-off.

### Extensibility
- Additional categories (e.g., “metrics”, “pipeline”) can be layered by returning new Reminder objects.
- `defaults.reminder` in project configs provides deep customization without touching code.

---

## Testing & Quality Gates
- `pytest MCP_SPINE/tests` covers tool workflows, rate limits, rotation logic, doc generation, and state handling.
- `python -m compileall MCP_SPINE/scribe_mcp` assures bytecode compilation.
- `python MCP_SPINE/scripts/test_mcp_server.py` acts as a smoke test for MCP protocol compliance.
- Reminder engine and state manager were explicitly unit tested post-refactor to guarantee timezone correctness and state migration stability.

---

## Roadmap Snapshot (ref. Phase Plan)
- **Storage Enhancements**: asyncpg pooling, write-ahead queue, checksum reconciliation.
- **Reminder Evolution**: dynamic scoring UI, per-agent weighting, doc diff display.
- **Governance Mode**: compliance scoring (`audit_project` tool), dashboard integration, health metrics export.
- **Extended MCP Suite**: additional servers hosted under `MCP_SPINE` alongside Scribe (GitHub control, observability, etc.).
- **CLI/UX polish**: richer CLI output, integration with taxonomies in `AGENTS.md`/`AGENTS_EXTENDED.md`.

---

## Conclusion
Scribe MCP transforms project logging from a passive history into an active governance layer. Packing it into `MCP_SPINE` unlocks reusability: the codebase can now be dropped into other ecosystems as a plug-and-play MCP server manager. Its reminder engine, storage abstraction, and state tracking ensure teams keep documentation and implementation synchronized—exactly what the Codex MCP ecosystem needs for transparent, auditable workflows.

As Scribe evolves (metrics, audits, dashboards), it will anchor a family of MCP servers under MCP_SPINE, each sharing the same robust infrastructure established here.
