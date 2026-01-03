# ⚙️ Phase Plan — scribe_tool_output_refinement
**Author:** ArchitectAgent
**Version:** v1.0
**Status:** ready_for_implementation
**Last Updated:** 2026-01-02 14:04:00 UTC

> Sequential execution roadmap for implementing readable output formats across all Scribe MCP tools.

---
## Phase Overview
<!-- ID: phase_overview -->

| Phase | Goal | Duration | Key Deliverables | Dependencies | Confidence |
|-------|------|----------|------------------|--------------|------------|
| Phase 0 - Foundation | Extend ResponseFormatter with readable format core | 3 days | ResponseFormatter methods, helper functions, unit tests | None | 0.95 |
| Phase 1 - read_file | Implement readable format for priority tool | 1 week | read_file with format parameter, integration tests | Phase 0 | 0.95 |
| Phase 2 - append_entry | Implement readable format for log writing | 1 week | append_entry with format parameter, bulk mode support | Phase 0 | 0.95 |
| Phase 3 - Log Tools | Implement readable format for log query tools | 1 week | read_recent, query_entries with format parameter | Phase 0 | 0.95 |
| Phase 4 - Remaining Tools | Complete format parameter rollout | 2 weeks | All 14 tools with format parameter | Phase 0-3 | 0.9 |
| Phase 5 - Documentation & Polish | Final testing, docs, and release | 1 week | Documentation, visual validation, release | Phase 4 | 0.9 |

**Total Estimated Duration:** 6 weeks
**Critical Path:** Phase 0 → Phase 1 (read_file is highest priority)

---
## Phase 0 — Foundation (ResponseFormatter Extension)
<!-- ID: phase_0 -->

**Objective:** Extend utils/response.py with readable format infrastructure that all tools will use.

**Duration:** 3 days

### Key Tasks

1. **Add Format Constants** (2 hours)
   - Add `FORMAT_READABLE`, `FORMAT_STRUCTURED`, `FORMAT_COMPACT` constants
   - Update class docstrings with format documentation

2. **Implement Helper Methods** (1 day)
   - `_add_line_numbers(content, start=1) -> str` - Cat -n style line numbering
   - `_create_header_box(title, metadata) -> str` - ASCII box header generation
   - `_create_footer_box(audit_data, reminders) -> str` - ASCII box footer
   - `_format_table(headers, rows) -> str` - Aligned ASCII table generator

3. **Implement Core Formatting Methods** (1 day)
   - `format_readable_file_content(data) -> str` - For read_file output
   - `format_readable_log_entries(entries, pagination) -> str` - For log tools
   - `format_readable_projects(projects, active) -> str` - For list_projects
   - `format_readable_confirmation(operation, data) -> str` - For operation confirmations
   - `format_readable_error(error, context) -> str` - Error message formatting

4. **Implement Format Router** (4 hours)
   - `finalize_tool_response(data, format, tool_name) -> Union[Dict, str]`
   - Routes to appropriate formatter based on format + tool_name
   - Handles invalid format gracefully (default to structured + warning)

5. **Unit Tests** (4 hours)
   - `tests/test_response_formatter.py` - Comprehensive unit tests
   - Test line numbering padding and alignment
   - Test ASCII box generation and width calculations
   - Test format routing logic
   - Test error handling

### Deliverables

- [ ] `utils/response.py` extended with ~300 lines of readable format code
- [ ] `tests/test_response_formatter.py` created with 100% coverage of new methods
- [ ] All helper methods tested independently
- [ ] Format router tested with all format values

### Acceptance Criteria

- [ ] All unit tests pass (100% coverage of new code)
- [ ] Line numbering produces correct cat -n format
- [ ] ASCII boxes align correctly at various terminal widths
- [ ] Format router returns correct types (Dict for structured, str for readable)
- [ ] Invalid format values default to structured with warning logged
- [ ] No breaking changes to existing ResponseFormatter functionality

### Dependencies

**None** - This is the foundation phase

### Risks & Mitigations

- **Risk:** ASCII box drawing doesn't align properly
  - **Mitigation:** Comprehensive width calculation tests, manual visual inspection

- **Risk:** Line numbering padding breaks on large line counts
  - **Mitigation:** Test with 1, 10, 100, 1000, 10000 line files

### Notes

This phase blocks all subsequent phases. Must be fully tested and working before proceeding to tool integration.

---
## Phase 1 — read_file Tool (Priority)
<!-- ID: phase_1 -->

**Objective:** Implement readable format for read_file - the highest priority tool with worst current agent experience.

**Duration:** 1 week

### Key Tasks

