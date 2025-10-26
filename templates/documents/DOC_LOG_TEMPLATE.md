# 📋 Documentation Update Log — {{PROJECT_NAME}}
**Maintained By:** {{AUTHOR}}
**Timezone:** UTC

> This log tracks all changes to project documentation files. Use via Scribe MCP tool with `log_type="doc_updates"` or `--log doc_updates`.

{{#IS_ROTATION}}
---

## 🔄 Log Rotation Information
**Rotation ID:** {{ROTATION_ID}}
**Rotation Timestamp:** {{ROTATION_TIMESTAMP_UTC}}
**Current Sequence:** {{CURRENT_SEQUENCE}}
**Total Rotations:** {{TOTAL_ROTATIONS}}

{{#PREVIOUS_LOG_PATH}}
### Previous Log Reference
- **Path:** {{PREVIOUS_LOG_PATH}}
- **Hash:** {{PREVIOUS_LOG_HASH}}
- **Entries:** {{PREVIOUS_LOG_ENTRIES}}
{{/PREVIOUS_LOG_PATH}}
{{/IS_ROTATION}}

---

## Entry Format
```
[EMOJI] [YYYY-MM-DD HH:MM:SS UTC] [Agent: <name>] [Project: {{PROJECT_NAME}}] Message text | doc=<doc_name>; section=<section_id>; action=<action_type>; [additional metadata]
```

**Required Metadata Fields:**
- `doc`: Document name (e.g., "architecture", "phase_plan", "checklist")
- `section`: Section ID being modified (e.g., "directory_structure", "phase_overview")
- `action`: Action type (replace_section, append, status_update)

**Optional Metadata Fields:**
- `file_path`: Full path to document file
- `changes_count`: Number of lines changed
- `review_status`: Status of any review (pending/approved/rejected)
- `reviewer`: Name of reviewer if applicable
- `jira_ticket`: Associated ticket number
- `confidence`: Confidence level of changes (0-1)
- `context`: Additional context about the change

---

## Tips for Documentation Updates
- Always specify which document section you're updating using `section=` metadata
- Include `action=` to indicate the type of modification
- Reference specific checklist items or phases when applicable
- Use `--dry-run` first when making structural changes
- All documentation changes are automatically tracked and versioned

---

## Entries will populate below