# 🏗️ Architecture Guide — scribe_doc_management_1
**Author:** Scribe
**Version:** Draft v0.1
**Last Updated:** 2025-10-26 01:30:03 UTC

> TODO: Replace every placeholder and instructional block with project-specific detail. Keep this document in sync with reality—update it the moment architecture or directory structure changes.

---

## 1. Problem Statement
<!-- ID: problem_statement -->
- **Context:** The Scribe MCP doc management system has critical silent failures where document editing operations appear successful but don't persist changes to disk. The current templating system uses basic string substitution that's too fragile for complex document structures. Users need robust document management with version control and easy custom template creation.
- **Goals:**
  - Fix silent search/replace failures in manage_docs operations with proper error handling and verification
  - Implement robust document management with database mirroring while keeping file system authoritative
  - Add professional-grade Jinja2 templating capabilities with inheritance and custom variables
  - Create git-level change tracking and version control for all document modifications
  - Enable easy custom template creation for users with simple {{variable}} patterns
  - Ensure zero silent failures - all operations must be properly validated and reported
- **Non-Goals:**
  - Break existing file-based workflows or require users to change their git habits
  - Force users to learn complex new systems immediately - maintain simplicity for basic use cases
  - Create dependency on external services or web interfaces unless absolutely necessary
  - Replace the existing atomic write system that works well when called correctly
- **Success Metrics:**
  - 100% reliability of document editing operations with post-write verification
  - Zero silent failures - all operations properly succeed or raise appropriate errors
  - Custom templates can be created and used easily by non-technical users
  - Complete change history and diff tracking available for all document modifications
  - Bidirectional sync between file system and database works seamlessly without conflicts

---

## 2. Requirements & Constraints
<!-- ID: requirements_constraints -->
- **Functional Requirements:**
  - Reliable document editing with immediate persistence to file system
  - Atomic write operations with verification and rollback capabilities
  - Database mirroring of all document content for search and version tracking
  - Jinja2 template engine with inheritance, includes, and custom variables
  - Bidirectional synchronization between file system and database
  - File watcher for detecting manual edits and triggering database sync
  - Git-level change tracking with commit messages and diff history
  - Custom template system with simple file-based management
  - Section-level document editing with proper validation
  - Conflict resolution for simultaneous edits
- **Non-Functional Requirements:**
  - File system must always remain authoritative source of truth
  - Zero silent failures - all operations must succeed or raise appropriate errors
  - Performance must not degrade with large documents or many projects
  - Backward compatibility with existing project structures
  - Security sandboxing to prevent path traversal and unauthorized access
  - Atomic operations to prevent data corruption during concurrent access
- **Assumptions:**
  - Users have basic familiarity with markdown and git workflows
  - File system permissions allow read/write access to project directories
  - SQLite database is available for local storage and indexing
  - Python asyncio environment is available for async operations
  - Jinja2 library can be added as a dependency for template rendering
- **Risks & Mitigations:**
  - **Risk:** Bidirectional sync could cause data conflicts between file and database
    **Mitigation:** Implement timestamp-based conflict resolution with manual override options
  - **Risk:** File system watcher could miss changes or cause performance issues
    **Mitigation:** Use efficient file watching with debouncing and fallback polling
  - **Risk:** Complex Jinja2 templates might be confusing for non-technical users
    **Mitigation:** Provide simple default templates and extensive documentation
  - **Risk:** Database corruption could affect document management
    **Mitigation:** Regular backups and integrity checks with file system fallback

---

## 3. Architecture Overview
<!-- ID: architecture_overview -->
- **Solution Summary:** Document Management 2.0 implements a robust bidirectional sync system between the file system (authoritative source) and SQLite database (mirror/index). The system fixes critical silent failures by adding comprehensive validation, error handling, and post-write verification. It replaces basic string substitution with Jinja2 templating for professional-grade document generation while maintaining simplicity for basic use cases. A file watcher monitors manual edits and syncs changes to the database, providing git-level change tracking and conflict resolution.