1. **Add Format Parameter** (2 hours)
   - Add `format: str = "structured"` parameter to read_file signature
   - Update docstring with format parameter documentation
   - Update type hints: `-> Union[Dict[str, Any], str]`

2. **Integrate Format Selection** (1 day)
   - Modify return statements in all 6 modes (scan_only, chunk, line_range, page, full_stream, search)
   - Call `finalize_tool_response(response_data, format, "read_file")` before returning
   - Test each mode with format="readable"

3. **Readable Format Implementation** (2 days)
   - Implement readable output for chunk mode (priority)
   - Implement readable output for line_range mode
   - Implement readable output for page mode
   - Implement readable output for search mode
   - Implement readable output for full_stream mode
   - Implement readable output for scan_only mode

4. **Integration Tests** (1 day)
   - Test read_file(format="readable", mode="chunk")
   - Test read_file(format="readable", mode="line_range", start_line=1, end_line=50)
   - Test read_file(format="readable", mode="search", pattern="def")
   - Test backward compatibility: read_file() without format parameter
   - Test all existing tests pass unchanged

5. **Performance Validation** (1 day)
   - Benchmark readable format overhead vs structured
   - Test large file handling (10K lines)
   - Verify memory usage ≤2x current
   - Verify overhead ≤5ms per call

### Deliverables

- [ ] read_file tool with format parameter fully implemented
- [ ] All 6 output modes support readable format
- [ ] Integration tests for all modes × all formats (18 test cases minimum)
- [ ] Performance benchmarks show acceptable overhead
- [ ] Backward compatibility validated (all existing tests pass)

### Acceptance Criteria

- [ ] read_file(format="readable") produces line-numbered output with header/footer boxes
- [ ] Content has actual line breaks (not escaped `\n`)
- [ ] Metadata in footer section, not mixed with content
- [ ] All existing tests pass without modification
- [ ] Performance overhead ≤5ms
- [ ] Memory usage ≤2x for large files

### Dependencies

**Phase 0 Complete** - Requires ResponseFormatter readable methods

### Risks & Mitigations

- **Risk:** Performance degradation on large files
  - **Mitigation:** Lazy string building, streaming for full_stream mode, performance tests

- **Risk:** Breaking existing read_file integrations
  - **Mitigation:** Default format=structured, comprehensive backward compat tests

### Notes

read_file is the highest priority tool (worst current agent experience). Success here validates the entire approach.

---
## Phase 2 — append_entry Tool
<!-- ID: phase_2 -->

**Objective:** Implement readable format for append_entry - the primary logging tool used by all agents.

**Duration:** 1 week

### Key Tasks

1. **Add Format Parameter** (2 hours)
   - Add `format: str = "structured"` parameter
   - Update docstring and type hints
   - Handle format in both single entry and bulk modes

2. **Implement Readable Confirmation** (2 days)
   - Readable format for single entry success
   - Readable format for bulk entry success
   - Readable format for partial failures (some entries failed)
   - Readable format for complete failures
   - Display written line, path, metadata in readable format

3. **Integration Tests** (2 days)
   - Test append_entry(format="readable", message="test")
   - Test bulk mode: append_entry(format="readable", items=[...])
   - Test error cases with readable format
   - Test backward compatibility
   - Test existing append_entry tests pass unchanged

4. **Performance Validation** (1 day)
   - Benchmark single entry with readable format
   - Benchmark bulk mode with readable format
   - Verify no degradation in structured format performance

### Deliverables

- [ ] append_entry with format parameter for single and bulk modes
- [ ] Readable confirmation output showing entry details clearly
- [ ] Integration tests for all append_entry modes
- [ ] Performance validation completed

### Acceptance Criteria

- [ ] Readable format shows written line prominently
- [ ] Success/failure status clear with emoji
- [ ] Path, metadata, and audit info in organized sections
- [ ] Bulk mode shows summary + individual entry details
- [ ] All existing tests pass without modification
- [ ] Performance overhead ≤5ms

### Dependencies

**Phase 0 Complete** - Requires ResponseFormatter readable methods

### Risks & Mitigations

- **Risk:** Bulk mode readable format too verbose
  - **Mitigation:** Summary section + collapsible details, visual testing

### Notes

append_entry is used heavily by all agents. Readable format will significantly improve logging experience.

---
## Phase 3 — Log Query Tools (read_recent & query_entries)
<!-- ID: phase_3 -->

**Objective:** Implement readable format for log retrieval tools.

**Duration:** 1 week

### Key Tasks

1. **read_recent Tool** (3 days)
   - Add format parameter to read_recent
   - Implement readable format with line-numbered log entries
   - Show pagination info clearly
   - Integration tests for all pagination scenarios

