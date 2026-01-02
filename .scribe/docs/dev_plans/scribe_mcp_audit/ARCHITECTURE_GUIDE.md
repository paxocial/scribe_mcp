---
id: scribe_mcp_audit-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 scribe_mcp_audit"
doc_type: architecture
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
  - Produce AUDIT_REPORT.md with file/line citations (no assumptions).
  - Produce IMPLEMENTATION_PLAN.md with minimal diffs and a test plan.
  - Deliver doc lifecycle primitives: frontmatter engine (done), normalize_headers (done), generate_toc (done), create_doc (done), validate_crosslinks (done).
  - Record the open section-level edit issue in the audit report (no fix during audit).
  - Define the audit tooling roadmap (repo-root .scribe config, audit tool, apply_patch automation flags, YAML context parsing, evidence reader, token-budget guardrails).
  - Update README, Scribe_Usage, and whitepaper to match new behaviors (done).
  - Provide targeted tests for every new action and idempotency guarantees (done).
- **Non-Goals:**
  - No unrelated feature work or speculative behavior claims.
  - No replacement files or parallel systems.
- **Success Metrics:**
  - Audit claims are fully cited.
  - Doc lifecycle actions are deterministic and idempotent.
  - Tests pass for all new behaviors.
  - User approves Phase 0 deliverables for release gating.
## Requirements & Constraints
<!-- ID: requirements_constraints -->
- **Functional Requirements:**
  - Collect audit facts with file/line citations (no assumptions).
  - Produce AUDIT_REPORT.md and IMPLEMENTATION_PLAN.md.
  - Implement/manage doc lifecycle actions: frontmatter (done), normalize_headers (done), generate_toc (done), create_doc (done), validate_crosslinks (done).
  - create_doc can optionally register docs; one-off docs may remain unregistered.
  - Structural actions validate doc keys against the registry and fail on unknown docs.
  - Add a formal audit tool that enforces evidence-only claims and captures file lists + hashes (design pending).
  - Support repo-root `.scribe` config overrides for per-repo behavior (pending).
  - Allow apply_patch metadata flags to auto-run normalize_headers/generate_toc/validate_crosslinks and update YAML frontmatter fields (pending).
  - Parse YAML frontmatter for context when building tool responses (pending).
  - Add a read-only evidence reader to record which files were inspected (pending).
  - Add token-budget guardrails for audit outputs (pending).
- **Non-Functional Requirements:**
  - Deterministic, idempotent edits (body-relative line math).
  - Preserve frontmatter byte-for-byte unless explicitly updated.
  - Use Scribe MCP tools for logging and doc edits.
  - Tests live under /tests with targeted runs.
  - Audit outputs must be evidence-only and record sources explicitly.
  - Token-aware output (summaries, capped excerpts, explicit file lists).
- **Assumptions:**
  - Repo is accessible under /home/austin/projects/MCP_SPINE/scribe_mcp.
  - Jinja templating is internal-only for built-in templates; create_doc uses plain content/snippets.
- **Risks & Mitigations:**
  - Body-relative line regressions → add/extend tests with frontmatter offsets.
  - Header/TOC idempotency drift → add idempotency tests per action.
  - Doc key healing → enforce DOC_NOT_FOUND on unknown docs.
  - Automation flags could mask unintended writes → require explicit metadata opt-in and dry_run support.

---
## Architecture Overview
<!-- ID: architecture_overview -->
- **Solution Summary:** Execute a facts-locked audit plus deterministic doc-lifecycle primitives for Scribe MCP v2.1.1.
- **Component Breakdown:**
  - **Repo Discovery & Config:** Resolve repo root and load scribe.yaml, config.json, and any log config.
  - **Repo Config Overrides:** Allow repo-root `.scribe` configuration to override defaults (pending).
  - **Log Routing:** Map log_type to file paths and metadata constraints.
  - **Doc Manager:** manage_docs edit actions + verification with body-relative edits and registry-validated doc keys.
  - **Frontmatter Engine:** Parse/preserve YAML frontmatter and reattach after body edits.
  - **Header Normalizer:** Normalize ATX/Setext headers with canonical numbering; fenced code ignored.
  - **TOC Generator:** Insert/replace deterministic TOC between markers using GitHub-style anchors.
  - **Doc Creator:** Build from plain content/snippets/sections; optional registry update.
  - **Crosslink Validator:** Validate related docs and anchors (read-only diagnostics).
  - **Audit Tool:** Evidence-first audit logging with hashes and strict no-assumption enforcement (pending).
  - **Evidence Reader:** Read-only file inspection tool that records which files/lines were inspected (pending).
  - **Automation Orchestrator:** apply_patch metadata flags for normalize_headers/generate_toc/validate_crosslinks and frontmatter updates (pending).
  - **Token Guardrails:** Output shaping to preserve context budgets (pending).
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
3. **normalize_headers Action (done)**
   - Supports ATX headers with/without space plus Setext (`====` / `----`).
   - Body-only, fenced code ignored, idempotent output.
