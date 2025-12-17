import os
from datetime import datetime, timezone
from pathlib import Path

from scribe_mcp.utils.reminder_engine import ReminderContext, ReminderEngine


def test_reminder_cooldown_cache_roundtrip(monkeypatch, tmp_path):
    cache_path = tmp_path / "reminder_cooldowns.json"
    monkeypatch.setenv("SCRIBE_REMINDER_CACHE_PATH", str(cache_path))

    engine = ReminderEngine()
    key = "/tmp/repo|agentA|append_entry|teaching.example"
    engine.history.reminder_hashes[key] = datetime.now(timezone.utc)
    engine._cooldown_cache_dirty = True  # noqa: SLF001 - test-only access
    engine._save_cooldown_cache()  # noqa: SLF001 - test-only access

    assert cache_path.exists()

    engine2 = ReminderEngine()
    assert key in engine2.history.reminder_hashes


def test_reset_cooldowns_scoped_to_project_and_agent(monkeypatch, tmp_path):
    cache_path = tmp_path / "reminder_cooldowns.json"
    monkeypatch.setenv("SCRIBE_REMINDER_CACHE_PATH", str(cache_path))

    engine = ReminderEngine()
    engine.history.reminder_hashes["/tmp/repo|agentA|append_entry|r1"] = datetime.now(timezone.utc)
    engine.history.reminder_hashes["/tmp/repo|agentB|append_entry|r2"] = datetime.now(timezone.utc)
    engine.history.reminder_hashes["/other/repo|agentA|append_entry|r3"] = datetime.now(timezone.utc)
    engine._cooldown_cache_dirty = True  # noqa: SLF001 - test-only access
    engine._save_cooldown_cache()  # noqa: SLF001 - test-only access

    cleared = engine.reset_cooldowns(project_root="/tmp/repo", agent_id="agentA")
    assert cleared == 1
    assert "/tmp/repo|agentA|append_entry|r1" not in engine.history.reminder_hashes
    assert "/tmp/repo|agentB|append_entry|r2" in engine.history.reminder_hashes
    assert "/other/repo|agentA|append_entry|r3" in engine.history.reminder_hashes

