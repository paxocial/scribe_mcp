# 🏗️ Architecture Guide — Reminders Overhaul
**Author:** Scribe
**Version:** Draft v0.1
**Last Updated:** 2025-10-26 01:01:13 UTC

> TODO: Replace every placeholder and instructional block with project-specific detail. Keep this document in sync with reality—update it the moment architecture or directory structure changes.

---

## 1. Problem Statement <!-- ID: problem_statement -->

**Context:** The current Scribe MCP reminder system lacks configurability and transparency. Users cannot customize reminder thresholds, tones, or timing, making the system feel rigid and impersonal. Additionally, reminder configuration is hardcoded, requiring code changes for behavioral adjustments.

**Goals:**
- Externalize all reminder configuration to editable files
- Enable per-agent and per-project customization
- Implement hot-reload for configuration changes
- Add new reminder categories for better project health monitoring
- Provide CLI tools for preview and configuration management
- Maintain sandbox safety for all file operations

**Non-Goals:**
- Replacing the core reminder engine architecture
- Modifying existing reminder logic behaviors (only making them configurable)
- Changing the append_entry tool interface
- Database schema changes

**Success Metrics:**
- Users can customize reminder behavior without code changes
- Configuration changes apply immediately without server restart
- All reminder file I/O operations respect sandbox boundaries
- CLI tools provide intuitive configuration management
- Existing reminder behaviors remain consistent when using defaults

---

## 2. Requirements & Constraints <!-- ID: requirements -->

**Functional Requirements:**
- External configuration file for all reminder settings
- Per-agent and per-project configuration overrides
- Hot-reload capability for configuration changes
- CLI commands for preview, show-config, and update operations
- New reminder categories: rotation threshold, test health, phase drift
- Sandbox enforcement for all file operations
- Configuration schema validation with clear error messages

**Non-Functional Requirements:**
- Performance: Configuration changes must apply within 1 second
- Reliability: Hot-reload failures must not crash the reminder system
- Security: All file I/O must respect sandbox boundaries
- Compatibility: Existing behaviors must remain unchanged with defaults
- Auditability: All configuration changes must be logged to security log

**Assumptions:**
- Users have appropriate file system permissions for project directories
- Python file watching capabilities (watchdog) are available
- JSON schema validation can be performed on configuration files
- Existing reminder engine logic will remain fundamentally unchanged

**Risks & Mitigations:**
- **Risk:** Configuration file corruption could break reminders
  - **Mitigation:** Schema validation and graceful fallback to defaults
- **Risk:** Hot-reload race conditions during config updates
  - **Mitigation:** Atomic file operations with temporary files
- **Risk:** Path traversal attacks via malicious config
  - **Mitigation:** Strict sandbox path validation and input sanitization

---

## 3. Architecture Overview <!-- ID: overview -->

**Solution Summary:** The reminders overhaul introduces a layered configuration system that externalizes all reminder behavior while maintaining the existing engine's core logic. A JSON-based configuration file provides global defaults, with support for per-project overrides and per-agent customizations. A hot-reload mechanism watches for configuration changes and applies them atomically without interrupting reminder generation. CLI tools provide user-friendly interfaces for previewing, viewing, and updating configurations.

**Component Breakdown:**
- **Configuration Loader**: Handles JSON parsing, schema validation, and config merging with precedence rules
- **File Watcher**: Monitors configuration files for changes and triggers hot-reload events
- **Sandbox Validator**: Ensures all file paths remain within project boundaries
- **CLI Interface**: Provides preview, show-config, and update commands for configuration management
- **Enhanced Reminder Engine**: Extended with configurable thresholds, tones, and categories
- **Audit Logger**: Records all configuration changes to security logs with integrity hashes

**Data Flow:**
1. Configuration files (global → project → agent) are loaded and merged
2. Schema validation ensures configuration integrity
3. Hot-reload watcher monitors for file changes
4. When changes detected: validate → atomically swap → log to security
5. Reminder generation uses merged configuration for behavior customization
6. CLI tools interface with configuration loader for user interactions

**External Integrations:**
- **watchdog library**: File system monitoring for hot-reload capability
- **jsonschema library**: Configuration validation and schema enforcement
- **Existing append_entry tool**: Logging infrastructure for audit trails
- **Project state manager**: Per-project configuration storage and retrieval

---

## 4. Reminders Engine Design <!-- ID: reminders_design -->

### Configuration Schema
**Purpose:** Defines the structure and validation rules for reminder configuration files.

**Interfaces:**
- Input: JSON configuration file
- Output: Validated configuration dictionary
- Schema: JSON Schema with type validation, required fields, and value constraints

**Implementation Notes:**
- Uses jsonschema library for validation
- Supports nested configuration with inheritance
- Provides clear error messages for validation failures
- Includes default values for optional settings

