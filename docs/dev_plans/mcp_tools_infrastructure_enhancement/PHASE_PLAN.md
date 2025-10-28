
# ⚙️ Phase Plan — MCP Tools Infrastructure Enhancement
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2025-10-27 13:14:09 UTC

> Execution roadmap for MCP Tools Infrastructure Enhancement.

---
## Phase Overview
<!-- ID: phase_overview -->
| Phase | Goal | Key Deliverables | Confidence (0-1) |
|-------|------|------------------|------------------|
| Phase 0 — Foundation | Stabilize document writes and storage. | Async atomic write, SQLite mirror | 0.90 |
| Phase 1 — Templates | Introduce advanced Jinja2 template system. | Base templates, Custom template discovery | 0.80 |
Update this table as the project evolves. Confidence values should change as knowledge increases.


---
## Phase 0 — Phase 0 — Foundation
<!-- ID: phase_0 -->
**Objective:** Create unified tool framework with context safety mechanisms to resolve parameter serialization and prevent token blowup.

**Key Tasks:**
- Design BaseTool abstract class with standardized parameter handling
- Implement ParameterNormalizer utility for consistent JSON parsing
- Create ToolRegistry for tool discovery and permissions
- Update existing tools (append_entry, query_entries, set_project) to use BaseTool
- **CRITICAL**: Implement ContextManager and ResponsePaginator for token safety
- **CRITICAL**: Fix list_projects with intelligent filtering and pagination

**Deliverables:**
- Unified tool framework with consistent parameter normalization
- **Context Safety Layer** (utils/context_safety.py) with:
  - Smart project filtering (excludes test projects)
  - Pagination for large datasets
  - Token limit enforcement and warnings
  - Intelligent defaults (5 recent projects)
- Updated core tools with proper dict/list parameter handling
- Plugin integration framework for external tools
- Comprehensive test suite validating all scenarios

**Acceptance Criteria:**
- [ ] All dict parameters handled consistently across tools
- [ ] Plugin tools can leverage core infrastructure  
- [ ] No "string indices must be integers" errors
- [ ] Backwards compatibility maintained
- [ ] Test coverage > 90% for parameter scenarios
- [ ] **list_projects defaults to 5 most recent active projects**
- [ ] **Auto-filtering of test/temp projects**
- [ ] **Token warnings before context overflow**
- [ ] **Pagination available for large project lists**
- [ ] **Graceful degradation to compact mode**
<!-- ID: phase_1 -->
**Objective:** Introduce advanced Jinja2 template system.

**Key Tasks:**
- Add inheritance- Add sandboxing

**Deliverables:**
- Base templates- Custom template discovery

**Acceptance Criteria:**
- [ ] All built-in templates render (proof: pytest)

**Dependencies:** Phase 0

**Notes:** Focus on template authoring UX.


---
## Milestone Tracking
<!-- ID: milestone_tracking -->
| Milestone | Target Date | Owner | Status | Evidence/Link |
|-----------|-------------|-------|--------|---------------|
| Foundation Complete | 2025-10-29 | DevTeam | 🚧 In Progress | PROGRESS_LOG.md |
| Template Engine Ship | 2025-11-02 | DevTeam | ⏳ Planned | Phase 1 tasks |
Update status and evidence as work progresses. Always link to PROGRESS_LOG entries or commits.


---
## Retro Notes & Adjustments
<!-- ID: retro_notes -->
- Summarise lessons learned after each phase completes.  
- Document any scope changes or re-planning decisions here.


---