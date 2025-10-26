# 🏗️ Architecture Guide — Enhanced Log Rotation with Auditability
**Author:** SecurityDev
**Version:** v1.0
**Last Updated:** 2025-10-24 11:05:00 UTC

## 1. Problem Statement

### **Context**
The current Scribe MCP log rotation system lacks security features and auditability. When logs are rotated, the system simply creates empty files without:
- Maintaining project context across rotations
- Linking to previous log files
- Providing integrity verification
- Creating an audit trail of rotation events

### **Goals**
- **Security:** Implement file integrity hashing (SHA-256) to detect tampering
- **Auditability:** Create comprehensive rotation metadata and audit trails
- **Continuity:** Maintain project context and linking across log rotations
- **Verification:** Provide tools to verify log integrity and rotation history
- **Compliance:** Meet enterprise-grade audit requirements for log management

### **Non-Goals**
- Modify existing append_entry functionality
- Change database schema or storage backends
- Implement external log storage or cloud integration
- Add encryption (beyond integrity hashing)

### **Success Metrics**
- **100%** of log rotations include integrity hashes
- **100%** of new logs include previous log references
- **<5 seconds** additional overhead per rotation operation
- **Zero** failed integrity verifications in production
- **Complete** audit trail available for all rotation events

---

## 2. Requirements & Constraints

### **Functional Requirements**
- **FR-1:** System must generate SHA-256 hash for each rotated log file
- **FR-2:** System must count entries in archived logs before rotation
- **FR-3:** System must create rotation metadata with unique UUID per rotation
- **FR-4:** System must maintain sequential page numbering across rotations
- **FR-5:** System must include previous log path and hash in new log headers
- **FR-6:** System must store rotation audit trail in project state
- **FR-7:** System must provide integrity verification functions
- **FR-8:** System must support rotation history queries

### **Non-Functional Requirements**
- **Performance:** Rotation operations must complete within 5 seconds for logs up to 10MB
- **Reliability:** 99.9% success rate for rotation operations
- **Security:** Hashing algorithm must be cryptographically secure (SHA-256)
- **Compatibility:** Must work with existing SQLite and PostgreSQL backends
- **Backward Compatibility:** Existing rotation API must remain functional

### **Assumptions**
- File system supports standard file operations (read, write, rename)
- Scribe MCP server has write permissions to project directories
- Template system is available and functional
- Project state management is persistent

### **Risks & Mitigations**
- **Risk:** Hash computation performance degradation on large logs
  - **Mitigation:** Implement streaming hash computation, set size limits
- **Risk:** Template system failures during rotation
  - **Mitigation:** Fallback to basic file creation with minimal headers
- **Risk:** Race conditions during concurrent rotation attempts
  - **Mitigation:** Implement file-level locking and rotation state tracking
- **Risk:** Storage overhead for rotation metadata
  - **Mitigation:** Implement metadata rotation limits and cleanup policies

---

## 3. Architecture Overview

### **Solution Summary**
The Enhanced Log Rotation system builds upon the existing Scribe MCP rotation mechanism by adding security, auditability, and continuity features. The system maintains backward compatibility while introducing comprehensive file integrity verification, metadata tracking, and template-based log generation that preserves project context across rotations.

The solution integrates three core components: an enhanced rotation engine that performs file hashing and metadata collection, a template system that generates context-rich new log files, and an audit trail manager that maintains rotation history and provides verification capabilities. This approach ensures that every rotation event is cryptographically verifiable and auditable while maintaining the seamless user experience of the existing system.

### **Component Breakdown**

| Component | Responsibilities | Interactions |
|-----------|------------------|--------------|
| **Enhanced Rotation Engine** (`rotate_log.py`) | File hashing, entry counting, metadata collection, archive management | Template System, Audit Trail Manager, Storage Backend |
| **Template Integration** (`templates/`) | Generate context-rich new logs, maintain project continuity, rotation-specific headers | Rotation Engine, Project State Manager |
| **Audit Trail Manager** (`utils/audit.py`) | Store rotation metadata, maintain history, provide verification APIs | Rotation Engine, Storage Backend, State Manager |
| **Integrity Verifier** (`utils/integrity.py`) | SHA-256 hash computation, file verification, tamper detection | Rotation Engine, Audit Trail Manager |
| **Rotation Metadata Store** (`state/rotation.json`) | Persistent rotation history, metadata persistence | Audit Trail Manager, Project State Manager |

### **Data Flow**

