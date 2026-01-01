---
id: scribe_mcp_audit-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 scribe_mcp_audit"
doc_type: architecture
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-01'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
##Title
Title Setext
====
Sub Setext
----
```
## 3. Code Block
```
### Third
# 🏗️ Architecture Guide — scribe_mcp_audit
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-01-01 09:56:17 UTC

> Architecture guide for scribe_mcp_audit.

---
## Problem Statement
<!-- ID: problem_statement -->
- **Context:** scribe_mcp_audit is a Phase 0, release-focused audit and documentation lifecycle buildout for Scribe MCP v2.1.1 in /home/austin/projects/MCP_SPINE/scribe_mcp.
- **Goals:**
  - Produce AUDIT_REPORT.md with file/line citations.
  - Produce IMPLEMENTATION_PLAN.md with minimal diffs and a test plan.
  - Deliver doc lifecycle primitives: frontmatter engine (done), normalize_headers, generate_toc, create_doc, validate_crosslinks.
  - Update README, Scribe_Usage, and whitepaper to match new behaviors.
  - Provide targeted tests for every new action and idempotency guarantees.
- **Non-Goals:**
  - No unrelated feature work or speculative behavior claims.
  - No replacement files or parallel systems.
- **Success Metrics:**
  - Audit claims are fully cited.
  - Doc lifecycle actions are deterministic and idempotent.
  - Tests pass for all new behaviors.
  - User approves Phase 0 deliverables for release gating.

---
## Requirements & Constraints
<!-- ID: requirements_constraints -->
- **Functional Requirements:**
  - Collect audit facts with file/line citations.
  - Produce AUDIT_REPORT.md and IMPLEMENTATION_PLAN.md.
  - Implement/manage doc lifecycle actions: frontmatter (done), normalize_headers, generate_toc, create_doc, validate_crosslinks.
  - Ensure create_doc registers new docs in the project registry.
- **Non-Functional Requirements:**
  - Deterministic, idempotent edits (body-relative line math).
  - Preserve frontmatter byte-for-byte unless explicitly updated.
  - Use Scribe MCP tools for logging and doc edits.
  - Tests live under /tests with targeted runs.
- **Assumptions:**
  - Repo is accessible under /home/austin/projects/MCP_SPINE/scribe_mcp.
  - Jinja2 template engine is available in the current manage_docs pipeline (verify, do not assume).
- **Risks & Mitigations:**
  - Body-relative line regressions → add/extend tests with frontmatter offsets.
  - Header/TOC idempotency drift → add idempotency tests per action.
  - Template wiring mismatch → verify template_engine usage before create_doc.

---
## Architecture Overview
<!-- ID: architecture_overview -->
- **Solution Summary:** Execute a facts-locked audit plus deterministic doc-lifecycle primitives for Scribe MCP v2.1.1.
- **Component Breakdown:**
  - **Repo Discovery & Config:** Resolve repo root and load scribe.yaml, config.json, and any log config.
  - **Log Routing:** Map log_type to file paths and metadata constraints.
  - **Doc Manager:** manage_docs edit actions + verification with body-relative edits.
  - **Frontmatter Engine:** Parse/preserve YAML frontmatter and reattach after body edits.
  - **Header Normalizer:** Compute canonical numbering for markdown headers.
  - **TOC Generator:** Insert/replace deterministic TOC between markers.
  - **Doc Creator:** Render templates, inject frontmatter/body, register docs.
  - **Crosslink Validator:** Validate related docs and anchors (read-only diagnostics).
  - **Query Engine:** query_entries + read_recent behavior and scope resolution.
- **Data Flow:** Read files → parse frontmatter → mutate body → reattach frontmatter → write → tests → docs updates → audit reports.
- **External Integrations:** Local filesystem only; no network calls.

---
## Detailed Design
<!-- ID: detailed_design -->
1. **Audit Discovery & Citations**
   - Use rg to locate repo discovery, config loading, log routing, manage_docs, read_recent, and query_entries.
   - Capture file paths and line numbers for every claim and map behavior vs docs.
2. **Frontmatter Engine (done)**
   - Parse/preserve YAML frontmatter, auto-create canonical fields, update last_updated.
   - Run body-relative edits and reattach frontmatter after mutations.
3. **normalize_headers Action**
   - Strip numeric prefixes, compute canonical numbering, rewrite headers only.
   - Idempotent: repeated runs produce no diff.
4. **generate_toc Action**
   - Scan headers, generate GitHub-style anchors, insert/replace between TOC markers.
   - Insert TOC after frontmatter when missing.
5. **create_doc Action**
   - Verify Jinja template path, render template, inject frontmatter/body, register doc.
   - Log creation and return registry metadata.
6. **validate_crosslinks Action**
   - Verify related docs exist and anchors resolve (read-only diagnostics).
7. **Documentation Updates (done)**
   - Updated README, Scribe_Usage, and whitepaper with apply_patch structured mode + patch_mode enum guidance.
   - Updated skills/reminders to prefer apply_patch structured mode.
8. **Tests & Evidence (done for apply_patch updates)**
   - apply_patch structured mode + patch_mode enum validation tests passing (pytest -q tests/test_manage_docs_patch_range.py tests/test_template_engine_manage_docs.py tests/test_manage_docs_structured_edit.py).
   - Record runs in PROGRESS_LOG.

---
## Directory Structure (Keep Updated)
<!-- ID: directory_structure -->
```
/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/docs/dev_plans/scribe_mcp_audit
```
> Agents rely on this tree for orientation. Update whenever files are added, removed, or reorganised.

---
## Data & Storage
<!-- ID: data_storage -->
- **Datastores:** ['Filesystem markdown']
- **Indexes & Performance:** No new indexes required for audit.
- **Migrations:** None for Phase 0.

---
## Testing & Validation Strategy
<!-- ID: testing_strategy -->
- **Verification:** Manual inspection of citations plus targeted automated tests for doc lifecycle actions.
- **Tooling:** rg for search; apply_patch/replace_range for doc edits; pytest -q for focused suites.
- **Evidence:** Link key findings and test runs to PROGRESS_LOG entries.
- **Idempotency:** Re-run normalize_headers/generate_toc to confirm no diffs.
- **Usability Notes:** Log any friction using apply_patch/replace_range (error codes, patch_source_hash flow).

---
## Deployment & Operations
<!-- ID: deployment_operations -->
- **Environments:** Local development only.
- **Release Process:** Audit report → user approval → implementation phase.
- **Configuration Management:** Existing .scribe settings; no changes in Phase 0.
- **Maintenance & Ownership:** Codex performs audit under user direction.

---
## Open Questions & Follow-Ups
<!-- ID: open_questions -->
| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| Where is log routing config loaded today? | Codex | TODO | Determine log_config.json usage. |
| Confirm create_doc registry contract + path resolution? | Codex | TODO | Verify ProjectRegistry updates for new docs. |
| Scope for validate_crosslinks anchor checking? | Codex | TODO | Decide anchor rules and matching behavior. |
| Should list_sections expose line ranges for replace_range? | Codex | TODO | Improve edit ergonomics. |
| Should read_recent accept search_scope? | Codex | TODO | Determine desired API. |
| Release v2.1.1 sign-off gate? | User | TODO | Confirm approval requirements for tagging. |

---
## References & Appendix
<!-- ID: references_appendix -->
- docs/dev_plans/scribe_mcp_audit/PROGRESS_LOG.md
- docs/dev_plans/scribe_mcp_audit/ARCHITECTURE_GUIDE.md
- Scribe MCP codebase under /home/austin/projects/MCP_SPINE/scribe_mcp