- **Component Breakdown:**
  - **Sync Manager:** Coordinates bidirectional sync between file system and database with conflict resolution
  - **Template Engine:** Jinja2-based rendering with inheritance, includes, and custom variable support
  - **File Watcher:** Monitors file system changes and triggers database synchronization
  - **Change Logger:** Git-style change tracking with commit messages and diff history
  - **Document Manager:** Enhanced manage_docs API with validation and error handling
  - **Custom Template System:** File-based template discovery with JSON variable definitions
  - **Atomic Write Layer:** Bulletproof file operations with verification and rollback

- **Data Flow:**
  1. **API Changes** → Database → Atomic File Write → Verification → Change Log
  2. **Manual Edits** → File Watcher → Database Sync → Change Detection → Notification
  3. **Template Rendering** → Jinja2 Engine → Context Variables → Generated Content → File System
  4. **Conflict Resolution** → Timestamp Comparison → Manual Override → Record Resolution

- **External Integrations:**
  - **Jinja2:** Professional templating engine with inheritance and custom filters
  - **SQLite:** Local database for content mirroring and change tracking
  - **Watchdog:** File system monitoring for detecting manual edits
  - **Git Integration:** Change tracking and version control (future enhancement)

---

## 4. Detailed Design
<!-- ID: detailed_design -->

### 4.1 Sync Manager Component
1. **Purpose:** Coordinates bidirectional synchronization between file system and SQLite database, ensuring data consistency and handling conflicts.
2. **Interfaces:**
   - **Input:** File paths, content changes, timestamps, metadata
   - **Output:** Sync status, conflict notifications, change records
   - **Data Contracts:** DocumentSection, ChangeRecord, ConflictRecord models
3. **Implementation Notes:**
   - Uses asyncio for non-blocking sync operations
   - Implements timestamp-based conflict resolution with LWW (Last Write Wins)
   - Maintains in-memory cache of recent changes for performance
   - Uses SQLite transactions for atomic database updates
4. **Error Handling:**
   - Database failures trigger file system rollback
   - File write failures prevent database updates
   - Conflicts are logged and flagged for manual resolution
   - Network/storage issues cause exponential backoff retries

### 4.2 Template Engine Component
1. **Purpose:** Renders Jinja2 templates with rich context objects, custom variables, and inheritance support.
2. **Interfaces:**
   - **Input:** Template files, context dictionaries, variable definitions
   - **Output:** Rendered markdown content, template metadata
   - **Data Contracts:** TemplateContext, VariableDefinition, RenderResult
3. **Implementation Notes:**
   - Jinja2 environment with custom filters and security sandboxing
   - Template inheritance using `{% extends %}` and `{% block %}` syntax
   - Custom variable system with JSON configuration files
   - Context enrichment with project metadata and computed values
4. **Error Handling:**
   - Template syntax errors provide detailed line/column information
   - Missing variables default to empty string with warning logs
   - Circular template inheritance detected and prevented
   - Security errors block template execution entirely

### 4.3 File Watcher Component
1. **Purpose:** Monitors file system for manual edits and triggers database synchronization.
2. **Interfaces:**
   - **Input:** Watch directories, file patterns, event callbacks
   - **Output:** File change events, modification timestamps
   - **Data Contracts:** FileChangeEvent, FileSystemMetadata
3. **Implementation Notes:**
   - Uses watchdog library for efficient cross-platform file monitoring
   - Debouncing to prevent excessive sync operations during rapid edits
   - Recursive directory watching with configurable ignore patterns
   - Background thread with async event queue integration
4. **Error Handling:**
   - Permission errors logged and directory skipped
   - Temporary unavailability triggers retry with exponential backoff
   - Malformed file paths are ignored with warning logs
   - Watcher failures fall back to periodic polling

### 4.4 Document Manager Component
1. **Purpose:** Enhanced manage_docs API with robust validation, error handling, and verification.
2. **Interfaces:**
   - **Input:** Document operations, section content, edit parameters
   - **Output:** Operation results, success/failure status, change summaries
   - **Data Contracts:** DocumentOperation, SectionEdit, OperationResult
