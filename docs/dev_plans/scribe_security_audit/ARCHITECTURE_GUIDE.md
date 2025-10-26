# 🏗️ Architecture Guide — Scribe Security Audit
**Author:** Codex (via Scribe)  
**Version:** Draft v1.0  
**Last Updated:** 2025-10-25 20:49 UTC

This document defines the scope and architectural understanding needed to execute a two-phase (Audit ➜ Fix) hardening effort for the Scribe MCP server that lives inside the MCP_SPINE mono-repo. It complements AGENTS.md / CLAUDE.md guidance and will be kept in lockstep with every material change to the system or to our audit plan.

---

## 1. Problem Statement
- **Context:** Scribe MCP is the canonical logging/documentation server for every agent operating inside MCP_SPINE. It orchestrates project bootstrap, doc generation, and append-only progress logs. The platform is used by multiple autonomous agents, so correctness and security are existential.
- **Goals:**
  - Perform a comprehensive security + stability audit of the Scribe MCP codebase, supporting infrastructure, and operator guidance (AGENTS.md + CLAUDE.md parity).
  - Produce an auditable findings report plus remediation plan prior to touching production code.
  - Deliver a predictable Fix phase that closes all critical/high findings, validates with automated + manual tests, and ships a stable release candidate.
- **Non-Goals:**
  - Building net-new product features unrelated to security/stability.
  - Expanding scope beyond the Scribe MCP server (other MCP servers remain future work unless the audit uncovers shared utilities that are unsafe).
  - Rewriting the stack or migrating away from the current Python-based architecture.
- **Success Metrics:**
  - ✅ Audit report delivered with prioritized findings, affected files, and recommended fixes.
  - ✅ AGENTS.md and CLAUDE.md aligned in both guidance and tone.
  - ✅ 0 critical/high open issues after Fix phase; automated test suite green; no regressions in doc bootstrap or logging flows.
  - ✅ New checklists, docs, and scribe log entries cover the entire effort (no undocumented gaps).

---

## 2. Requirements & Constraints
- **Functional Requirements:**
  - Maintain the core toolchain (`set_project`, `append_entry`, doc templating, state management, reminders) while auditing for correctness and abuse resistance.
  - Generate and maintain an audit report document that tracks findings, severity, reproduction steps, and remediation owners.
  - Keep AGENTS.md and CLAUDE.md synchronized so every agent receives identical security-critical rules.
  - Enforce the Audit ➜ Fix workflow with explicit entry/exit criteria and traceability to CHECKLIST.md.
- **Non-Functional Requirements:**
  - Security: guard against log injection, path traversal, state corruption, and privilege escalation inside MCP tooling.
  - Reliability: no data loss in doc bootstrap or logging pipelines; idempotent tooling.
  - Compliance: immutable audit logs, UTC timestamps, and deterministic tool responses.
  - Performance: audits may run frequently, so inspection tooling must not stall interactive agents.
- **Assumptions:**
  - Python 3.11 runtime, workspace-write sandbox, no network constraints unless explicitly noted.
  - Default storage backend is SQLite (`scribe_mcp/storage/sqlite.py`) with optional Postgres support.
  - Agents work from `/home/austin/projects/Scribe/MCP_SPINE` and respect the no-replacement-files rule.
- **Risks & Mitigations:**
  - *Risk:* Divergent instructions between AGENTS.md and CLAUDE.md cause unsafe behavior.  
    *Mitigation:* Diff both documents, merge authoritative guidance, and add parity checks to the checklist.
  - *Risk:* Hidden security flaws (e.g., unchecked user input in CLI/script paths).  
    *Mitigation:* Threat-model each tool, read associated tests, and add negative test cases.
  - *Risk:* Audit stalls without proper logging discipline.  
    *Mitigation:* Enforce append_entry after every meaningful action; leverage meta fields for traceability.

---

## 3. Architecture Overview
- **Solution Summary:** Scribe MCP exposes a set of MCP tools (via `scribe_mcp/server.py`) that let agents create/select projects, bootstrap documentation, and append structured log entries backed by SQLite/Postgres. Supporting modules handle reminders, state persistence, templating, and security policies. Our audit overlays on top of this architecture by cataloging each surface area, evaluating security posture, and preparing focused remediation work.
- **Component Breakdown:**

