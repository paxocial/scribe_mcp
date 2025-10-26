# ✅ Acceptance Checklist — Scribe MCP Server
**Version:** v0.5  
**Maintainers:** CortaLabs  
**Last Updated:** 2025-10-22 08:30 UTC

---

## Documentation Hygiene
- [x] Architecture guide reflects current problem statement, goals, and directory tree (proof: PROGRESS_LOG 2025-10-22 08:45 UTC).
- [x] Phase plan updated after every scope change (proof: PROGRESS_LOG 2025-10-22 08:45 UTC).
- [ ] Checklist cross-referenced in progress log entries (proof: meta checklist ids).

---

## Phase 0 – Bootstrap & Scaffolding
- [x] Create `scribe_mcp` package with server entrypoint and lifecycle hooks (proof: PROGRESS_LOG 2025-10-20 06:09 UTC).
- [x] Add config, utils, state management, and DB schema scaffolding (proof: same entry as above).
- [x] Document MCP workflow in `docs/mcp_server_guide.md` (proof: PROGRESS_LOG 2025-10-20 06:32 UTC).

---

## Phase 1 – Tooling & Logging Flow
- [x] Implement project selection tools (`set_project`, `get_project`, `list_projects`, `read_recent`) (proof: PROGRESS_LOG 2025-10-20 06:13 UTC).
- [x] Deliver `append_entry` with file append + Postgres mirroring (proof: automated tests / PROGRESS_LOG 2025-10-20 06:13 UTC).
- [x] Add `rotate_log`, `generate_doc_templates`, and `sync_to_github` stub (proof: PROGRESS_LOG 2025-10-20 06:13 UTC).
- [x] Establish sandbox-friendly unit tests (Austin-run) (proof: PROGRESS_LOG 2025-10-20 06:28 UTC).

---

## Phase 2 – Storage Backend & Query Enhancements
- [x] Define `StorageBackend` interface and adapter factory (proof: `storage/base.py`, PROGRESS_LOG 2025-10-22 03:30 UTC).
- [x] Implement SQLite backend and migration path (proof: `storage/sqlite.py`, PROGRESS_LOG 2025-10-22 03:30 UTC).
- [x] Port Postgres helpers into backend implementation (proof: `storage/postgres.py`, PROGRESS_LOG 2025-10-22 03:30 UTC).
- [x] Ship `query_entries` tool with parity across file/DB backends (proof: PROGRESS_LOG 2025-10-22 03:30 UTC).
- [x] Add project setup validation for collisions/permissions (proof: PROGRESS_LOG 2025-10-22 03:33 UTC).
- [x] Wire reminder engine into MCP responses (proof: PROGRESS_LOG 2025-10-22 08:45 UTC).
- [x] Support configurable reminder tone, severity scoring, and doc drift detection (proof: PROGRESS_LOG 2025-10-22 08:45 UTC).
- [ ] Update settings/config docs with backend selection guidance (proof: docs commit).
- [ ] Extend tests to cover both backends (proof: Austin test run results).

---

## Phase 3 – Metrics, GitHub, and UX Enhancements
- [ ] Expand metrics tracking (per-agent stats, rolling summaries) (proof: new DB fields + tests).
- [ ] Flesh out GitHub sync (issues/discussions) behind feature flag (proof: feature flag toggles).
- [ ] Support template overwrites and phase plan auto-updates (proof: tool output samples).
- [ ] Evaluate MCP resource exposure for recent entries/metrics (proof: resource listing).
- [ ] Draft observability hooks (structured logging, error reporting) (proof: architecture updates).

---

## Stretch Goals
- [ ] Implement optional LLM-generated summaries post-MVP (proof: feature flag and docs).
- [ ] Ship web/dashboard review tooling (proof: repo link and screenshots).
- [ ] Automate multi-repo project discovery service (proof: design doc).
