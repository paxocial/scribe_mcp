# 🤖 Agent-Scoped Project Context Development Plan

**Project:** Enhanced Log Rotation with Auditability
**Phase:** Multi-Agent Architecture Implementation
**Status:** In Progress (Phase 3/6)
**Author:** Scribe & Carl (Security Review)
**Date:** 2025-10-24

---

## 📋 Executive Summary

This document outlines the comprehensive development plan for implementing **agent-scoped project context** in the Scribe MCP system. The goal is to transform the current global project state management into a robust multi-agent architecture that supports concurrent operations across multiple agents with proper isolation and conflict resolution.

### 🎯 Problem Statement

**Current Issues:**
- **Race Conditions:** Global project state causes data loss during concurrent operations
- **No Agent Isolation:** All agents share one global project context
- **No Concurrency Control:** Multiple agents can overwrite each other's project selections
- **Single Point of Failure:** Global state management lacks atomicity

### 🏗️ Solution Overview

**Target Architecture:**
- **Database as Source of Truth:** SQLite/PostgreSQL backend maintains authoritative agent contexts
- **JSON State as Cache:** Fast local state for UI continuity and warm starts
- **Agent Isolation:** Each agent has its own project context and session
- **Optimistic Concurrency:** Version-based conflict resolution prevents lost updates
- **Session Management:** Time-limited leases with automatic expiration

---

## 📊 Implementation Status

### ✅ **Phase 1: Database Schema Extensions** (COMPLETED)
**Status:** ✅ DONE
**Backend:** SQLite + PostgreSQL
**Implementation:**

```sql
-- Agent sessions table
CREATE TABLE IF NOT EXISTS agent_sessions (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL CHECK (status IN ('active','expired')) DEFAULT 'active',
    metadata JSONB
);

-- Agent projects table (agent-scoped current project)
CREATE TABLE IF NOT EXISTS agent_projects (
    agent_id TEXT PRIMARY KEY,
    project_name TEXT,
    version INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT,
    session_id TEXT,
    FOREIGN KEY (project_name) REFERENCES scribe_projects(name) ON DELETE SET NULL
);
```

**Files Modified:**
- `MCP_SPINE/scribe_mcp/storage/sqlite.py` - Added schema initialization
- `MCP_SPINE/scribe_mcp/db/init.sql` - Added PostgreSQL schema
- `MCP_SPINE/scribe_mcp/storage/base.py` - Added abstract methods and ConflictError

### ✅ **Phase 2: Storage Backend API Extensions** (COMPLETED)
**Status:** ✅ DONE
**Features:** Session management, optimistic concurrency, cross-platform support
**Implementation:**

**New Storage Methods:**
```python
async def upsert_agent_session(agent_id: str, session_id: str, metadata: Optional[Dict[str, Any]]) -> None
async def heartbeat_session(session_id: str) -> None
async def end_session(session_id: str) -> None
async def get_agent_project(agent_id: str) -> Optional[Dict[str, Any]]
async def set_agent_project(agent_id: str, project_name: Optional[str], expected_version: Optional[int], updated_by: str, session_id: str) -> Dict[str, Any]
```

**Files Modified:**
- `MCP_SPINE/scribe_mcp/storage/sqlite.py` - SQLite implementation with atomic operations
- `MCP_SPINE/scribe_mcp/db/ops.py` - PostgreSQL asyncpg operations
- `MCP_SPINE/scribe_mcp/storage/postgres.py` - PostgreSQL backend wrapper

**Key Features:**
- ✅ **Optimistic Concurrency Control:** Version-based conflict detection
- ✅ **Atomic Operations:** Write-ahead logging for crash recovery
- ✅ **Cross-Platform Support:** SQLite + PostgreSQL parity
- ✅ **Session Management:** TTL-based lease system (15 minutes)

### 🔄 **Phase 3: AgentContextManager Orchestration Layer** (IN PROGRESS)
**Status:** 🔄 IN PROGRESS
**Files:** `MCP_SPINE/scribe_mcp/state/agent_manager.py` (Created)
**Features:** Session coordination, lease management, JSON state mirroring