| Component | Location | Responsibilities | Notes |
| --- | --- | --- | --- |
| MCP Server Core | `scribe_mcp/server.py` | Registers all Scribe tools, handles stdio IPC, enforces reminders. | Critical entry point; misconfigurations here affect every agent. |
| Tool Suite | `scribe_mcp/tools/` | Implements `set_project`, `append_entry`, `list_projects`, `generate_doc_templates`, etc. | Primary audit target; multiple file + filesystem interactions. |
| Storage Layer | `scribe_mcp/storage/` | Abstracts SQLite/Postgres backends plus models. | Validate SQL injection defenses, journaling, rotation behavior. |
| State & Reminders | `scribe_mcp/state/`, `scribe_mcp/reminders.py` | Tracks active projects, emits logging reminders/alerts. | Ensure reminder logic cannot be bypassed or DOS’d. |
| Documentation Templates | `scribe_mcp/templates/`, `docs/dev_plans/` | Generate per-project ARCHITECTURE/PHASE/CHECKLIST/PROGRESS docs. | Confirm templates do not leak data and remain consistent. |
| CLI / Scripts | `scripts/scribe.py`, `scripts/scribe_cli.py`, `scripts/test_mcp_server.py` | Human-facing entry points mirroring MCP tools. | Need parity in validation and environment hygiene. |
| Tests | `tests/` | 70+ functional + performance tests. | Provide coverage insight; add new cases during Fix phase. |

- **Data Flow:** Typical workflow → Agent runs `set_project` which loads/creates docs + state (filesystem + JSON). Subsequent `append_entry` calls write to `PROGRESS_LOG.md` via storage backend while reminders warn if gaps occur. Tools like `generate_doc_templates` and `list_projects` read/write config in `config/projects/`. Our audit observes each flow, enumerates trust boundaries (user input ➜ filesystem, CLI ➜ storage), and flags insecure transitions.
- **External Integrations:** Optional Postgres via `scribe_mcp/storage/postgres.py`, plus potential future integration hooks (`sync_to_github` stub). No third-party APIs are called today, simplifying the threat model.

---

## 4. Detailed Design
### 4.1 MCP Server Core
- **Purpose:** Provide a stdio MCP server entry that hosts the Scribe toolset.
- **Interfaces:** Accepts MCP tool invocations; loads settings from environment (`SCRIBE_ROOT`, storage backend env vars).
- **Implementation Notes:** Uses the MCP SDK (when available) but includes graceful fallbacks. Error handling ensures informative reminders.
- **Security Considerations:** Validate project names, ensure relative paths remain inside repo root, sanitize reminder payloads (avoid user-controlled format strings).

### 4.2 Tool Suite
- **Purpose:** Encapsulate discrete operations (project selection, logging, doc generation, queries).
- **Interfaces:** Each tool exposes a `run`/`handle` function invoked by MCP. Parameters typically include strings, dicts, or JSON payloads.
- **Implementation Notes:** Tools rely heavily on filesystem operations (`pathlib.Path`, `os`, `json`). Many functions reopen Markdown files and rely on locking (`PROGRESS_LOG.md.lock`).
- **Security Considerations:** Check for path traversal in project config (`progress_log`), enforce UTF-8 + ASCII guidelines, ensure metadata serialization cannot execute code, and confirm locking prevents concurrency corruption.

### 4.3 Storage Layer
- **Purpose:** Provide persistent storage for log entries and metadata.
- **Interfaces:** `StorageBackend` abstract class with concrete `SQLiteStorage` + `PostgresStorage`.
- **Implementation Notes:** SQLite uses WAL/journal files and integrity checks; Postgres backend relies on async drivers (asyncpg). Both share schema definitions in `storage/models.py`.
- **Security Considerations:** Parameterize SQL queries, enforce journaling cleanup, and validate migration paths. During audit we will review transaction boundaries and error recovery.

### 4.4 State, Reminders, and Security Modules
- **Purpose:** Manage active project context, send reminders for stale logging, and enforce security policies (e.g., commandment validations).
- **Interfaces:** `state/manager.py`, `reminders.py`, and helpers inside `security/`.
- **Implementation Notes:** State persisted as JSON under `scribe_mcp/state`; reminders triggered per tool execution.
- **Security Considerations:** Prevent state poisoning by limiting which files can be loaded; ensure reminder JSON cannot be used to inject terminal control codes.