2. **query_entries Tool** (3 days)
   - Add format parameter to query_entries
   - Implement readable format for search results
   - Show filters and result count prominently
   - Integration tests for all query scenarios

3. **Shared Implementation** (1 day)
   - Both tools use `format_readable_log_entries()` helper
   - Ensure consistent output format between tools
   - Test pagination consistency

### Deliverables

- [ ] read_recent with format parameter
- [ ] query_entries with format parameter
- [ ] Consistent readable format for log entries across both tools
- [ ] Integration tests for pagination and filtering

### Acceptance Criteria

- [ ] Log entries line-numbered with emoji, timestamp, agent, message visible
- [ ] Pagination info clear (Page X of Y, Total: N entries)
- [ ] Metadata in footer section
- [ ] All existing tests pass without modification
- [ ] Performance overhead ≤5ms per query

### Dependencies

**Phase 0 Complete** - Requires ResponseFormatter readable methods

### Risks & Mitigations

- **Risk:** Large result sets produce overwhelming output
  - **Mitigation:** Pagination limits, visual hierarchy, compact metadata

### Notes

These tools are used for reviewing project progress. Readable format will make log analysis much easier.

---
## Phase 4 — Remaining Tools (Complete Rollout)
<!-- ID: phase_4 -->

**Objective:** Add format parameter to all remaining tools to complete the rollout.

**Duration:** 2 weeks

### Tools in Scope (9 tools)

1. **list_projects** (2 days)
   - Implement ASCII table format for project listing
   - Show status, last entry time, activity metrics
   - Use `format_readable_projects()` helper

2. **get_project** (1 day)
   - Readable format showing current project details
   - Use `format_readable_confirmation()` helper

3. **set_project** (1 day)
   - Readable confirmation of project selection
   - Show project details clearly

4. **manage_docs** (2 days)
   - Readable confirmation of document operations
   - Show section updated, diff summary, verification status

5. **rotate_log** (2 days)
   - Readable confirmation of log rotation
   - Show old/new file paths, entry counts, integrity status

6. **doctor** (2 days)
   - Readable diagnostic output with organized sections
   - Show health checks, warnings, recommendations

7. **generate_doc_templates** (1 day)
   - Readable confirmation showing generated files

8. **delete_project** (1 day)
   - Readable confirmation with safety warnings

9. **health_check** (1 day)
   - Readable health status output

### Key Tasks

- Add format parameter to each tool (consistent signature)
- Implement readable format using appropriate ResponseFormatter method
- Write integration tests for each tool × each format
- Validate backward compatibility for each tool
- Performance testing for each tool

### Deliverables

- [ ] All 14 tools support format parameter
- [ ] Comprehensive integration tests (42+ test cases total)
- [ ] All tools use consistent readable format patterns
- [ ] Complete backward compatibility validation

### Acceptance Criteria

- [ ] All tools accept format parameter with default="structured"
- [ ] Readable format consistent across all tools (header/content/footer pattern)
- [ ] All existing tests pass without modification
- [ ] No performance regressions in any tool
- [ ] Visual validation completed for all readable outputs

### Dependencies

**Phase 0 Complete** - Requires ResponseFormatter infrastructure

### Risks & Mitigations

- **Risk:** Inconsistent readable format across tools
  - **Mitigation:** Centralized ResponseFormatter methods, visual validation

- **Risk:** Tool-specific edge cases break readable format
  - **Mitigation:** Comprehensive integration tests, error handling

### Notes

This phase completes the technical implementation. All tools will support all three formats.

---
## Phase 5 — Documentation & Final Release
<!-- ID: phase_5 -->

**Objective:** Complete documentation, visual validation, and prepare for release.

**Duration:** 1 week

### Key Tasks

1. **Create FORMAT_SPECIFICATION.md** (2 days)
   - Document all three formats (readable, structured, compact)
   - Include visual examples for each tool
   - Document format parameter usage
   - Create format selection decision tree

2. **Update CLAUDE.md** (1 day)
   - Add format parameter to tool reference section
   - Include format usage examples
   - Document best practices for agents

3. **Update Tool Docstrings** (1 day)
   - Add format parameter documentation to all 14 tools
   - Include format examples in each docstring
   - Update type hints if needed

4. **Visual Validation** (2 days)
   - Run test_output_visual.py to generate samples
   - Manual review of all tool outputs in readable format
   - Verify alignment, box drawing, emoji rendering
   - Test at 80, 120, 160 character terminal widths

5. **Performance Validation** (1 day)
   - Run full performance test suite
   - Compare against baseline JSON results
   - Verify no regressions in structured format
   - Document readable format overhead

6. **Final Testing** (1 day)
   - Run complete test suite (unit + integration + performance)
   - Verify 100% backward compatibility
   - Code coverage analysis (target ≥90% for new code)

