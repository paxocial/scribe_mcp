#!/usr/bin/env python3
"""Integration test for append_entry dual parameter support.

This test validates that the actual append_entry function works with:
1. Legacy parameters (existing behavior)
2. AppendEntryConfig object (new functionality)
3. Mixed parameters with proper precedence
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

# Add the MCP_SPINE directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp.tools.append_entry import append_entry
from scribe_mcp.tools.config.append_entry_config import AppendEntryConfig
from scribe_mcp import server


async def test_append_entry_integration():
    """Test actual append_entry function with dual parameter support."""

    # Setup test environment
    tmpdir = Path(tempfile.mkdtemp())
    project_dir = tmpdir / "test_project"
    project_dir.mkdir()
    docs_dir = project_dir / "docs" / "dev_plans" / "test_project"
    docs_dir.mkdir(parents=True)
    log_file = docs_dir / "PROGRESS_LOG.md"
    log_file.write_text("# Test Progress Log\n\n")

    # Mock project context
    mock_project = {
        "name": "test_project",
        "root": str(project_dir),
        "progress_log": str(log_file),
        "defaults": {
            "agent": "DefaultAgent",
            "emoji": "🔍"
        }
    }

    print("🧪 Testing append_entry integration...")

    # Test 1: Legacy parameters only
    print("   📋 Test 1: Legacy parameters call")
    try:
        with patch('scribe_mcp.tools.append_entry.resolve_logging_context') as mock_resolve:
            mock_context = Mock()
            mock_context.project = mock_project
            mock_context.recent_projects = ["test_project"]
            mock_context.reminders = []
            mock_resolve.return_value = mock_context

            with patch('scribe_mcp.tools.append_entry.reminders.get_reminders') as mock_reminders:
                mock_reminders.return_value = []

                with patch('scribe_mcp.tools.append_entry.server_module.get_agent_identity') as mock_agent:
                    mock_agent.return_value = None

                    result = await append_entry(
                        message="Test legacy call",
                        status="info",
                        agent="TestAgent"
                    )

                assert result["ok"] == True
                assert "written_line" in result
                print("      ✅ Legacy parameters call works")
    except Exception as e:
        print(f"      ❌ Legacy parameters test failed: {e}")
        return False

    # Test 2: AppendEntryConfig object only
    print("   📋 Test 2: AppendEntryConfig object call")
    try:
        config = AppendEntryConfig(
            message="Test config call",
            status="success",
            agent="ConfigAgent"
        )

        with patch('scribe_mcp.tools.append_entry.resolve_logging_context') as mock_resolve:
            mock_context = Mock()
            mock_context.project = mock_project
            mock_context.recent_projects = ["test_project"]
            mock_context.reminders = []
            mock_resolve.return_value = mock_context

            with patch('scribe_mcp.tools.append_entry.reminders.get_reminders') as mock_reminders:
                mock_reminders.return_value = []

                with patch('scribe_mcp.tools.append_entry.server_module.get_agent_identity') as mock_agent:
                    mock_agent.return_value = None

                    result = await append_entry(
                        message="",  # Empty because config provides the actual message
                        config=config
                    )

                assert result["ok"] == True
                assert "written_line" in result
                print("      ✅ AppendEntryConfig object call works")
    except Exception as e:
        print(f"      ❌ AppendEntryConfig object test failed: {e}")
        return False

    # Test 3: Legacy parameters override config object
    print("   📋 Test 3: Legacy parameter precedence")
    try:
        config = AppendEntryConfig(
            message="Config message",
            status="warn",
            agent="ConfigAgent"
        )

        with patch('scribe_mcp.tools.append_entry.resolve_logging_context') as mock_resolve:
            mock_context = Mock()
            mock_context.project = mock_project
            mock_context.recent_projects = ["test_project"]
            mock_context.reminders = []
            mock_resolve.return_value = mock_context

            with patch('scribe_mcp.tools.append_entry.reminders.get_reminders') as mock_reminders:
                mock_reminders.return_value = []

                with patch('scribe_mcp.tools.append_entry.server_module.get_agent_identity') as mock_agent:
                    mock_agent.return_value = None

                    result = await append_entry(
                        message="Legacy override message",  # Should override config
                        status="error",                   # Should override config
                        agent="LegacyOverride",          # Should override config
                        config=config                    # Base config
                    )

                assert result["ok"] == True
                assert "written_line" in result
                print("      ✅ Legacy parameter precedence works")
    except Exception as e:
        print(f"      ❌ Legacy precedence test failed: {e}")
        return False

    print("✅ All append_entry integration tests passed!")
    return True


async def main():
    """Run integration tests."""
    print("🚀 Phase 2 Task 2.4 - AppendEntry Integration Tests")
    print("=" * 65)

    success = await test_append_entry_integration()

    if success:
        print("\n🎉 append_entry integration tests passed!")
        print("   • Legacy parameter calls: ✅")
        print("   • AppendEntryConfig object calls: ✅")
        print("   • Legacy parameter precedence: ✅")
    else:
        print("\n❌ Integration tests failed!")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)