3. **Implementation Notes:**
   - Pre-edit validation of content and section markers
   - Post-write verification comparing file content to expected result
   - Atomic section replacement with proper newline handling
   - Comprehensive logging and change tracking
4. **Error Handling:**
   - Section not found errors provide specific anchor information
   - Write failures trigger rollback with detailed error context
   - Validation errors include suggestions for fixing common issues
   - All errors are logged with full context for debugging

---

## 5. Directory Structure (Keep Updated)
<!-- ID: directory_structure -->
```
/home/austin/projects/Scribe/MCP_SPINE/
├── scribe_mcp/                          # Main MCP server package
│   ├── doc_management/                 # Enhanced document management
│   │   ├── manager.py                  # Core document management logic
│   │   ├── sync_manager.py             # NEW: Bidirectional sync coordination
│   │   ├── template_engine.py          # NEW: Jinja2 template rendering
│   │   ├── file_watcher.py             # NEW: File system monitoring
│   │   └── change_logger.py            # NEW: Git-style change tracking
│   ├── tools/                          # MCP tool implementations
│   │   ├── manage_docs.py              # Enhanced with validation and verification
│   │   ├── set_project.py              # Project setup and configuration
│   │   └── append_entry.py             # Progress logging with metadata
│   ├── storage/                        # Database layer
│   │   ├── models.py                   # Extended with new document models
│   │   ├── sqlite.py                   # Enhanced with document_sections support
│   │   └── migrations/                 # NEW: Database schema migrations
│   ├── templates/                      # Template system
│   │   ├── documents/                  # Base document templates
│   │   ├── fragments/                  # Reusable template fragments
│   │   └── custom/                     # NEW: User custom templates
│   └── utils/
│       ├── files.py                    # Enhanced with async_atomic_write
│       └── template_utils.py           # NEW: Template utilities and helpers
├── docs/dev_plans/scribe_doc_management_1/  # This project's documentation
│   ├── ARCHITECTURE_GUIDE.md           # ✅ This file - system design
│   ├── PHASE_PLAN.md                   # 📋 Implementation phases
│   ├── CHECKLIST.md                    # ✅ Task tracking and verification
│   ├── PROGRESS_LOG.md                 # 📝 Detailed change history
│   ├── BUG_REPORT_MANAGE_DOCS.md       # 🐛 Critical bug analysis
│   └── .scribe/                        # NEW: Project-specific configuration
│       ├── templates/                  # Custom templates for this project
│       └── variables.json              # Custom variable definitions
└── tests/                              # Test suite
    ├── test_doc_management/            # NEW: Document management tests
    └── test_integration/               # NEW: End-to-end integration tests
```

> Agents rely on this tree for orientation. Update whenever files are added, removed, or reorganised.

---

## 6. Data & Storage
<!-- ID: data_storage -->
- **Datastores:**
  - **SQLite Database (Primary):**
    - `projects` - Existing project metadata
    - `document_sections` - NEW: Mirrored document content by section
    - `custom_templates` - NEW: User-defined templates and variables
    - `document_changes` - NEW: Git-style change tracking
    - `sync_status` - NEW: Bidirectional sync state tracking
  - **File System (Authoritative):**
    - Markdown documents with `<!-- ID: section_name -->` markers
    - Template files with Jinja2 syntax
    - JSON configuration files for custom variables
    - Change logs and backup files

- **Indexes & Performance:**
  - **Primary Keys:** All tables have auto-incrementing integer primary keys
  - **Foreign Keys:** document_sections.project_id, custom_templates.project_id
  - **Search Indexes:** document_sections.content (FTS5), document_changes.change_summary
  - **Performance Indexes:** document_sections.updated_at, sync_status.last_sync
  - **Retention:** Change history retained for 1 year, older records archived quarterly

- **Migrations:**
  - **Step 1:** Create new tables (document_sections, custom_templates, document_changes, sync_status)
  - **Step 2:** Populate document_sections from existing files via one-time import
  - **Step 3:** Add indexes and constraints after data migration
  - **Step 4:** Update application code to use new schema
  - **Rollback Plan:** Backup existing database, maintain reverse migration scripts

