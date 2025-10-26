# ⚙️ Phase Plan — Scribe MCP Server
**Project:** Scribe MCP Server  
**Version:** Draft v0.5  
**Author:** CortaLabs (Codex)  
**Last Updated:** 2025-10-22 08:30 UTC

---

## Phase 0 – Bootstrap & Scaffolding
**Objective:**  
Stand up the MCP package skeleton, core configuration, and baseline documentation.

**Key Tasks:**
- [x] Create `MCP_SPINE/scribe_mcp` package with server entrypoint and lifecycle hooks.
- [x] Add config, utils, state management, and DB schema scaffolding.
- [x] Document MCP workflow in `docs/mcp_server_guide.md`.

**Deliverables:**
- `MCP_SPINE/scribe_mcp/server.py` (async stdio server).
- Initial DB schema (`db/init.sql`) and helper modules.
- Updated MCP server guide with hybrid storage notes.

**Acceptance Criteria:**
- [x] `python -m MCP_SPINE.scribe_mcp.server` imports cleanly.
- [x] Package compiles under `python -m compileall`.

**Dependencies:** None  
**Confidence:** 0.85

---

## Phase 1 – Tooling & Logging Flow
**Objective:**  
Implement core MCP tools for project selection, logging, documentation scaffolding, and GitHub stubs.

**Key Tasks:**
- [x] Implement `set_project`, `get_project`, `list_projects`, and `read_recent`.
- [x] Deliver `append_entry` with file append + Postgres mirroring.
- [x] Add `rotate_log`, `generate_doc_templates`, and `sync_to_github` stub.
- [x] Establish sand-box friendly unit tests (Austin-run).

**Deliverables:**
- Complete tool suite registered via decorators.
- Tests in `tests/test_tools.py` with sync harness for CI portability.

**Acceptance Criteria:**
- [x] Tools return structured `{"ok": ...}` responses.
- [x] Tests pass locally (validated by Austin).

**Dependencies:** Phase 0  
**Confidence:** 0.80

---

## Phase 2 – Storage Backend & Query Enhancements (In Progress)
**Objective:**  
Introduce a pluggable storage layer supporting SQLite default and Postgres optional, and expose advanced querying consistently across engines.

**Key Tasks:**
- [x] Define `StorageBackend` interface and adapter factory (proof: `storage/base.py`, `storage/__init__.py`).
- [x] Implement SQLite backend (custom async wrapper) with parity helpers (proof: `storage/sqlite.py`).
- [x] Port Postgres helpers into backend implementation (proof: `storage/postgres.py`, `db/ops.py`).
- [x] Deliver `query_entries` tool with date/status/meta filters and file fallback (proof: PROGRESS_LOG 2025-10-22 03:30 UTC).
- [x] Add project setup validation/warnings for path collisions & permissions (proof: PROGRESS_LOG 2025-10-22 03:33 UTC).
- [ ] Update settings/config docs with backend selection guidance.
- [ ] Extend tests to exercise both backends (Austin-run).
- [x] Implement documentation reminder prompts (stale doc detection + MRU project context) (proof: PROGRESS_LOG 2025-10-22 08:45 UTC).
- [x] Add configurable reminder tone, severity scoring, and doc hash drift detection (proof: PROGRESS_LOG 2025-10-22 08:45 UTC).

**Deliverables:**
- Storage adapter module (`MCP_SPINE/scribe_mcp/storage/`) with SQLite/Postgres parity.
- Advanced query surface for MCP/file clients.
- Updated configuration documentation and examples.

**Acceptance Criteria:**
- [ ] MCP tools operate identically across both backends (including advanced queries).
- [ ] Local default uses SQLite without extra env vars.
- [ ] Postgres path remains opt-in via `SCRIBE_DB_URL`.
- [x] Scribe surfaces doc-reminder metadata with project selection/listing tools.

**Dependencies:** Phases 0–1  
**Confidence:** 0.70

---

## Phase 3 – Metrics, GitHub, and UX Enhancements (Queued)
**Objective:**  
Layer on richer metrics aggregation, GitHub sync, and doc automation polish.

**Key Tasks:**
- [ ] Expand metrics tracking (per-agent stats, rolling summaries).
- [ ] Flesh out GitHub sync (issues/discussions) behind feature flag.
- [ ] Support template overwrites and phase plan auto-updates.
- [ ] Evaluate MCP resource exposure for recent entries/metrics.
- [ ] Draft observability hooks (structured logging, error reporting).

**Deliverables:**  
- Enhanced metrics API.  
- GitHub integration design + stub implementation.  
- CLI/mcp documentation updates.

**Acceptance Criteria:**
- [ ] Feature flags guard non-local integrations.
- [ ] Metrics verified in both storage backends.

**Dependencies:** Phase 2  
**Confidence:** 0.55

---

## Phase 4 – Stretch Goals
- LLM-generated summaries (opt-in) once core logging is rock solid.
- Web UI/dashboard for log review and metrics.
- Multi-repo project discovery service.
