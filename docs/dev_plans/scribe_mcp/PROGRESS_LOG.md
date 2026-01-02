# 📜 Progress Log — Scribe MCP Server
**Maintained By:** CortaLabs
**Timezone:** UTC

---

## Entry Format

```
[EMOJI] [YYYY-MM-DD HH:MM:SS UTC] [Agent: <name>] [Project: Scribe MCP Server] Message text | key=value
```

*Use `scripts/scribe.py` to append new entries automatically.*
```
python scripts/scribe.py "Scribe workflow configured for development logging" --status success --meta ticket=init --meta scope=docs
```

[ℹ️] [2025-12-07 20:42:16 UTC] [Agent: Codex] [Project: scribe_mcp] Investigating read_recent behavior after latest rotate_log and registry changes for project "Scribe Project Registry Upgrade". | project=Scribe Project Registry Upgrade; component=read_recent; phase=verification; reasoning={'why': 'User reported historical issues with read_recent returning no entries; we need to verify current behavior via MCP and ensure DB mirror + progress log integration are healthy.', 'what': 'Confirm current active project, switch to Scribe Project Registry Upgrade, then call read_recent to see if it returns recent entries; if it fails or returns empty unexpectedly, inspect DB mirror and tool wiring.', 'how': 'Used get_project to inspect current context (scribe_mcp), will switch to Scribe Project Registry Upgrade via set_project and then call read_recent for that project using MCP tools, comparing results to on-disk PROGRESS_LOG if necessary.'}; log_type=progress
[ℹ️] [2026-01-02T10:00:02.130724+00:00] [Agent: 2e4e9cb6-c7f2-488a-a54e-0f64b6a58322] [Project: scribe_mcp] read_file | execution_id=bd5e21dd-0291-4320-beaa-56b63e1dc5d3; session_id=897279c7-91d4-4b0e-9180-933bad78e25e; intent=tool:read_file; agent_kind=other; agent_instance_id=2e4e9cb6-c7f2-488a-a54e-0f64b6a58322; agent_sub_id=None; agent_display_name=None; agent_model=None; read_mode=scan_only; absolute_path=/home/austin/projects/MCP_SPINE/scribe_mcp/docs/dev_plans/scribe_mcp/PROGRESS_LOG.md; repo_relative_path=docs/dev_plans/scribe_mcp/PROGRESS_LOG.md; byte_size=1399; line_count=18; sha256=391e0ddf18a0fea47e6eea649cf1f59a935743745f21d638092d40026724d5fb; newline_type=LF; encoding=utf-8; estimated_chunk_count=1
[✅] [2026-01-02 11:13:55 UTC] [Agent: Codex] [Project: scribe_mcp] Added --rebuild flag to scripts/reindex_vector.py to clear the FAISS index via vector_indexer.rebuild_index before reindexing. reasoning: {"why":"User requested a clean rebuild so old coarse chunks are removed before reindex.","what":"Constraints: destructive action must be explicit; keep default behavior unchanged; handle rebuild errors cleanly.","how":"Added rebuild arg, passed into _run_reindex, and invoked vector_indexer.rebuild_index with error handling."} | action=code_change; files_changed=["scripts/reindex_vector.py"]; topic=vector_rebuild_flag; log_type=progress; content_type=log