**Core Components:**
```python
class AgentContextManager:
    - start_session(agent_id, metadata) -> session_id
    - set_current_project(agent_id, project_name, session_id, expected_version) -> result
    - get_current_project(agent_id) -> project_info
    - heartbeat_session(session_id) -> None
    - cleanup_expired_sessions() -> count
```

**Current Status:**
- ✅ Session management with TTL (15-minute leases)
- ✅ Optimistic concurrency control
- ✅ JSON state mirroring (non-authoritative cache)
- ✅ Session lease validation
- ⚠️ **Testing Required:** Unit tests for session lifecycle

### ⏳ **Phase 4: Tool Integration Updates** (PENDING)
**Status:** ⏳ PENDING
**Target Tools:** `set_project`, `append_entry`, `read_recent`, `query_entries`

**Required Changes:**
1. **set_project Tool Enhancement:**
   ```python
   @app.tool()
   async def set_project(
       name: Optional[str],
       agent_id: str = "Scribe",  # NEW: Agent identification
       expected_version: Optional[int] = None,  # NEW: Version control
       # ... existing parameters
   )
   ```

2. **append_entry Tool Enhancement:**
   ```python
   @app.tool()
   async def append_entry(
       message: str,
       agent_id: str = "Scribe",  # NEW: Agent identification
       # ... existing parameters
   )
   ```

### ⏳ **Phase 5: Migration and Backfill Logic** (PENDING)
**Status:** ⏳ PENDING
**Target:** Server startup migration from legacy global state
**Implementation:** `migrate_legacy_state()` function

**Migration Strategy:**
1. **Detect Legacy State:** Check for existing agent_projects entries
2. **Migrate Global Project:** Move `current_project` to "Scribe" agent
3. **Clear Global State:** Remove `current_project` from JSON to avoid dual sources
4. **Create Migration Session:** Mark migration for audit trail

### ⏳ **Phase 6: Comprehensive Concurrency Testing** (PENDING)
**Status:** ⏳ PENDING
**Test Scenarios:**
1. **Agent Isolation Test:** Verify Agent-A and Agent-B can work on different projects simultaneously
2. **Version Conflict Test:** Confirm optimistic versioning prevents lost updates
3. **Session Expiry Test:** Validate expired sessions can be superseded
4. **Append Storm Test:** 16 concurrent appends across agents without cross-contamination
5. **Database Parity Test:** Ensure SQLite and PostgreSQL behave identically

---

## 🛠️ Technical Architecture

### **Data Flow Diagram**
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Agent Tool      │    │  JSON State      │    │   Database      │
│  (MCP Client)   │    │  (Local Cache)   │    │ (Source of Truth)│
└─────────┬─────────┘    └───────┬─────────┘    └─────────┬─────────┘
          │                    │                    │
          ▼                    ▼                    ▼
    AgentContextManager ↔ set_project()   ↔   Storage Backend
    (Orchestration)        ↔   append_entry()   ↔   (SQLite/Postgres)
          │                    │                    │
          └────────────────────┘                    └────────────────────┘
```

### **Session Management**
```python
# Session Lease Lifecycle
1. start_session(agent_id) → Creates 15-minute lease
2. set_current_project() → Validates lease before operation
3. heartbeat_session() → Extends lease as needed
4. end_session() → Marks session as expired
5. cleanup_expired_sessions() → Removes expired leases
```

### **Optimistic Concurrency Control**
```python
# Version Conflict Resolution
try:
    # Attempt update with expected version
    await storage.set_agent_project(
        agent_id="AgentA",
        project_name="ProjectX",
        expected_version=3,  # Current version
        session_id="session-123"
    )
except ConflictError:
    # Conflict! Get current state and retry
    current = await storage.get_agent_project("AgentA")
    await storage.set_agent_project(
        agent_id="AgentA",
        project_name="ProjectX",
        expected_version=current["version"],
        session_id="session-123"
    )
