---
id: scribe_sentinel_concurrency_v1-phase_plan
title: "\u2699\uFE0F Phase Plan \u2014 scribe_sentinel_concurrency_v1"
doc_type: phase_plan
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

# ⚙️ Phase Plan — scribe_sentinel_concurrency_v1
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-01-02 04:17:01 UTC

> Execution roadmap for scribe_sentinel_concurrency_v1.

---
## Phase Overview
<!-- ID: phase_overview -->
| Phase | Goal | Key Deliverables | Confidence (0-1) |
|-------|------|------------------|------------------|
| Phase 0 — Project Setup | Bootstrap dev_plan docs + audit report scaffold. | ARCH/PHASE/CHECKLIST seeded, AUDIT_REPORT created | 0.90 |
| Phase 1 — Audit | Document current state with file/line citations. | AUDIT_REPORT.md sections A–E filled | 0.60 |
| Phase 2 — Spec (Revision Plan #2) | Finalize design + acceptance criteria for approval with current_project quarantine + reconnect rules. | Updated ARCH/PHASE/CHECKLIST + stop gate summary | 0.50 |
| Phase 3 — Implementation | Implement sentinel mode, session isolation, read_file, query_entries. | Code changes + tool updates | 0.40 |
| Phase 4 — Proof | Validate with tests and demos. | Test suite + evidence links | 0.40 |
Update this table as the project evolves. Confidence values should change as knowledge increases.
<!-- ID: phase_0 -->
## Phase 0 — Project Setup
**Objective:** Bootstrap project docs and audit scaffold.

**Key Tasks:**
- Create new dev_plan project and read progress log.
- Seed ARCHITECTURE_GUIDE, PHASE_PLAN, CHECKLIST via manage_docs.
- Create AUDIT_REPORT.md with required sections.

**Deliverables:**
- Dev_plan doc suite + audit report stub.

**Acceptance Criteria:**
- [ ] All docs created and updated via manage_docs (proof: DOC_LOG.md entries).

**Dependencies:** None

**Notes:** No code changes allowed in this phase.
<!-- ID: phase_1 -->
## Phase 1 — Audit
**Objective:** Audit current implementation (no code changes).

**Key Tasks:**
- Locate project context storage and scope (global vs session). [A]
- Inspect tool call routing and session/client identity availability. [B]
- Trace log path resolution and current write locations. [C]
- Review query_entries capabilities + extension points. [D]
- Identify best insertion point for read_file tool and read provenance logging. [E]

**Deliverables:**
- AUDIT_REPORT.md populated with file/line citations for sections A–E.

**Acceptance Criteria:**
- [ ] Audit report complete with citations and risks recorded.

**Dependencies:** Phase 0

**Notes:** Stop if any ambiguity blocks safe design decisions.

---
## Phase 2 — Spec (Revision Plan #2)
**Objective:** Finalize design and acceptance criteria for approval, including current_project quarantine.

**Key Tasks:**
- Define ExecutionContext schema, router enforcement, and hard-fail behavior. [A,B]
- Define session identity source + reconnect fingerprint rules. [B]
- Define current_project fallback rules (project mode only; sentinel forbidden). [A]
- Specify sentinel directory layout + log schemas. [C]
- Define bug/security linkage fields and landing status gates. [C]
- Define read_file allow/deny policy + provenance fields. [E]
- Define WAL/file-lock acceptance criteria and ordering. [C]
- Define query_entries sentinel scope/types + filters. [D]
- Draft stop-gate checklist and approval request. [A–E]

**Deliverables:**
- Updated ARCHITECTURE_GUIDE.md, PHASE_PLAN.md, CHECKLIST.md.
- Stop-gate summary logged to PROGRESS_LOG.

**Acceptance Criteria:**
- [ ] User approval received before implementation.

**Dependencies:** Phase 1

---
## Phase 3 — Implementation
**Objective:** Implement sentinel mode, session isolation, read_file tool, and query_entries extensions.

**Key Tasks:**
- Session-scoped context and path validation hard-fails.
- Sentinel daily logging (MD + JSONL).
- read_file tool with provenance logging.
- query_entries sentinel search support.

**Deliverables:**
- Code changes for tools, logging, and context isolation.

**Acceptance Criteria:**
- [ ] All required functionality implemented and reviewed.

**Dependencies:** Phase 2

---
## Phase 4 — Proof
**Objective:** Validate with tests and demos.

**Key Tasks:**
- Tests for mode gating, path enforcement, session isolation.
- Tests for read_file logging + sha256.
- Tests for append-safe sentinel JSONL logging.
- query_entries sentinel search regression tests.

**Deliverables:**
- Test results + evidence links in CHECKLIST.

**Acceptance Criteria:**
- [ ] All tests pass with evidence recorded.

**Dependencies:** Phase 3
<!-- ID: milestone_tracking -->
| Milestone | Target Date | Owner | Status | Evidence/Link |
|-----------|-------------|-------|--------|---------------|
| Audit Complete | TBD | Codex | ⏳ Planned | AUDIT_REPORT.md |
| Spec Approved | TBD | Carl | ⏳ Planned | PROGRESS_LOG.md |
| Implementation Complete | TBD | Codex | ⏳ Planned | PROGRESS_LOG.md |
| Proof Complete | TBD | Codex | ⏳ Planned | CHECKLIST.md |
Update status and evidence as work progresses. Always link to PROGRESS_LOG entries or commits.
<!-- ID: retro_notes -->
- Capture re-plans, scope shifts, and validation gaps after each phase.
- Link retro notes to PROGRESS_LOG entries for traceability.
