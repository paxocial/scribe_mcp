
# 🏗️ Architecture Guide — MCP Tools Infrastructure Enhancement
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2025-10-27 13:14:09 UTC

> Architecture guide for MCP Tools Infrastructure Enhancement.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
## Problem Statement

### Core Issues Identified

1. **Parameter Serialization Inconsistency**: MCP framework serializes dict parameters as JSON strings, but our tools handle this inconsistently
2. **Tool Infrastructure Gaps**: No unified base class, parameter validation, or error handling patterns
3. **Plugin Compatibility**: External plugins (like vector indexer) can't leverage core tool infrastructure
4. **Permission Management**: No centralized access control or capability system for tools
5. **Error Handling**: Inconsistent error responses and recovery mechanisms across tools
6. **Logger Normalization**: Tools handle logging and state management differently

### Current State

- **Working**: Basic CRUD operations, simple parameter types
- **Broken**: Dict parameter handling in `set_project`, `query_entries`
- **Missing**: Unified tool framework, plugin support, permissions
- **Risks**: Inconsistent user experience, plugin compatibility issues

### Impact

- **User Experience**: "string indices must be integers, not 'str'" errors
- **Development**: Each tool must re-implement parameter parsing logic
- **Extensibility**: Plugins can't use core tool infrastructure
- **Maintainability**: Scattered parameter handling across codebase
<!-- ID: requirements_constraints -->
**Key Tasks:**
- Design BaseTool abstract class with standardized parameter handling
- Implement ParameterNormalizer utility for consistent JSON parsing
- Create ToolRegistry for tool discovery and permissions
- Update existing tools (append_entry, query_entries, set_project) to use BaseTool
- Add comprehensive test coverage for parameter handling
- **CRITICAL**: Implement context window safety mechanisms to prevent token blowup

**Deliverables:**
- Unified tool framework with consistent parameter normalization
- Updated core tools with proper dict/list parameter handling
- Plugin integration framework for external tools
- Comprehensive test suite validating all scenarios
- **Context safety layer with intelligent filtering and pagination**

**Acceptance Criteria:**
- [ ] All dict parameters handled consistently across tools
- [ ] Plugin tools can leverage core infrastructure  
- [ ] No "string indices must be integers" errors
- [ ] Backwards compatibility maintained
- [ ] Test coverage > 90% for parameter scenarios
- [ ] list_projects defaults to 5 most recent active projects
- [ ] All tools respect context window limits with warnings
- [ ] Pagination and filtering available for large datasets

## 2. Requirements & Constraints
<!-- ID: architecture_overview -->
## Proposed Solution

### Architecture Overview

Implement a **Unified Tool Framework** that provides consistent parameter handling, error management, and plugin support across all Scribe MCP tools.

### Core Components

#### 1. Base Tool Infrastructure (`tools/base/`)
- **`BaseTool`** abstract class with standardized parameter normalization
- **`ToolRegistry`** for tool discovery, permissions, and lifecycle management
- **`ParameterNormalizer`** utility for consistent dict/list parsing
- **`ToolResult`** standardized response format with error handling

#### 2. Context Safety Layer (`utils/context_safety.py`)
- **`ContextManager`** - Enforces token limits and provides warnings
- **`ResponsePaginator`** - Intelligent pagination for large datasets
- **`SmartFilter`** - Prioritizes active/recent projects over test projects
- **`TokenGuard`** - Prevents context window overflow with automatic truncation

#### 3. Parameter Normalization Layer (`utils/parameter_normalizer.py`)
- **`normalize_dict_param()`** - Handle JSON serialization consistently
- **`normalize_list_param()`** - Handle list parameter serialization
- **`validate_param_types()`** - Type validation with helpful errors
- **`safe_get_nested()`** - Safe nested dictionary access

#### 4. Enhanced Tool Interface (`tools/interfaces/`)
- **`ITool`** interface defining contract for all tools
- **`IPluginTool`** interface for plugin-provided tools
- **`ToolContext`** unified context management for all tools

#### 5. Plugin Integration Framework (`plugins/tool_framework.py`)
- Plugin tool registration and discovery
- Permission and capability management
- Shared infrastructure access for plugins
- Consistent parameter handling for plugin tools

### Implementation Phases

**Phase 1: Foundation** - Create base infrastructure + Context Safety
**Phase 2: Migration** - Update existing tools to use BaseTool
**Phase 3: Plugin Integration** - Enable plugins to use framework
**Phase 4: Advanced Features** - Permissions, capabilities, validation

### Context Safety Strategy

- **Default Limits**: `list_projects` defaults to 5 most recent active projects
- **Intelligent Filtering**: Auto-hide test/temp projects (regex: `test-.*-[a-f0-9]{8,}`)
- **Smart Pagination**: Automatic pagination for datasets > 5 items
- **Token Warnings**: Clear warnings when approaching context limits
- **Graceful Degradation**: Fallback to compact mode when needed

### Benefits

- **Consistency**: All tools handle parameters identically
- **Scalability**: Handles thousands of projects without token blowup
- **User Experience**: Predictable responses with smart defaults
- **Maintainability**: Single source of truth for tool patterns
- **Extensibility**: Plugins can leverage core infrastructure
<!-- ID: detailed_design -->
For each subsystem:
1. **Doc Change Pipeline**
   - **Purpose:** Coordinate apply/verify steps.
   - **Interfaces:** Atomic writer, storage backend
   - **Implementation Notes:** Async aware
   - **Error Handling:** Rollback on verification failure


---
## 5. Directory Structure (Keep Updated)
<!-- ID: directory_structure -->
```
/home/austin/projects/MCP_SPINE/scribe_mcp/docs/dev_plans/mcp_tools_infrastructure_enhancement
```
> Agents rely on this tree for orientation. Update whenever files are added, removed, or reorganised.


---
## 6. Data & Storage
<!-- ID: data_storage -->
- **Datastores:** ['Filesystem markdown', 'SQLite mirror']
- **Indexes & Performance:** FTS for sections
- **Migrations:** Sequential migrations tracked in storage layer


---
## 7. Testing & Validation Strategy
<!-- ID: testing_strategy -->
- **Unit Tests:** Template rendering + doc ops
- **Integration Tests:** manage_docs tool exercises real files
- **Manual QA:** Project review after each release
- **Observability:** Structured logging via doc_updates log


---
## 8. Deployment & Operations
<!-- ID: deployment_operations -->
- **Environments:** Local development
- **Release Process:** Git commits drive deployment
- **Configuration Management:** Project-specific .scribe settings
- **Maintenance & Ownership:** Doc management team


---
## 9. Open Questions & Follow-Ups
<!-- ID: open_questions -->
| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| Should templates support conditionals per phase? | Docs Lead | TODO | Evaluate after initial rollout. |
Close each question once answered and reference the relevant section above.


---
## 10. References & Appendix
<!-- ID: references_appendix -->
- PROGRESS_LOG.md- ARCHITECTURE_GUIDE.md
Generated via generate_doc_templates.


---