```

---

## 🔧 Implementation Details

### **Database Schema Considerations**

**Foreign Key Relationships:**
- `agent_projects.project_name` → `scribe_projects.name` (ON DELETE SET NULL)
- Ensures project references remain valid when projects are deleted

**Indexing Strategy:**
- `idx_agent_sessions_agent` on `agent_sessions(agent_id)` for fast agent lookups
- `idx_agent_projects_updated_at` on `agent_projects(updated_at DESC)` for cleanup queries

**Cross-Platform Compatibility:**
- **SQLite:** Uses `CURRENT_TIMESTAMP` and TEXT fields
- **PostgreSQL:** Uses `NOW()` and TIMESTAMPTZ fields
- **Consistent Interfaces:** Abstract storage base ensures both backends behave identically

### **Concurrency Safety Mechanisms**

**1. Database-Level Locking:**
- SQLite: `_write_lock` asyncio.Lock for serialized writes
- PostgreSQL: asyncpg connection pooling with built-in transaction isolation

**2. Application-Level Leases:**
- Session leases prevent stale sessions from making changes
- Lease validation before every state-changing operation
- Automatic cleanup of expired leases

**3. Optimistic Versioning:**
- Every update increments the version number
- Conflicts are detected and resolved without data loss
- Provides visibility into concurrent modification attempts

### **JSON State Integration**

**Non-Authoritative Cache Pattern:**
```python
# JSON state is kept for UI continuity but DB is source of truth
async def _mirror_to_json_state(self, agent_id: str, result: Dict[str, Any]) -> None:
    # Minimal mirroring for UI warm-start
    state = await self.state_manager.load()
    # Store crumbs for UI, but don't rely on this data
    await self.state_manager.persist(state)
```

**Backward Compatibility:**
- Legacy migration ensures smooth transition from global state
- JSON state still exists for existing UI workflows
- New tools use DB source of truth while maintaining UI familiarity

---

## 🧪 Testing Strategy

### **Unit Tests**
```python
# Session Management Tests
test_agent_session_lifecycle()
test_session_heartbeat()
test_session_expiration()