### Hot Reload Mechanism
**Purpose:** Enables configuration changes to apply without server restart.

**Interfaces:**
- Input: File system events from watchdog
- Output: Atomic configuration updates
- Events: File modified, created, deleted

**Implementation Notes:**
- Debounces rapid file changes to prevent reload storms
- Uses atomic file operations (write temp → rename)
- Maintains fallback configuration during reload failures
- Logs all reload attempts to security log

### Per-Agent Configuration
**Purpose:** Allows different agents to have customized reminder behaviors.

**Interfaces:**
- Input: Agent identity from MCP context
- Output: Agent-specific configuration overlay
- Override strategy: Deep merge with agent preferences

**Implementation Notes:**
- Agent names extracted from MCP SDK context
- Supports partial agent configurations (inherits from global)
- Validates agent-specific settings against schema
- Caches agent configurations for performance

### New Reminder Categories
**Purpose:** Expands reminder coverage beyond basic logging and documentation.

**Categories Added:**
1. **Rotation Threshold**: Warns when approaching log rotation limits
2. **Test Health**: Nudges about failing test runs
3. **Phase Drift**: Identifies stalled development phases

**Implementation Notes:**
- Each category has configurable severity and thresholds
- Categories can be individually enabled/disabled
- Integration with existing reminder scoring system
- Customizable suppression rules per category

### Error Handling Strategy
**Failure Modes:**
- **Invalid configuration**: Fallback to defaults, log error, continue operation
- **File system errors**: Log to security log, use cached configuration
- **Schema validation failures**: Detailed error messages, refuse to load
- **Watcher crashes**: Graceful degradation, manual reload available

**Recovery Strategy:**
- Always maintain a known-good configuration in memory
- Automatic retry for transient file system errors
- Manual configuration reload through CLI interface
- Comprehensive logging for debugging configuration issues

---

## 5. Directory Structure (Keep Updated)
```
/home/austin/projects/MCP_SPINE/scribe_mcp/
  # TODO: replace with the real directory tree for Reminders Overhaul
```

> Agents rely on this tree for orientation. Update whenever files are added, removed, or reorganised.

---

## 6. Data & Storage
- **Datastores:** Tables/collections involved, with schema snapshots.
- **Indexes & Performance:** Indexing strategy, retention, archival plans.
- **Migrations:** Steps, ordering, rollback plan.

---

## 5. Security & Sandbox <!-- ID: security -->
- **Sandbox Boundaries:** All file I/O operations must respect project root constraints
- **Path Validation:** Configuration files and reminder outputs use safe path resolution
- **Privilege Separation:** Reminder system runs with minimal required permissions
- **Input Validation:** Configuration schema validation prevents malicious inputs

---

## 6. Testing & Validation Strategy <!-- ID: testing -->
- **Unit Tests:** Configuration loading, hot reload behavior, sandbox path validation
- **Integration Tests:** End-to-end reminder generation with various configurations
- **Security Tests:** Negative test cases for path traversal and symlink attacks
- **Performance Tests:** Config file watching and reminder generation overhead

---

## 7. Directory Structure (Keep Updated)
```
/home/austin/projects/MCP_SPINE/scribe_mcp/
├── scribe_mcp/
│   ├── config/
│   │   └── reminder_config.json          # Main reminder configuration
│   ├── tools/
│   │   ├── reminders.py                   # Updated reminder engine
│   │   └── reminder_cli.py               # CLI interface
│   └── utils/
│       ├── config_loader.py              # Configuration loading and hot-reload
│       └── sandbox_paths.py              # Path validation utilities
├── config/
│   └── log_config.json                   # Multi-log routing configuration
├── tests/
│   ├── test_reminders_config.py         # Configuration tests
│   ├── test_reminders_hot_reload.py     # Hot-reload behavior tests
│   └── test_reminders_security.py       # Sandbox security tests
└── docs/dev_plans/reminders_overhaul/
    ├── ARCHITECTURE_GUIDE.md
    ├── PHASE_PLAN.md
    ├── CHECKLIST.md
    └── PROGRESS_LOG.md
```

---

## 8. Data & Storage
- **Configuration Schema:** JSON schema validation for reminder config files
- **Hot Reload State:** In-memory caching with atomic config swapping
- **Audit Trail:** All configuration changes logged to security log
- **Project Overrides:** Per-project configuration stored in project state

---

## 9. Open Questions & Follow-Ups
| Item | Owner | Status | Notes |
| ---- | ----- | ------ | ----- |
| TBD | TBD | TBD | Capture decisions, blockers, or research tasks. |

Close each question once answered and reference the relevant section above.

---

## 10. References & Appendix
- Link to diagrams, ADRs, research notes, or external specs.
- Include raw data, calculations, or supporting materials.