7. **Release Preparation** (1 day)
   - Update CHANGELOG.md with format feature details
   - Version bump (v2.2.0)
   - Create release notes with format examples
   - Update MCP server guide

### Deliverables

- [ ] FORMAT_SPECIFICATION.md created with comprehensive examples
- [ ] CLAUDE.md updated with format usage guidance
- [ ] All tool docstrings updated
- [ ] Visual validation completed and samples reviewed
- [ ] Performance validation passed
- [ ] Release notes and CHANGELOG.md updated
- [ ] v2.2.0 ready for deployment

### Acceptance Criteria

- [ ] All documentation complete and reviewed
- [ ] Visual samples verified at multiple terminal widths
- [ ] Performance tests pass with no regressions
- [ ] Code coverage ≥90% for new code
- [ ] All existing tests pass without modification
- [ ] Release notes include format examples and migration guide

### Dependencies

**Phase 4 Complete** - All tools must have format parameter before final docs

### Risks & Mitigations

- **Risk:** Documentation incomplete or examples unclear
  - **Mitigation:** Peer review, visual examples, step-by-step usage guide

### Notes

This phase is critical for agent adoption. Clear documentation with visual examples will drive format parameter usage.

---
## Milestone Tracking
<!-- ID: milestone_tracking -->

| Milestone | Target Date | Owner | Status | Evidence/Link |
|-----------|-------------|-------|--------|---------------|
| Phase 0 - ResponseFormatter Extended | Week 1 | Coder | ⏳ Planned | Phase 0 acceptance criteria |
| Phase 1 - read_file Complete | Week 2 | Coder | ⏳ Planned | Phase 1 acceptance criteria |
| Phase 2 - append_entry Complete | Week 3 | Coder | ⏳ Planned | Phase 2 acceptance criteria |
| Phase 3 - Log Tools Complete | Week 4 | Coder | ⏳ Planned | Phase 3 acceptance criteria |
| Phase 4 - All Tools Complete | Week 6 | Coder | ⏳ Planned | Phase 4 acceptance criteria |
| Phase 5 - Documentation & Release | Week 7 | Coder + Docs | ⏳ Planned | v2.2.0 release |

**Status Legend:**
- ⏳ Planned
- 🚧 In Progress
- ✅ Complete
- ⚠️ Blocked
- ❌ Failed

---
## Cross-Phase Dependencies
<!-- ID: dependencies -->

```
Phase 0 (Foundation)
    ├─> Phase 1 (read_file)
    ├─> Phase 2 (append_entry)
    ├─> Phase 3 (Log Tools)
    └─> Phase 4 (Remaining Tools)
            └─> Phase 5 (Documentation)
```

**Critical Path:** Phase 0 → Phase 1 → Phase 5

**Parallel Opportunities:**
- Phases 1, 2, 3, 4 can proceed in parallel AFTER Phase 0 completes
- However, sequential execution recommended for risk mitigation and learning

---
## Risk Management
<!-- ID: risk_management -->

### High-Risk Items

1. **Phase 0 Foundation Issues**
   - **Impact:** Blocks all subsequent phases
   - **Probability:** Low (0.1)
   - **Mitigation:** Comprehensive unit tests, early implementation
   - **Contingency:** If blocked, reassess architecture with reduced scope

2. **Performance Degradation**
   - **Impact:** Unacceptable overhead for agents
   - **Probability:** Medium (0.3)
   - **Mitigation:** Performance tests in every phase, optimization as needed
   - **Contingency:** Optimize string building, consider caching, reduce metadata in readable format

3. **Backward Compatibility Break**
   - **Impact:** Breaks existing integrations
   - **Probability:** Low (0.1)
   - **Mitigation:** Default format=structured, comprehensive tests
   - **Contingency:** Immediate rollback, hotfix release

### Medium-Risk Items

1. **Inconsistent Readable Format**
   - **Impact:** Poor agent experience, confusion
   - **Probability:** Medium (0.4)
   - **Mitigation:** Centralized ResponseFormatter, visual validation
   - **Contingency:** Refactor to enforce consistency, update specification

2. **Incomplete Documentation**
   - **Impact:** Low adoption of readable format
   - **Probability:** Low (0.2)
   - **Mitigation:** Dedicated documentation phase, visual examples
   - **Contingency:** Extended Phase 5, community feedback integration

---
## Retro Notes & Adjustments
<!-- ID: retro_notes -->

*This section will be populated during implementation with lessons learned and scope adjustments.*

**Phase Retrospective Template:**
- What went well?
- What could be improved?
- Scope changes made and why?
- Performance/quality metrics achieved?
- Recommendations for next phase?

---
