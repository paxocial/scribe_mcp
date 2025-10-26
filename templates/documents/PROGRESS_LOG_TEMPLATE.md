# 📜 Progress Log — {{PROJECT_NAME}}
**Maintained By:** {{AUTHOR}}
**Timezone:** UTC

> Generated automatically. Use the Scribe MCP tool (`append_entry`) or `scripts/scribe.py` to append new entries. Never edit past lines by hand.

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

{{#HASH_CHAIN_PREVIOUS}}
### Hash Chain Information
- **Chain Sequence:** {{HASH_CHAIN_SEQUENCE}}
- **Previous Hash:** {{HASH_CHAIN_PREVIOUS}}
- **Root Hash:** {{HASH_CHAIN_ROOT}}
{{/HASH_CHAIN_PREVIOUS}}

{{/IS_ROTATION}}

---

## Entry Format
```
[EMOJI] [YYYY-MM-DD HH:MM:SS UTC] [Agent: <name>] [Project: {{PROJECT_NAME}}] Message text | key=value; key2=value2
```

**Tips:**
- Always include `meta` fields tying work back to the checklist/phase (e.g., `phase=1` or `checklist_id=phase0-task2`).
- Keep confidence in a `confidence=` meta key if useful.
- Use `--dry-run` first when unsure what will be written.

---

## Reminders
- Append after every meaningful change (code, docs, decisions).
- Mention updated docs explicitly (e.g., `docs=architecture,phase_plan`).
- Rotate the log (via `rotate_log`) when it nears 200 entries.
- All rotations are cryptographically verified and auditable.

---

## Entries will populate below