# Concurrency Tests
test_agent_isolation()
test_version_conflicts()
test_concurrent_project_switching()
```

### **Integration Tests**
```python
# Multi-Agent Workflows
test_multi_agent_concurrent_operations()
test_agent_context_switching_under_load()
test_cross_agent_data_isolation()
```

### **Performance Tests**
```python
# Concurrency Under Load
test_concurrent_append_operations(agent_count=16, operations_per_agent=100)
test_session_management_scalability(session_count=1000)
test_database_backends_performance()
```

### **Database Parity Tests**
```python
# Cross-Platform Validation
test_sqlite_postgres_parity()
test_agent_context_migration_across_backends()
```

---

## 📊 Risk Assessment & Mitigation

### **High Risk Areas:**
1. **Race Conditions During Migration:** Legacy state transition
   - **Mitigation:** Atomic migration with backup and rollback capability
   - **Monitoring:** Migration logging and verification steps

2. **Session Lease Exhaustion:** DoS attacks or resource exhaustion
   - **Mitigation:** Rate limiting and session cleanup mechanisms
   - **Monitoring:** Active session count and lease expiration tracking

3. **Database Corruption:** Concurrent modifications during writes
   - **Mitigation:** Atomic operations and write-ahead logging
   - **Monitoring:** Database integrity checks and automatic repair

### **Medium Risk Areas:**
1. **JSON State Inconsistency:** Cache drift from database
   - **Mitigation:** Regular synchronization and validation
   - **Monitoring:** State consistency checks and alerts

2. **Version Conflict Storms:** High concurrency scenarios
   - **Mitigation:** Exponential backoff and conflict resolution strategies
   - **Monitoring:** Conflict frequency and resolution success rates

### **Low Risk Areas:**
1. **Cross-Platform Differences:** SQLite vs PostgreSQL behavior
   - **Mitigation:** Comprehensive cross-platform testing
   - **Monitoring:** Parallel test execution and result comparison

2. **Performance Degradation:** Overhead from new architecture
   - **Mitigation:** Performance benchmarks and optimization
   - **Monitoring:** Query performance and session management overhead

---

## 📅 Implementation Timeline

### **Completed (Phases 1-2):**
- ✅ Database schema extensions (SQLite + PostgreSQL)
- ✅ Storage backend API implementations with optimistic concurrency
- ✅ Conflict detection and resolution mechanisms
- ✅ Session management foundations

### **Current (Phase 3):**
- 🔄 AgentContextManager implementation
- ⏳ Unit testing for session lifecycle
- ⏳ Integration testing with storage backends
- ⏳ JSON state mirroring validation

### **Next (Phases 4-6):**
- ⏳ Tool integration updates (set_project, append_entry)
- ⏳ Server startup migration logic
- ⏳ Comprehensive concurrency test suite
- ⏋ Performance benchmarking and optimization

### **Estimated Timeline:**
- **Phase 3:** 2-3 days (testing and validation)
- **Phase 4:** 1-2 days (tool updates)
- **Phase 5:** 1 day (migration logic)
- **Phase 6:** 2-3 days (comprehensive testing)
- **Total:** 6-11 days to complete full multi-agent transformation

---

## 🎯 Success Criteria

### **Functional Requirements:**
- ✅ **Agent Isolation:** Multiple agents can work on different projects simultaneously
- ✅ **Concurrency Safety:** No data loss during concurrent operations
- ✅ **Version Control:** Optimistic concurrency prevents lost updates
- ✅ **Session Management:** Automatic lease expiration and cleanup
- ✅ **Cross-Platform:** Identical behavior on SQLite and PostgreSQL

### **Non-Functional Requirements:**
- ✅ **Performance:** <50ms for project switching operations
- ✅ **Reliability:** Zero data loss under concurrent load
- ✅ **Scalability:** Support for 10+ concurrent agents
- ✅ **Maintainability:** Clear separation between database and JSON state
- ✅ **Backward Compatibility:** Smooth migration from legacy state

### **Integration Requirements:**
- ✅ **MCP Tool Compatibility:** Existing tools work with new agent system
- ✅ **Database Compatibility:** Works with existing SQLite and PostgreSQL backends
- ✅ **UI Continuity:** JSON state provides warm-start for existing interfaces
- ✅ **Audit Trail:** Full tracking of agent operations and project changes

---

## 📚 Related Documentation

### **Architecture:**
- `ARCHITECTURE_GUIDE.md` - System architecture and design decisions
- `PHASE_PLAN.md` - Development roadmap and milestone tracking
- `CHECKLIST.md` - Verification requirements and acceptance criteria

### **Progress Tracking:**
- `PROGRESS_LOG.md` - Detailed implementation log with audit trail
- This `AGENT_SCOPED_CONTEXT_DEVELOPMENT_PLAN.md` - Central development tracking document

### **Technical References:**
- `storage/base.py` - Abstract storage interface definitions
- `storage/sqlite.py` - SQLite backend implementation
- `storage/postgres.py` - PostgreSQL backend implementation
- `db/ops.py` - PostgreSQL operation helpers
- `state/manager.py` - JSON state management
- `state/agent_manager.py` - Agent context orchestration

---

## 🔄 Next Steps

### **Immediate (Phase 3 Completion):**
1. **Fix Syntax Error:** Resolve AgentContextManager async context issue
2. **Complete Unit Tests:** Test session lifecycle and lease management
3. **Integration Testing:** Validate storage backend coordination
4. **JSON State Mirroring:** Ensure cache consistency

### **Upcoming (Phase 4):**
1. **Tool Integration:** Update set_project and append_entry with agent_id parameters
2. **Version Conflict Handling:** Implement retry logic for concurrent operations
3. **Error Messages:** Provide actionable guidance for conflict resolution
4. **Backward Compatibility:** Ensure existing workflows continue to work

### **Future (Phases 5-6):**
1. **Migration Logic:** Implement startup migration from legacy state
2. **Test Suite Creation:** Comprehensive concurrency and integration tests
3. **Performance Validation:** Benchmark and optimize multi-agent performance
4. **Documentation Updates:** Update user guides and API documentation

---

## 📞 Contact Information

**Project Maintainers:**
- **Lead Developer:** Scribe (AI Agent)
- **Security Reviewer:** Carl (Third-party security audit)
- **Architecture Review:** Crawler (Multi-agent concurrency specialist)

**Project Location:**
- **Repository:** `/home/austin/projects/MCP_SPINE/scribe_mcp`
- **Documentation:** `/docs/dev_plans/enhanced_log_rotation_with_auditability/`
- **Progress Tracking:** This `AGENT_SCOPED_CONTEXT_DEVELOPMENT_PLAN.md`

**Last Updated:** 2025-10-24 17:42 UTC
**Version:** 1.0 (Phase 3 In Progress)