```
1. User calls rotate_log()
   ↓
2. Enhanced Rotation Engine:
   - Hash current log file (SHA-256)
   - Count log entries
   - Generate rotation UUID
   - Create rotation metadata
   ↓
3. Archive Operations:
   - Move log to archive with timestamp
   - Store hash and metadata
   ↓
4. Template Generation:
   - Load progress log template
   - Inject rotation context
   - Include previous log reference
   - Generate fresh log with headers
   ↓
5. Audit Trail Update:
   - Store rotation record
   - Update project state
   - Maintain sequence numbering
   ↓
6. Return rotation result with metadata
```

### **External Integrations**
- **Template System:** Reuses existing `generate_doc_templates` infrastructure
- **Storage Backends:** Compatible with SQLite and PostgreSQL for metadata storage
- **File System:** Standard file operations for log archiving and creation
- **State Management:** Integrates with existing project state persistence

---

## 4. Detailed Design

### **Enhanced Rotation Engine** (`rotate_log.py`)
**Purpose:** Core rotation logic with security and auditability features

**Interfaces:**
- Input: `rotate_log(suffix: Optional[str] = None)`
- Output: `{ok: bool, archived_to: str, rotation_metadata: dict, ...}`

**Implementation Notes:**
- Uses `hashlib.sha256()` for file integrity
- Streaming hash computation for large files
- UUID generation via `uuid.uuid4()`
- Entry counting via line parsing

**Error Handling:**
- Template system failures → fallback to basic file creation
- Hash computation errors → log warning, continue rotation
- File system errors → detailed error messages, rollback on failure

### **Audit Trail Manager** (new: `utils/audit.py`)
**Purpose:** Persistent storage and retrieval of rotation metadata

**Interfaces:**
- `store_rotation_metadata(project_name: str, metadata: dict)`
- `get_rotation_history(project_name: str) -> list[dict]`
- `verify_rotation_integrity(rotation_id: str) -> bool`

**Implementation Notes:**
- JSON-based storage in `state/rotation_{project_name}.json`
- Atomic file operations for metadata persistence
- Merkle tree structure for hash verification chains

### **Template Integration**
**Purpose:** Generate context-rich new logs after rotation

**New Template Variables:**
```python
{
  "rotation_id": "uuid-v4",
  "rotation_timestamp_utc": "2025-10-24 11:00:00 UTC",
  "previous_log_path": "/path/to/archive.md",
  "previous_log_hash": "sha256:abc123...",
  "previous_log_entries": 127,
  "current_sequence": 2,
  "total_rotations": 1,
  "is_rotation": True,
  # Hash chaining variables (NEW):
  "hash_chain_previous": "sha256:previous_log_hash",
  "hash_chain_sequence": 2,
  "hash_chain_root": "sha256:initial_log_hash"
}
```

### **Cryptographic Hash Chaining (NEW)**
**Purpose:** Establish perfect cryptographic continuity between log rotations

**Implementation:**
- **Root Hash:** Initial log gets a unique root hash when first created
- **Chain Link:** Each rotation includes previous log's hash in first entry
- **Chain Verification:** Ability to verify entire chain from root to current
- **Tamper Evidence:** Any modification breaks the cryptographic chain

**Chain Entry Format:**
```markdown
[🔐] [2025-10-24 11:00:00 UTC] [Agent: Scribe] [Project: My Project] LOG ROTATION - Chain established | rotation_id=uuid; previous_log_hash=sha256:abc123; hash_chain_sequence=2; hash_chain_previous=sha256:def456
```

**Verification API:**
- `verify_hash_chain(project_name)` → Returns chain integrity status
- `get_hash_chain(project_name)` → Returns complete hash sequence
- `break_chain_analysis(project_name)` → Identifies where chain breaks

### **Advanced Metadata Tracking (FUTURE ENHANCEMENTS)**
**Purpose:** Add comprehensive provenance and evolution tracking

**Future Metadata Fields:**
```python
{
  # Git integration (when available)
  "commit_hash": "abc123def456",
  "scribe_rev": "v1.3.0",

  # Agent/Model tracking
  "scribe_version": "1.3.0",
  "claude_model": "sonnet-4.5-20250929",
  "agent_capabilities": "bulk_append, intelligent_recovery",

  # System metadata
  "session_id": "uuid-v4",
  "process_id": "12345",
  "hostname": "dev-server"
}
```