---

## 7. Testing & Validation Strategy
<!-- ID: testing_strategy -->
- **Unit Tests:**
  - **Target:** 95% code coverage for all new components
  - **Focus:** Document manager validation, template engine rendering, sync manager operations
  - **Tools:** pytest with asyncio support, mock file system operations
  - **Coverage:** Edge cases, error conditions, boundary testing

- **Integration Tests:**
  - **Environment:** Temporary project directories with isolated SQLite databases
  - **Fixtures:** Sample documents with various section structures and template complexities
  - **Scenarios:** Bidirectional sync under concurrent access, conflict resolution, file watcher reliability
  - **Data Sets:** Real project documentation with custom templates and variables

- **Manual QA:**
  - **Acceptance Criteria:** All manage_docs operations work with zero silent failures
  - **User Workflows:** Template creation, document editing, conflict resolution
  - **Performance:** Large documents (10MB+) and multiple concurrent projects
  - **Edge Cases:** Manual file edits during sync operations, database corruption recovery

- **Observability:**
  - **Logging:** Structured JSON logs with operation context and timing metrics
  - **Metrics:** Operation success rates, sync latency, template rendering performance
  - **Tracing:** End-to-end request tracking from API call through file system update
  - **Alerting:** Silent failure detection, sync conflict warnings, performance degradation

---

## 8. Deployment & Operations
<!-- ID: deployment_operations -->
- **Environments:**
  - **Development:** Local SQLite database with file system watcher disabled
  - **Testing:** Temporary isolated databases with synthetic test data
  - **Production:** Persistent SQLite with full sync manager and file watcher enabled
  - **Configuration Differences:** Sync intervals, logging levels, performance monitoring

- **Release Process:**
  - **Automation:** Database migrations run automatically on first startup
  - **Approvals:** Code review required for database schema changes
  - **Rollback:** Database backup before migration, reverse migration scripts maintained
  - **Validation:** Post-deployment smoke tests verify all document operations

- **Configuration Management:**
  - **Database Settings:** Connection strings, timeout values, sync intervals
  - **Template Paths:** Custom template directories, variable file locations
  - **Feature Flags:** Enable/disable file watcher, conflict resolution strategies
  - **Runtime Toggles:** Debug logging, performance monitoring, sync behavior

- **Maintenance & Ownership:**
  - **On-call:** Document system reliability, sync conflict resolution assistance
  - **SLOs:** 99.9% document operation success rate, <5s sync latency
  - **Future Work:** Git integration, web UI for template management, advanced conflict resolution
  - **Monitoring:** Database health, file system performance, template rendering metrics

---

## 9. Open Questions & Follow-Ups
<!-- ID: open_questions -->
| Item | Owner | Status | Notes |
| ---- | ----- | ------ | ----- |
| File watcher library selection | TBD | Research | Evaluate watchdog vs inotify vs polling for cross-platform support |
| Jinja2 security sandboxing approach | TBD | Research | Determine best practices for template security and variable access |
| Database migration strategy | TBD | Planning | How to handle existing projects during schema upgrade |
| Conflict resolution UI requirements | TBD | Planning | Determine if CLI notification is sufficient or if interactive resolution needed |
| Performance benchmarking targets | TBD | Planning | Define acceptable latency for document operations and sync |

---

## 10. References & Appendix
<!-- ID: references_appendix -->
- **Critical Bug Report:** `/docs/dev_plans/scribe_doc_management_1/BUG_REPORT_MANAGE_DOCS.md` - Comprehensive analysis of manage_docs silent failure
- **Original Investigation:** Discovery of async/await mismatch in manager.py line 83
- **Implementation Plan:** Document Management 2.0 architecture with bidirectional sync and Jinja2 templates
- **Database Schema Design:** Extended SQLite models for document_sections, custom_templates, document_changes
- **Testing Strategy:** 95% code coverage target with integration testing for sync operations
- **Performance Requirements:** <5s sync latency, 99.9% operation success rate, support for 10MB+ documents

