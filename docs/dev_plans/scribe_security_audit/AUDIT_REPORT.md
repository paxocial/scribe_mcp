# 🔒 Scribe MCP Security Audit Report
**Project:** Scribe Security Audit  
**Owner:** Codex (via Scribe)  
**Status:** Phase 1 — Audit & Alignment (in progress)  
**Last Updated:** 2025-10-25 20:54 UTC

This report captures methodology, findings, and remediation tracking for the Scribe MCP security + stability review. Update it continuously as the audit evolves; link every entry to a PROGRESS_LOG line, commit, or artifact.

---

## 1. Scope & Objectives
- Validate the integrity and security of Scribe MCP (tools, storage, server, CLI, docs, and tests) within `MCP_SPINE/`.
- Ensure AGENTS.md and CLAUDE.md deliver identical policies to all agents.
- Produce prioritized findings with reproduction steps, impact analysis, and remediation guidance.
- Feed actionable tasks into Phase 2 of the Phase Plan and the acceptance checklist.

Out of scope: implementing new features unrelated to hardening, auditing other MCP servers (unless shared code is affected), and modifying production environments prior to Phase 2.

---

## 2. Methodology
- **Document Review:** Read AGENTS.md, CLAUDE.md, ARCHITECTURE_GUIDE.md, PHASE_PLAN.md, CHECKLIST.md, PROJECT_NAMING.md, and relevant docs for policy gaps.
- **Code Review:** Systematically inspect `scribe_mcp/server.py`, `tools/`, `storage/`, `state/`, `security/`, `templates/`, `scripts/`, and representative tests. Capture threats such as injection, path traversal, race conditions, privilege escalation, or data-loss risks.
- **Hands-on Validation:** Run non-mutating commands (e.g., dry-run `set_project`, `append_entry`, CLI invocations) to confirm assumptions. Postpone code changes until Phase 2.
- **Threat Modeling:** For each component, identify assets, entry points, trust boundaries, and mitigations. Record them in the Findings Log or Supporting Notes.
- **Logging Discipline:** Every meaningful investigation step must be logged with `append_entry` referencing `AUDIT_REPORT.md` + checklist IDs (AUD-INV, AUD-REPORT, etc.).

---

## 3. Severity Rubric
| Severity | Description | Expected Response |
|----------|-------------|-------------------|
| Critical | Immediate risk of data loss, RCE, or irreparable corruption. | Fix/blocker before progressing; halt release until resolved. |
| High | Significant vulnerability or stability risk with plausible exploitation. | Prioritize in first remediation wave; add regression tests. |
| Medium | Noticeable defect, defense-in-depth gap, or doc mismatch. | Schedule fix during Phase 2; document rationale if deferred. |
| Low | Minor issue, stylistic concern, or future enhancement. | Optional fix; ensure backlog visibility. |

---

## 4. Findings Log
Populate the table as the audit proceeds. Use consistent IDs (`AUD-001`, etc.) and keep statuses current.

| ID | Component / File | Description & Impact | Severity | Status | Owner | Evidence / Links |
|----|------------------|----------------------|----------|--------|-------|------------------|
| AUD-001 | Doc workflow tooling | Missing first-class Scribe tool for creating/updating ARCH/PHASE/CHECKLIST docs means no structured metadata, SQL history, or enforcement of templates; increases drift risk. | Medium | Resolved (manage_docs tool + doc_changes table) | Codex | Files: scribe_mcp/tools/manage_docs.py, scribe_mcp/doc_management/manager.py |
| AUD-002 | append_entry extensibility | append_entry limited to single PROGRESS_LOG; lacks template-driven multi-log support (bug log, suggestion log, etc.), so teams cannot segment entries or automate reminders per log type. | Medium | Resolved (log_config + multi-log routing) | Codex | Files: scribe_mcp/tools/append_entry.py, scribe_mcp/config/log_config.py, config/log_config.json |
| AUD-003 | Plugin loader (`scribe_mcp/plugins/registry.py`) | `spec.loader.exec_module` executes arbitrary Python from `plugins_dir` without signing/allowlisting; malicious plugin can run with repo privileges whenever server starts. Needs policy/permission validation or explicit opt-in. | High | Resolved (config-gated + sandboxed) | Codex | File: scribe_mcp/plugins/registry.py |
| AUD-004 | Agent fallback paths (`scribe_mcp/tools/agent_project_utils.py`) | When AgentContextManager returns a project but storage lookup fails, tool fabricates `/tmp/<project>` roots/logs. Append/rotate can then write outside repo, violating sandbox expectations and Commandment #11. Need safer fallback (load from state/config) or error. | Medium | Resolved (state/config fallback) | Codex | File: scribe_mcp/tools/agent_project_utils.py |
| AUD-005 | Unused sandbox/permission framework (`scribe_mcp/security/sandbox.py`) | Path sandbox + permission checker are never invoked (no references to safe_path/safe_file_operation). Provides a false sense of multi-tenant safety; file operations remain unsandboxed. Need integration or removal. | High | Resolved (utils/files enforces sandbox) | Codex | File: scribe_mcp/utils/files.py |
| AUD-006 | Instruction drift (`AGENTS.md` vs `CLAUDE.md`) | CLAUDE guidance lacks doc-suite workflow, reminders about Commandment #11/#12 enforcement, and import rules parity with AGENTS. Agents receive conflicting instructions, risking security/process violations. | Medium | Resolved (docs updated for parity + new tooling) | Codex | Files: AGENTS.md, CLAUDE.md |
| AUD-007 | Dead GitHub sync tool (`scribe_mcp/tools/sync_to_github.py`) | Stub tool always returns error but still exposed through MCP; wastes audit surface, confuses users, and could be hijacked if ever invoked. Should be removed or feature-flagged to avoid implying availability. | Low | Resolved (tool removed) | Codex | Removal: scribe_mcp/tools/sync_to_github.py |

Add new rows for every finding. If a finding is accepted (won’t fix), capture rationale in the status column and reference the approving stakeholder.

---

## 5. Supporting Notes & Threat Models
Use this section for structured notes that do not yet qualify as findings (e.g., architecture diagrams, data-flow sketches, or questions awaiting answers). Once a note becomes actionable, migrate it into the Findings Log.

---

## 6. Remediation Tracking (Phase 2 Preview)
Summarize how findings will map to remediation work:
- Critical/High issues ➜ immediate backlog items with owners.
  - AUD-003 / AUD-005 demand guardrails around plugin loading + sandbox enforcement.
- Medium/Low ➜ grouped into themed batches (doc parity + UX cleanup, append_entry/log innovation, stale tools removal).
  - AUD-001/002/006/007 captured under “Doc & Logging UX Enhancements”.
  - AUD-004 requires safer session fallback handling touching `agent_project_utils` + append_entry flows.
- Testing requirements ➜ specify target files/tests to update (e.g., `tests/test_append_entry_integration.py` plus new suites covering plugin gating and sandbox enforcement).

This section should evolve once Phase 1 concludes and hand-off to Phase 2 begins.

---

## 7. Evidence & References
- PROGRESS_LOG entries (include timestamps + checklist IDs).
- Git diffs/commits once Phase 2 starts.
- Screenshots or CLI output snippets if needed (stored inline or linked).
- External references (e.g., CVE writeups) that informed mitigations.

---

## 8. Sign-Offs
| Role | Name | Date | Notes |
|------|------|------|-------|
| Auditor | Codex | _TBD_ |  |
| Reviewer | _TBD_ | _TBD_ |  |
| Approver | _TBD_ | _TBD_ |  |

Signatures should reference PROGRESS_LOG entries documenting the approval.
