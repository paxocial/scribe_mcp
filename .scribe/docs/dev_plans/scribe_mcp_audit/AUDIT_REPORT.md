---
id: scribe_mcp_audit-custom_doc
title: "AUDIT_REPORT \u2014 scribe_mcp_audit"
doc_type: custom_doc
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-02'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# AUDIT_REPORT — scribe_mcp_audit

**Scope:** Phase 0 facts-locked audit for Scribe MCP v2.1.1 in `/home/austin/projects/MCP_SPINE/scribe_mcp`.
**Method:** Evidence-first audit with file/line citations; no code changes during audit.

---
## A) Config Loading Audit (Repo discovery + config load)
**Status:** IN PROGRESS
**Questions:**
- Where is repo root discovered? Which configs are read (scribe.yaml/config.json/log_config.json)?
- Which functions own this flow and how are defaults applied?

**Evidence (file/line citations):**
- `config/repo_config.py:139-191` — `RepoDiscovery.find_repo_root` searches upward for repo markers (.git, .scribe, pyproject.toml, package.json, Cargo.toml, go.mod) and `.scribe/scribe.yaml`.
- `config/repo_config.py:193-238` — `RepoDiscovery.load_config` checks config paths in order and returns defaults if none found.
- `config/log_config.py:49-84` — `load_log_config` loads/creates `config/log_config.json`, merges defaults, and returns merged log definitions.
- `config/log_config.py:105-136` — `resolve_log_path` resolves log file paths with project context and `docs_dir` fallback.

**Findings:**
- Repo discovery and config load are implemented in `RepoDiscovery` with explicit marker search and a fixed config path order.
- Log configuration is loaded from `config/log_config.json` with default generation when missing or invalid.

---
## B) manage_docs Precision Audit
**Status:** IN PROGRESS
**Questions:**
- How do apply_patch / replace_range / replace_section behave on mismatches?
- What diagnostics are emitted on failures?
- How are frontmatter/body splits handled and how do line numbers map?

**Evidence (file/line citations):**
- `doc_management/manager.py:1219-1296` — `_apply_unified_patch` enforces strict hunk format and context matching; emits PATCH_INVALID_FORMAT/PATCH_CONTEXT_MISMATCH/PATCH_DELETE_MISMATCH/PATCH_RANGE_ERROR.
- `doc_management/manager.py:1309-1323` — `_replace_range_text` validates line ranges and raises out-of-range errors.
- `doc_management/manager.py:1326-1363` — `_replace_block_text` skips fenced code blocks, errors on missing/ambiguous anchors, and replaces to the next blank line.
- `tools/manage_docs.py:683-697` — manage_docs validates doc keys against project registry and returns DOC_NOT_FOUND for unknown docs.

**Findings:**
- apply_patch uses strict unified diff parsing and emits explicit error codes on invalid hunks or context mismatches.
- replace_range and replace_block are guarded with explicit error paths for invalid ranges or ambiguous anchors.
- manage_docs blocks structural edits against unknown doc keys (DOC_NOT_FOUND).

---
## C) read_recent Scope Audit
**Status:** IN PROGRESS
**Questions:**
- What scope resolution rules are implemented?
- How does include_metadata flow through the response?

**Evidence (file/line citations):**
- `tools/read_recent.py:152-229` — read_recent uses resolve_logging_context with require_project=True; errors if no project context.
- `tools/read_recent.py:233-241` — n/limit legacy handling: n used as page_size when default pagination args are used.
- `tools/read_recent.py:244-259` — backend pagination path when storage backend supports pagination.
- `tools/read_recent.py:136-145` — include_metadata parameter is healed and passed through to output formatting.

**Findings:**
- read_recent requires an active project context (no cross-project scope in this tool).
- include_metadata is explicitly healed and then used to control response formatting.

---
## D) query_entries Behavior Matrix
**Status:** IN PROGRESS
**Questions:**
- What search_scope/document_types options are implemented?
- How are filters (message, time_range, agents, meta) applied?

**Evidence (file/line citations):**
- `tools/query_entries.py:37-39` — VALID_SEARCH_SCOPES and VALID_DOCUMENT_TYPES enumerations.
- `tools/query_entries.py:61-231` — _validate_search_parameters heals/validates enums, lists, ranges, and strings for search parameters.
- `tools/query_entries.py:1069-1099` — resolve_logging_context with require_project=False (tool can run without active project).

**Findings:**
- query_entries exposes explicit search_scope and document_types enums and validates/heals them before search execution.
- query_entries can resolve context without an active project (require_project=False).

---
## E) Audit Tool Design
**Status:** NOT STARTED
**Questions:**
- What audit-specific parameters are required to enforce no-assumption rules?
- What evidence capture fields should be mandatory (file list, line ranges, hashes)?
- How should audit results be chained or verified?

**Evidence (file/line citations):**
- (pending)

**Findings:**
- (pending)

---
## Issues
```
---

## ISSUE: Section-Level Edits Are Still Range-Dependent and Can Duplicate Structure

**Summary:**
`apply_patch` with `replace_range` can still produce **duplicate section headers or partial overwrites** when line ranges drift or land inside an existing section. This happens even though doc registry resolution, frontmatter isolation, and context recovery are now solid.

**Why this matters:**

* The system is *mechanically reliable* now, but still **structurally brittle**.
* Large semantic edits (like audit sections A–D) should be **section-addressed**, not line-addressed.
* Line-based ranges are an optimization, not a contract — and long-lived docs will drift.

**Current failure mode:**

* `replace_range` may leave behind an existing header or separator.
* Results in duplicated headers (e.g., `## A) Config Loading Audit`) or malformed section boundaries.
* The system recovers, but only *after* mutation.

**Desired fix:**

* Make **section-anchored replacement** the default for top-level headers.
* Ensure edits targeting `## <Section>` *replace the entire section body deterministically*.
* Line ranges should be optional/fallback, not primary, for structured docs.

---
```

---
## Notes
- This report is the source of truth for audit claims and citations.
- Cross-reference the rotated log for prior investigation notes: `PROGRESS_LOG.md.2026-01-02.md`.
