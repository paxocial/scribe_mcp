# Scribe MCP Tool Usage Guide

This document provides comprehensive usage instructions for all available Scribe MCP tools, including required parameters, optional parameters, and practical examples.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Core Project Management](#core-project-management)
3. [Logging Operations](#logging-operations)
4. [Query and Analysis](#query-and-analysis)
5. [Documentation Management](#documentation-management)
6. [Log Maintenance](#log-maintenance)
7. [Project Cleanup](#project-cleanup)

---

## Prerequisites

### **IMPORTANT: Project Context Required**

Most Scribe tools require an active project context. Before using any tool, you MUST set a project:

```python
await set_project(name="your-project-name")
```

**Failure to set a project first will result in errors like:**
- `"No project configured. Invoke set_project before using this tool."`
- `"No project configured. Invoke set_project before reading logs"`

---

## Core Project Management

### `set_project`
**Purpose**: Create/select a project and bootstrap documentation structure.

**Required Parameters:**
- `name` (string): Project name

**Optional Parameters:**
- `root` (string): Project root directory (defaults to current directory)
- `progress_log` (string): Path to progress log file
- `defaults` (dict): Default settings for the project

**Example Usage:**
```python
# Basic usage
await set_project(name="my-project")

# With custom defaults
await set_project(
    name="my-project",
    defaults={"emoji": "🧪", "agent": "MyAgent"}
)
```

**Returns:**
```json
{
  "ok": true,
  "project": {
    "name": "my-project",
    "root": "/path/to/project",
    "progress_log": "/path/to/progress/log.md",
    "docs_dir": "/path/to/docs",
    "docs": {
      "architecture": "/path/to/ARCHITECTURE_GUIDE.md",
      "phase_plan": "/path/to/PHASE_PLAN.md",
      "checklist": "/path/to/CHECKLIST.md",
      "progress_log": "/path/to/PROGRESS_LOG.md"
    },
    "defaults": {"agent": "Scribe"},
    "author": "Scribe"
  }
}
```

### `get_project`
**Purpose**: Retrieve current active project context and configuration.

**Parameters:** None

**Example Usage:**
```python
await get_project()
```

**Returns:**
```json
{
  "ok": true,
  "project": {
    "name": "current-project",
    "root": "/path/to/project",
    "progress_log": "/path/to/log.md",
    "docs_dir": "/path/to/docs",
    "defaults": {"agent": "Scribe"},
    "author": "Scribe"
  }
}
```

### `list_projects`
**Purpose**: Discover available projects and their configurations.

**Optional Parameters:**
- `limit` (int, default: 5): Maximum number of projects to return
- `filter` (string): Filter projects by name (case-insensitive)
- `compact` (bool): Use compact response format
- `fields` (list): Specific fields to include in response
- `include_test` (bool, default: false): Include test/temp projects
- `page` (int, default: 1): Page number for pagination
- `page_size` (int): Number of items per page

**Example Usage:**
```python
# Basic usage
await list_projects()

# With pagination
await list_projects(limit=10, page=1)

# Filtered search
await list_projects(filter="my-project", limit=3)
```

**Returns:**
```json
{
  "ok": true,
  "projects": [
    {
      "name": "project-name",
      "root": "/path/to/project",
      "progress_log": "/path/to/log.md"
    }
  ],
  "count": 1,
  "pagination": {
    "page": 1,
    "page_size": 5,
    "total_count": 10,
    "has_next": true,
    "has_prev": false
  }
}
```

---

## Logging Operations

### `append_entry`
**Purpose**: **PRIMARY TOOL** - Add structured log entries with metadata.

#### Single Entry Mode

**Required Parameters:**
- `message` (string): Log message content

**Optional Parameters:**
- `status` (string): Status type - "info", "success", "warn", "error", "bug", "plan"
- `emoji` (string): Custom emoji override
- `agent` (string): Agent identifier
- `meta` (dict): Metadata dictionary for context
- `timestamp_utc` (string): Custom UTC timestamp
- `log_type` (string): Target log identifier (defaults to "progress")

**Example Usage:**
```python
# Basic entry
await append_entry(message="Fixed authentication bug")

# With full context
await append_entry(
    message="Fixed authentication bug",
    status="success",
    agent="DebugBot",
    meta={"component": "auth", "tests_fixed": 5}
)

# Planning entry
await append_entry(
    message="Beginning database migration phase",
    status="plan",
    emoji="🗄️",
    meta={"phase": "migration", "priority": "high"}
)
```

#### Bulk Entry Mode

**Required Parameters:**
- `items` (string or list): JSON string array or direct list of entry dictionaries

**Each Entry Requires:**
- `message` (string): Log message content

**Each Entry Optional:**
- `status`, `emoji`, `agent`, `meta`, `timestamp_utc`, `log_type`

**Example Usage:**
```python
# As JSON string
await append_entry(items=json.dumps([
  {"message": "First task completed", "status": "success"},
  {"message": "Bug found in auth module", "status": "bug", "agent": "DebugBot"},
  {"message": "Database migration finished", "status": "info",
   "meta": {"component": "database", "phase": "deployment"}}
]))

# As direct list
await append_entry(items=[
  {"message": "Code review completed", "status": "success"},
  {"message": "Tests passing", "status": "success", "meta": {"tests_run": 25}}
])
```

**Returns:**
```json
{
  "ok": true,
  "written_line": "[ℹ️] [2025-11-02 07:39:07 UTC] [Agent: AgentName] [Project: project] [ID: hash] Your message",
  "path": "/path/to/progress/log.md",
  "meta": {"log_type": "progress"}
}
```

---

## Query and Analysis

### `read_recent`
**Purpose**: Retrieve recent log entries with pagination.

**Optional Parameters:**
- `n` (int, default: 50): Number of recent entries to return
- `filter` (dict): Optional filters for agent, status, emoji
- `page` (int, default: 1): Page number for pagination
- `page_size` (int): Number of entries per page
- `compact` (bool): Use compact response format
- `fields` (list): Specific fields to include
- `include_metadata` (bool): Include metadata field in entries

**Example Usage:**
```python
# Basic usage
await read_recent()

# Limited entries
await read_recent(n=10)

# With filters
await read_recent(n=5, filter={"agent": "DebugBot", "status": "success"})
```

**Returns:**
```json
{
  "ok": true,
  "entries": [
    {
      "id": "entry_id",
      "ts": "2025-11-02 07:39:07 UTC",
      "emoji": "ℹ️",
      "agent": "AgentName",
      "message": "Log message",
      "meta": {"log_type": "progress"},
      "raw_line": "Full log line"
    }
  ],
  "count": 1,
  "pagination": {
    "page": 1,
    "page_size": 50,
    "total_count": 1,
    "has_next": false,
    "has_prev": false
  }
}
```

### `query_entries`
**Purpose**: Advanced log searching and filtering.

**Optional Parameters:**
- `project` (string): Project name (uses active project if None)
- `start` (string): Start timestamp filter
- `end` (string): End timestamp filter
- `message` (string): Message text filter
- `message_mode` (string): How to match message - "substring", "regex", "exact"
- `case_sensitive` (bool): Case sensitive message matching
- `emoji` (string or list): Filter by emoji(s)
- `status` (string or list): Filter by status(es)
- `agents` (string or list): Filter by agent name(s)
- `meta_filters` (dict): Filter by metadata key/value pairs
- `limit` (int): Maximum results to return
- `page` (int): Page number for pagination
- `page_size` (int): Number of results per page

**Enhanced Search Parameters:**
- `search_scope`: "project", "global", "all_projects", "research", "bugs", "all"
- `document_types`: ["progress", "research", "architecture", "bugs", "global"]
- `relevance_threshold`: Minimum relevance score (0.0-1.0)
- `verify_code_references`: Check if mentioned code exists
- `time_range`: Temporal filtering ("last_30d", "last_7d", "today")

**Example Usage:**
```python
# Basic message search
await query_entries(message="bug", message_mode="substring")

# Date range search
await query_entries(start="2025-10-23", end="2025-10-24")

# Enhanced cross-project search
await query_entries(
    message="authentication",
    search_scope="all_projects",
    document_types=["progress", "bugs"],
    relevance_threshold=0.8
)

# Metadata filtering
await query_entries(
    meta_filters={"component": "auth", "severity": "high"}
)
```

**Returns:**
```json
{
  "ok": true,
  "entries": [/* matching entries */],
  "count": 5,
  "pagination": {/* pagination info */}
}
```

---

## Documentation Management

### `manage_docs`
**Purpose**: Structured documentation system for projects.

**Required Parameters:**
- `action` (string): Action type - `replace_section`, `append`, `status_update`, `list_sections`, `batch`, `create_research_doc`, `create_bug_report`, `create_review_report`, `create_agent_report_card`
- `doc` (string): Document key (e.g., `architecture`, `phase_plan`, `checklist`, `implementation`)

**Action-Specific Parameters:**

#### `replace_section`
- `section` (string, required): Section anchor ID (e.g., "problem_statement")
- `content` (string, required): New section content

#### `append`
- `content` (string, required): Content to append
- `section` (string, optional): Section anchor to append near. When omitted the content is appended to the end of the file.
- `metadata.position` (string, optional): Insert placement relative to the section. Supported values: `before`, `inside` (immediately after the anchor), and `after` (default).

#### `status_update`
- `section` (string, required): Checklist item ID
- `metadata` (dict, optional): Status info such as `{"status": "done", "proof": "evidence"}`. When omitted the existing status is preserved and proofs can still be updated.

#### `list_sections`
- Returns the discovered section anchors for the requested document, including line numbers.

#### `batch`
- `metadata.operations` (list, required): Sequence of manage_docs payloads executed in order. Nested batches are rejected for safety.

#### `create_research_doc`
- `doc_name` (string, required): Document name
- `metadata` (dict, optional): Research metadata

#### `create_bug_report`
- `metadata` (dict, required): Bug report metadata

**Optional Parameters:**
- `metadata` (dict): Additional metadata for the operation
- `dry_run` (bool): Preview changes without applying
- Metadata payloads are auto-normalized; dicts, JSON strings, and legacy key/value sequences are all accepted.

**Example Usage:**
```python
# Replace architecture section
await manage_docs(
    action="replace_section",
    doc="architecture",
    section="problem_statement",
    content="## Problem Statement\n**Context:** ..."
)

# Append within a section
await manage_docs(
    action="append",
    doc="architecture",
    section="problem_statement",
    content="Updated scope paragraph",
    metadata={"position": "inside"}
)

# Update checklist status
await manage_docs(
    action="status_update",
    doc="checklist",
    section="phase_1_task_1",
    metadata={"status": "done", "proof": "code_review_completed"}
)

# Create research document
await manage_docs(
    action="create_research_doc",
    doc_name="RESEARCH_AUTH_SYSTEM_20251102",
    metadata={"research_goal": "Analyze authentication flow"}
)

# Batch multiple updates (executed sequentially)
await manage_docs(
    action="batch",
    doc="architecture",
    metadata={
        "operations": [
            {
                "action": "append",
                "doc": "architecture",
                "section": "requirements_constraints",
                "content": "Documented latency targets",
                "metadata": {"position": "after"}
            },
            {
                "action": "status_update",
                "doc": "checklist",
                "section": "documentation_hygiene",
                "metadata": {"status": "done", "proof": "PROGRESS_LOG#2025-11-02"}
            }
        ]
    }
)
```

**Returns:**
```json
{
  "ok": true,
  "doc": "architecture",
  "action": "replace_section",
  "path": "/path/to/document.md",
  "verification_passed": true,
  "dry_run": false
}
```

### `generate_doc_templates`
**Purpose**: Create/update documentation templates for a project.

**Required Parameters:**
- `project_name` (string): Name of the project

**Optional Parameters:**
- `author` (string): Document author
- `overwrite` (bool, default: false): Overwrite existing templates
- `documents` (list): Specific documents to generate
- `base_dir` (string): Base directory for templates

**Example Usage:**
```python
# Basic usage
await generate_doc_templates(project_name="my-project")

# With author and specific documents
await generate_doc_templates(
    project_name="my-project",
    author="MyAgent",
    documents=["architecture", "phase_plan"]
)
```

**Returns:**
```json
{
  "ok": true,
  "files": ["/paths/to/generated/files.md"],
  "skipped": ["/paths/to/existing/files.md"],
  "directory": "/path/to/docs/dir",
  "validation": {/* template validation results */}
}
```

---

## Log Maintenance

### `rotate_log`
**Purpose**: Archive current progress log and start fresh file.

**Optional Parameters:**
- `confirm` (bool): When True, perform actual rotation
- `dry_run` (bool, default: true): Preview rotation without changes
- `log_type` (string): Specific log type to rotate
- `log_types` (list): Multiple log types to rotate
- `rotate_all` (bool): Rotate every configured log type
- `auto_threshold` (bool): Only rotate if entry count exceeds threshold
- `threshold_entries` (int): Override entry threshold
- `suffix` (string): Optional suffix for archive filenames
- `custom_metadata` (string): JSON metadata for rotation record

**Example Usage:**
```python
# Preview rotation
await rotate_log(dry_run=True)

# Actually rotate progress log
await rotate_log(confirm=True)

# Rotate multiple log types
await rotate_log(
    confirm=True,
    log_types=["progress", "doc_updates"]
)

# Auto-threshold rotation
await rotate_log(
    confirm=True,
    auto_threshold=True,
    threshold_entries=1000
)
```

**Returns:**
```json
{
  "ok": true,
  "rotations": [
    {
      "log_type": "progress",
      "dry_run": false,
      "rotation_id": "unique-id",
      "project": "project-name",
      "current_file_path": "/path/to/current.md",
      "archived_to": "/path/to/archive.md",
      "entry_count": 150,
      "requires_confirmation": false,
      "auto_threshold_triggered": false
    }
  ]
}
```

### `verify_rotation_integrity`
**Purpose**: Verify the integrity of a specific rotation archive.

**Required Parameters:**
- `archive_path` (string): Path to rotation archive to verify

**Example Usage:**
```python
await verify_rotation_integrity(
    archive_path="/path/to/archive.md"
)
```

### `get_rotation_history`
**Purpose**: Return recent rotation history entries for the active project.

**Parameters:** None (requires active project)

**Example Usage:**
```python
await get_rotation_history()
```

**Returns:**
```json
{
  "ok": true,
  "project": "project-name",
  "rotation_count": 3,
  "rotations": [
    {
      "rotation_id": "id",
      "timestamp": "2025-11-02 07:40:21 UTC",
      "log_type": "progress",
      "entry_count": 150
    }
  ]
}
```

---

## Project Cleanup

### `delete_project`
**Purpose**: Delete or archive a project and all associated data.

**Required Parameters:**
- `name` (string): Project name to delete
- `confirm` (bool): Must be True to proceed with deletion

**Optional Parameters:**
- `mode` (string, default: "archive"): "archive" or "permanent"
- `force` (bool): Override safety checks (not recommended)
- `archive_path` (string): Custom archive directory
- `agent_id` (string): Agent identification

**Example Usage:**
```python
# Archive project (safe default)
await delete_project(
    name="old-project",
    confirm=True
)

# Permanent deletion (dangerous)
await delete_project(
    name="temp-project",
    confirm=True,
    mode="permanent"
)
```

**Returns:**
```json
{
  "success": true,
  "project_name": "project-name",
  "mode": "archive",
  "message": "Project 'project-name' archived to path",
  "archive_location": "/path/to/archive",
  "database_cleanup": true
}
```

---

## Best Practices

### 1. **Always Set Project First**
```python
await set_project(name="your-project")
# Now use other tools
```

### 2. **Use Structured Metadata**
```python
await append_entry(
    message="Fixed critical bug",
    status="success",
    meta={
        "component": "auth",
        "bug_id": "BUG-123",
        "tests_fixed": 5,
        "phase": "bugfix"
    }
)
```

### 3. **Log Meaningful Events**
- Code changes and why they were made
- Test results and failures
- Decisions and reasoning
- Bug discoveries and fixes
- Milestone completions

### 4. **Use Bulk Mode for Backfilling**
```python
# If you forget to log, use bulk mode immediately
await append_entry(items=[
    {"message": "Step 1 completed", "status": "success"},
    {"message": "Step 2 completed", "status": "success"},
    {"message": "Bug discovered", "status": "bug", "agent": "DebugBot"}
])
```

### 5. **Leverage Enhanced Search**
```python
# Cross-project learning
await query_entries(
    message="authentication pattern",
    search_scope="all_projects",
    document_types=["architecture", "progress"],
    relevance_threshold=0.9
)
```

---

## Error Handling

Common errors and solutions:

1. **"No project configured"** → Call `set_project()` first
2. **"Invalid arguments for tool"** → Check parameter names and types
3. **"dictionary update sequence element #0 has length 1; 2 is required"** → `meta` parameter format issue

---

## Tool Summary Quick Reference

| Tool | Purpose | Required Params | Project Context |
|------|---------|----------------|-----------------|
| `set_project` | Initialize project | `name` | No |
| `get_project` | Get current context | None | Yes |
| `list_projects` | Browse projects | None | No |
| `append_entry` | **PRIMARY** logging | `message` or `items` | Yes |
| `read_recent` | Recent entries | None | Yes |
| `query_entries` | Search logs | None | Yes |
| `manage_docs` | Documentation | `action`, `doc` | Yes |
| `generate_doc_templates` | Create templates | `project_name` | No |
| `rotate_log` | Archive logs | None | Yes |
| `verify_rotation_integrity` | Verify archive | `archive_path` | No |
| `get_rotation_history` | Rotation history | None | Yes |
| `delete_project` | Remove project | `name`, `confirm` | No |