**Use Cases:**
- **Forensic Analysis:** Trace which model/agent created each entry
- **Debugging:** Correlate entries with specific code commits
- **Compliance:** Provide complete audit trail of AI model usage
- **Performance:** Track which agents/models are most productive

---

## 5. Directory Structure (Keep Updated)
```
/home/austin/projects/MCP_SPINE/scribe_mcp/
├── scribe_mcp/
│   ├── tools/
│   │   ├── rotate_log.py (MODIFIED)
│   │   ├── generate_doc_templates.py (INTEGRATED)
│   │   └── set_project.py (REFERENCED)
│   ├── utils/
│   │   ├── files.py (ENHANCED)
│   │   ├── audit.py (NEW)
│   │   ├── integrity.py (NEW)
│   │   ├── hash_chain.py (NEW)
│   │   └── time.py (UTILIZED)
│   ├── templates/
│   │   ├── __init__.py (ENHANCED)
│   │   └── PROGRESS_LOG_TEMPLATE.md (ENHANCED)
│   └── state/
│       ├── rotation_{project_name}.json (NEW)
│       └── state.json (INTEGRATED)
└── docs/dev_plans/
    ├── 1_templates/
    │   └── PROGRESS_LOG_TEMPLATE.md (UPDATED)
    └── enhanced_log_rotation_with_auditability/
        ├── ARCHITECTURE_GUIDE.md (THIS FILE)
        ├── PHASE_PLAN.md
        ├── CHECKLIST.md
        └── PROGRESS_LOG.md
```

> Agents rely on this tree for orientation. Update whenever files are added, removed, or reorganised.

---

## 6. Data & Storage
- **Datastores:** Tables/collections involved, with schema snapshots.
- **Indexes & Performance:** Indexing strategy, retention, archival plans.
- **Migrations:** Steps, ordering, rollback plan.

---

## 7. Testing & Validation Strategy
- **Unit Tests:** Scope and coverage targets.
- **Integration Tests:** Required environments, fixtures, and data sets.
- **Manual QA:** Exploratory plans or acceptance walkthroughs.
- **Observability:** Logging, metrics, tracing, alerting expectations.

---

## 8. Deployment & Operations
- **Environments:** Dev/staging/prod differences.
- **Release Process:** Automation, approvals, rollback.
- **Configuration Management:** Secrets, feature flags, runtime toggles.
- **Maintenance & Ownership:** On-call, SLOs, future work.

---

## 9. Project Naming Guidelines

### **Reserved Project Names and Patterns**

**⚠️ Important:** The Scribe MCP system includes automatic temp project detection that prevents auto-switching to test projects. Avoid these patterns when naming real projects.

#### **Reserved Keywords (DO NOT USE in real project names):**
```
test, temp, tmp, demo, sample, example
mock, fake, dummy, trial, experiment
```

#### **Reserved Patterns (DO NOT USE for real projects):**
- **UUID Suffixes:** `project-xxxxxxxx` (8+ character suffixes)
- **Numeric Suffixes:** `project-123`, `test_001`
- **Any project name containing reserved keywords**

#### **Examples of Names That WILL Be Skipped:**
✅ **TEST/TEMP PROJECTS (these will be ignored):**
- `test-project.json`
- `temp-project.json`
- `demo-project.json`
- `history-test-711f48a0.json` (UUID pattern)
- `project-123.json` (numeric suffix)

#### **Examples of Names That WILL Be Recognized:**
✅ **REAL PROJECTS (these will work correctly):**
- `my-project.json`
- `production-app.json`
- `real-work.json`
- `enhanced-log-rotation.json`
- `client-work-2024.json`

#### **Implementation Details:**
The `_is_temp_project()` function in `scribe_mcp/tools/project_utils.py` implements this logic using simple NLP pattern matching:
- **Keyword Detection:** Scans for reserved keywords in project names
- **UUID Detection:** Identifies long hexadecimal suffixes common in test isolation
- **Numeric Suffix Detection:** Catches common test numbering patterns

#### **Rationale:**
This prevents the MCP system from automatically switching to test projects during development, ensuring that real work stays focused on production projects while test isolation remains robust.

---

## 10. Open Questions & Follow-Ups
| Item | Owner | Status | Notes |
| ---- | ----- | ------ | ----- |
| TBD | TBD | TBD | Capture decisions, blockers, or research tasks. |

Close each question once answered and reference the relevant section above.

---

## 10. References & Appendix
- Link to diagrams, ADRs, research notes, or external specs.
- Include raw data, calculations, or supporting materials.