4. **generate_toc Action (done)**
   - GitHub-style anchors with de-dup suffixes and TOC markers.
   - Body-only, fenced code ignored, idempotent output.
5. **create_doc Action (done)**
   - Build from content/body/snippets/sections; users do not supply Jinja.
   - Optional register_doc flag; multiline bodies preserved.
6. **validate_crosslinks Action (done)**
   - Read-only diagnostics; optional anchor checks; no doc_updates log.
7. **Documentation Updates (done)**
   - README, Scribe_Usage, whitepaper, and SKILL updated for 2.1.1 behaviors.
8. **Tests & Evidence (done)**
   - apply_patch structured mode, normalize_headers, generate_toc, create_doc, validate_crosslinks tests.
   - Record runs in PROGRESS_LOG.
9. **Section-Level Edit Issue (open)**
   - Track in AUDIT_REPORT Issues section; no fixes during audit.
10. **Repo-Root .scribe Config Overrides (pending)**
   - Allow per-repo config loading from `.scribe` under repo root.
11. **Formal Audit Tool (pending)**
   - Evidence-first audit logging with hashes and no-assumption enforcement.
12. **apply_patch Automation Flags (pending)**
   - Optional metadata to auto-run normalize_headers/generate_toc/validate_crosslinks and update YAML frontmatter.
13. **YAML Context Extraction (pending)**
   - Parse frontmatter for tool response context and audit metadata.
14. **Evidence Reader Tool (pending)**
   - Read-only file inspection that records which files/lines were reviewed.
15. **Token Budget Guardrails (pending)**
   - Output shaping to preserve context budgets during audits.
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
| Confirm create_doc registry contract + path resolution? | Codex | DONE | Verified registry validation + optional register_doc; see PROGRESS_LOG. |
| Scope for validate_crosslinks anchor checking? | Codex | DONE | Implemented anchor checks + diagnostics; see PROGRESS_LOG. |
| Audit read_recent scope behavior? | Codex | TODO | Confirm scope resolution vs docs. |
| Audit query_entries behavior matrix? | Codex | TODO | Capture search_scope/doc_type behavior. |
| Section-level edit issue (replace_range duplication) | Codex | TODO | Track in AUDIT_REPORT Issues; no fix during audit. |
| Repo-root `.scribe` config override? | Codex | TODO | Enable per-repo config loading. |
| Formal audit tool with cryptographic chaining? | Codex | TODO | Define parameters, evidence capture, and verification. |
| apply_patch automation flags? | Codex | TODO | Normalize headers/TOC/crosslinks + frontmatter updates via metadata. |
| YAML frontmatter context extraction? | Codex | TODO | Define how tools surface frontmatter context. |
| Evidence reader tool? | Codex | TODO | Read-only file inspection with recorded evidence. |
| Token budget guardrails? | Codex | TODO | Output shaping and context preservation strategy. |
| Should list_sections expose line ranges for replace_range? | Codex | TODO | Improve edit ergonomics. |
| Should read_recent accept search_scope? | Codex | DONE | Superseded by audit item; defer to audit findings. |
| Release v2.1.1 sign-off gate? | User | TODO | Confirm approval requirements for tagging. |

---
## References & Appendix
<!-- ID: references_appendix -->
- docs/dev_plans/scribe_mcp_audit/PROGRESS_LOG.md
- docs/dev_plans/scribe_mcp_audit/ARCHITECTURE_GUIDE.md
- Scribe MCP codebase under /home/austin/projects/MCP_SPINE/scribe_mcp
