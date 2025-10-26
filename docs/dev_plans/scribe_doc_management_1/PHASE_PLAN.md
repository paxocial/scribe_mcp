# ⚙️ Phase Plan — scribe_doc_management_1
**Author:** Scribe
**Version:** Draft v0.1
**Last Updated:** 2025-10-26 01:30:03 UTC

> TODO: Derive this plan from the Architecture Guide. Each phase should deliver a reviewable increment and reference the checklist items it will produce.

---

## Phase Overview
<!-- ID: phase_overview -->
| Phase | Goal | Key Deliverables | Confidence (0-1) |
|-------|------|------------------|------------------|
| Phase 0 | Foundation Fixes | Async bug fix, database schema, basic reliability | 0.90 |
| Phase 1 | Template Engine | Jinja2 integration, custom templates, enhanced rendering | 0.80 |
| Phase 2 | Sync & Change Tracking | Bidirectional sync, file watcher, git-level history | 0.75 |

Update this table as the project evolves. Confidence values should change as knowledge increases.

---

## ✅ Phase 0 — Foundation Fixes & Database Enhancement
<!-- ID: phase_0 -->
**Objective:** Fix critical silent failures and establish robust database foundation for document management

**Key Tasks:**
- [x] Fix async/await bug in manager.py (add async_atomic_write function)
- [x] Extend database schema with document_sections, custom_templates, document_changes tables
- [x] Implement database migration system for new schema
- [x] Add comprehensive error handling and validation to manage_docs operations
- [x] Create post-write verification to eliminate silent failures
- [x] Add structured logging for all document operations

**Deliverables:**
- Working manage_docs tool with 100% reliable file operations
- Enhanced SQLite database with document content mirroring
- Database migration system for backwards compatibility
- Comprehensive test coverage for document operations

**Acceptance Criteria:**
- [x] All manage_docs operations succeed or raise appropriate errors (no silent failures)
- [x] File content always matches expected result after operations
- [x] Database properly mirrors document content after each operation
- [x] All existing projects continue to work without manual intervention
- [x] Test suite demonstrates 100% reliability of document operations

**Dependencies:** SQLite database access, Jinja2 library (for later phases)
**Estimated Duration:** 2-3 days
**Notes:** This phase fixes the critical bug that prevents document editing and establishes the foundation for all subsequent phases.

---

## ✅ Phase 1 — Jinja2 Template Engine & Custom Templates
<!-- ID: phase_1 -->
**Objective:** Replace basic string substitution with professional Jinja2 templating and enable custom template creation

**Key Tasks:**
- [x] Integrate Jinja2 template engine with security sandboxing
- [x] Replace simple {{variable}} substitution with Jinja2 rendering
- [x] Implement template inheritance and block system
- [x] Create custom template discovery system (.scribe/templates/)
- [x] Add JSON-based custom variable definitions
- [x] Implement template validation and error reporting
- [x] Create migration from old templates to Jinja2 format *(legacy fallback supported)*
- [x] Add template testing and preview capabilities *(via validate_only and dry-run modes)*

**Deliverables:**
- Jinja2-based template engine with inheritance and includes
- Custom template system with simple file-based management
- Variable definition system with JSON configuration
- Template validation and error reporting
- Backward compatibility with existing template variables

**Acceptance Criteria:**
- [x] All existing templates render correctly with Jinja2 engine
- [x] Users can create custom templates with Jinja2 syntax
- [x] Custom variables defined in JSON are available in templates
- [x] Template inheritance works for base templates and extensions
- [x] Template errors provide clear, actionable feedback
- [x] Template rendering performance is acceptable (<100ms for typical documents)

**Dependencies:** Phase 0 completion, Jinja2 library
**Estimated Duration:** 3-4 days
**Notes:** This phase dramatically enhances template capabilities while maintaining simplicity for basic use cases.

## Phase 2 — Bidirectional Sync & Change Tracking
<!-- ID: phase_2 -->
**Objective:** Implement file system monitoring, database synchronization, and git-level change tracking

**Key Tasks:**
- [ ] Implement file system watcher for manual edit detection
- [ ] Create bidirectional sync manager with conflict resolution
- [ ] Add git-level change tracking with commit messages
- [ ] Implement change diff visualization and history
- [ ] Create conflict resolution system with manual override
- [ ] Add file system integrity verification
- [ ] Implement database change logging and rollback
- [ ] Add performance monitoring and metrics collection

**Deliverables:**
- File system watcher with efficient change detection
- Bidirectional sync manager with timestamp-based conflict resolution
- Change tracking system with git-style commit messages
- Conflict resolution interface and manual override capabilities
- Performance monitoring and alerting system

**Acceptance Criteria:**
- [ ] Manual file edits are detected and synced to database within 5 seconds
- [ ] Conflicts are detected and resolved with clear user notifications
- [ ] Complete change history is available with diff visualization
- [ ] System handles concurrent edits without data loss
- [ ] File watcher performance doesn't impact overall system responsiveness
- [ ] Change tracking provides sufficient detail for audit trails

**Dependencies:** Phase 1 completion, watchdog library, git integration
**Estimated Duration:** 4-5 days
**Notes:** This phase completes the core Document Management 2.0 vision with enterprise-grade change tracking.

---

## Milestone Tracking
<!-- ID: milestone_tracking -->
| Milestone | Target Date | Owner | Status | Evidence/Link |
|-----------|-------------|-------|--------|---------------|
| Critical Bug Analysis Complete | 2025-10-26 | InvestigatorAgent | ✅ Complete | BUG_REPORT_MANAGE_DOCS.md |
| Architecture Guide Complete | 2025-10-26 | SystemArchitect | ✅ Complete | ARCHITECTURE_GUIDE.md |
| Phase Plan Complete | 2025-10-26 | SystemArchitect | ✅ Complete | PHASE_PLAN.md |
| Phase 0 - Foundation Fixes | 2025-10-29 | DevTeam | 🚧 In Progress | PROGRESS_LOG.md entries |
| Phase 1 - Template Engine | 2025-11-02 | DevTeam | ⏳ Planned | Phase 1 tasks |
| Phase 2 - Sync & Tracking | 2025-11-07 | DevTeam | ⏳ Planned | Phase 2 tasks |

Update status and evidence as work progresses. Always link to PROGRESS_LOG entries or commits.

---

## Retro Notes & Adjustments
<!-- ID: retro_notes -->
- Summarise lessons learned after each phase completes.
- Document any scope changes or re-planning here.