### 4.5 Documentation & Templates
- **Purpose:** Maintain `docs/dev_plans/<project>/ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, `CHECKLIST.md`, `PROGRESS_LOG.md`.
- **Implementation Notes:** Templates live in `scribe_mcp/templates/` and are copied/filled when new projects spin up.
- **Security Considerations:** Confirm template rendering does not evaluate user-provided content; audit any string formatting or file globbing.

### 4.6 CLI + Tests
- **Purpose:** Provide human-friendly wrappers (`scripts/scribe.py`) and comprehensive automated validation (`tests/`).
- **Implementation Notes:** CLI mirrors MCP tool APIs; tests rely on `pytest` with fixtures for temp directories and performance measurement.
- **Security Considerations:** CLI command-line arguments must be sanitized; tests should include malicious input cases to prevent regressions.

---

## 5. Directory Structure (Keep Updated)
```
/home/austin/projects/Scribe/MCP_SPINE
├── config/                   # MCP + project configs
├── docs/                     # Shared guides + dev plans (incl. this project)
├── scribe_mcp/               # Primary server under audit
│   ├── config/               # Default settings + templates
│   ├── tools/                # MCP tool implementations
│   ├── storage/              # SQLite/Postgres backends + models
│   ├── state/                # Project/cache management
│   ├── security/             # Security policies/helpers
│   ├── templates/            # Doc + reminder templates
│   └── server.py             # MCP entry point
├── scripts/                  # CLI + helper scripts mirroring tools
├── tests/                    # Functional + performance suites
├── demo/                     # Example MCP usage
├── tmp_tests/                # Sandbox outputs for test runs
└── docs/dev_plans/scribe_security_audit/ # This project’s documentation suite
```

---

## 6. Data & Storage
- **Datastores:** Markdown files (`PROGRESS_LOG.md`, ARCH/PHASE/CHECKLIST) under repo control; SQLite DB for aggregated entries; optional Postgres for team deployments.
- **Indexes & Performance:** SQLite uses auto-indexes; Postgres schema defines indexes on timestamps/project. Rotation utilities keep Markdown logs <200 entries to avoid large file writes.
- **Retention & Archival:** `rotate_log` archives logs with timestamp suffixes; audit will validate integrity of rotation plus hash-chain (see `tests/test_audit_trails.py`).
- **Migrations:** Currently manual; need to verify there are scripts to migrate SQLite ➜ Postgres. Capture as an audit finding if missing.

---

## 7. Testing & Validation Strategy
- **Unit Tests:** Existing pytest modules cover tools, storage, reminders, and utilities. During Fix phase we will extend coverage for edge cases discovered in audit (e.g., malformed metadata, concurrent writes).
- **Integration Tests:** `test_set_project_integration.py`, `test_append_entry_integration.py`, and server smoke tests simulate real tool invocations. We will add regression tests for any vulnerabilities found.
- **Performance Tests:** `tests/test_performance.py` plus JSON result artifacts measure rotation throughput. Keep them opt-in via `-m performance`.
- **Manual QA:** During audit, dry-run CLI commands, intentionally misuse inputs, and verify reminders/log outputs. Document reproduction steps inside the audit report.
- **Observability:** Logging is Markdown-based; ensure wartime debugging info remains accessible (metadata fields, reminders, rotation history).

---

## 8. Deployment & Operations
- **Environments:** Local dev uses SQLite with workspace-write sandbox; production may set `SCRIBE_STORAGE_BACKEND=postgres`. Need to verify environment variable handling and secrets loading.
- **Release Process:** Tag a stable release after Fix phase, run pytest matrix, document results in CHECKLIST.md, and update AGENTS/CLAUDE instructions.
- **Configuration Management:** `config/projects/*.json` defines per-project roots; `PROJECT_NAMING.md` guards against temp/test names. Ensure audit verifies config validation logic.
- **Maintenance & Ownership:** CortaLabs / Scribe team owns the stack; this audit establishes on-call-ready documentation plus a repeatable hardening playbook.

---

## 9. Open Questions & Follow-Ups
| Item | Owner | Status | Notes |
| --- | --- | --- | --- |
| Confirm whether Postgres backend is exercised in CI | Audit Team | Open | Need to inspect tests + configs; may require local container. |
| Determine parity gaps between AGENTS.md and CLAUDE.md | Audit Team | In Progress | Early review shows CLAUDE.md emphasizes env setup; needs doc-suite + reminder content. |
| Decide location/format for the audit report doc | Audit Team | Open | Candidate: `docs/dev_plans/scribe_security_audit/AUDIT_REPORT.md`. Will finalize in Phase Plan step 3. |

---

## 10. References & Appendix
- `AGENTS.md`, `AGENTS_EXTENDED.md`, `CLAUDE.md` — core operating rules.
- `scribe_mcp/server.py`, `scribe_mcp/tools/*`, `scribe_mcp/storage/*` — primary code under audit.
- `tests/*.py` — reference for existing coverage.
- Project log (`docs/dev_plans/scribe_security_audit/PROGRESS_LOG.md`) — authoritative activity trail.
