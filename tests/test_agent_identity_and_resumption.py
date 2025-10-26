#!/usr/bin/env python3
"""Test automatic agent identification and project resumption."""

import asyncio
import sys
import tempfile
from pathlib import Path

# Add the MCP_SPINE directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.state.manager import StateManager
from scribe_mcp.state.agent_manager import AgentContextManager
from scribe_mcp.state.agent_identity import AgentIdentity


@pytest.mark.asyncio
async def test_automatic_agent_identification():
    """Test automatic agent ID generation and persistence."""
    print("🧪 Testing automatic agent identification...")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        db_path = temp_path / "test.db"
        state_path = temp_path / "state.json"

        # Initialize components
        storage = SQLiteStorage(db_path)
        await storage.setup()
        state_manager = StateManager(state_path)
        agent_identity = AgentIdentity(state_manager)

        # Test 1: Create new agent ID
        print("  ✓ Creating new agent ID...")
        agent_id_1 = await agent_identity.get_or_create_agent_id()
        print(f"    Generated agent ID: {agent_id_1}")

        # Test 2: Get same agent ID from persistent state
        print("  ✓ Retrieving agent ID from persistent state...")
        agent_id_2 = await agent_identity.get_or_create_agent_id()
        if agent_id_1 == agent_id_2:
            print(f"    ✓ Same agent ID retrieved: {agent_id_2}")
        else:
            print(f"    ❌ Agent IDs should match: {agent_id_1} != {agent_id_2}")
            return False

        # Test 3: Agent ID from context
        print("  ✓ Testing agent ID from context...")
        context = {
            "client_id": "test-client-123",
            "session_id": "session-456"
        }
        agent_id_3 = await agent_identity.get_or_create_agent_id(context)
        if agent_id_3.startswith("mcp-"):
            print(f"    ✓ Agent ID from context: {agent_id_3}")
        else:
            print(f"    ❌ Agent ID should come from context: {agent_id_3}")
            return False

        # Test 4: Activity tracking
        print("  ✓ Testing activity tracking...")
        await agent_identity.update_agent_activity(
            agent_id_1, "test_activity", {"test": True}
        )

        # Verify activity was logged
        state = await state_manager.load()
        if (hasattr(state, 'agent_state') and
            'activity_log' in state.agent_state and
            len(state.agent_state['activity_log']) > 0):
            print("    ✓ Activity tracking working")
        else:
            print("    ❌ Activity tracking failed")
            return False

        await storage.close()

    print("✅ Automatic agent identification tests completed successfully!")
    return True


@pytest.mark.asyncio
async def test_project_resumption():
    """Test project resumption functionality."""
    print("🧪 Testing project resumption...")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        db_path = temp_path / "test.db"
        state_path = temp_path / "state.json"

        # Initialize components
        storage = SQLiteStorage(db_path)
        await storage.setup()
        state_manager = StateManager(state_path)
        agent_manager = AgentContextManager(storage, state_manager)
        agent_identity = AgentIdentity(state_manager)

        # Test 1: Set up initial agent project
        print("  ✓ Setting up initial agent project...")
        project = await storage.upsert_project(
            name="ResumptionTestProject",
            repo_root=str(temp_path / "test_project"),
            progress_log_path=str(temp_path / "test_project" / "PROGRESS_LOG.md")
        )
        (temp_path / "test_project").mkdir(parents=True, exist_ok=True)
        (temp_path / "test_project" / "PROGRESS_LOG.md").touch()

        # Agent sets project
        session_1 = await agent_manager.start_session("TestAgent")
        await agent_manager.set_current_project("TestAgent", "ResumptionTestProject", session_1)
        await agent_manager.end_session("TestAgent", session_1)

        print("    ✓ Initial project set for TestAgent")

        # Test 2: Resume agent session (should restore project)
        print("  ✓ Testing project resumption...")
        resumed_session = await agent_identity.resume_agent_session("TestAgent", agent_manager)

        if resumed_session:
            print(f"    ✓ Session resumed: {resumed_session}")

            # Verify project was restored
            current_project = await agent_manager.get_current_project("TestAgent")
            if current_project and current_project["project_name"] == "ResumptionTestProject":
                print(f"    ✓ Project restored: {current_project['project_name']}")
            else:
                print("    ❌ Project was not restored")
                return False
        else:
            print("    ❌ Failed to resume session")
            return False

        # Test 3: Fresh session for new agent
        print("  ✓ Testing fresh session for new agent...")
        fresh_session = await agent_identity.resume_agent_session("NewAgent", agent_manager)

        if fresh_session:
            print(f"    ✓ Fresh session created: {fresh_session}")

            # Verify no project assigned
            current_project = await agent_manager.get_current_project("NewAgent")
            if current_project is None:
                print("    ✓ New agent starts with no project (correct)")
            else:
                print(f"    ❌ New agent should have no project: {current_project}")
                return False
        else:
            print("    ❌ Failed to create fresh session")
            return False

        await storage.close()

    print("✅ Project resumption tests completed successfully!")
    return True


@pytest.mark.asyncio
async def test_agent_state_updates():
    """Test agent state auto-updates."""
    print("🧪 Testing agent state auto-updates...")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        db_path = temp_path / "test.db"
        state_path = temp_path / "state.json"

        # Initialize components
        storage = SQLiteStorage(db_path)
        await storage.setup()
        state_manager = StateManager(state_path)
        agent_identity = AgentIdentity(state_manager)

        agent_id = await agent_identity.get_or_create_agent_id()

        # Test 1: Multiple activity updates
        print("  ✓ Testing multiple activity updates...")
        activities = [
            ("set_project", {"project_name": "TestProject"}),
            ("append_entry", {"message_length": 50}),
            ("read_recent", {"limit": 10}),
            ("query_entries", {"filters": "test"}),
        ]

        for activity_type, metadata in activities:
            await agent_identity.update_agent_activity(agent_id, activity_type, metadata)

        # Verify activities were logged
        state = await state_manager.load()
        if (hasattr(state, 'agent_state') and
            'activity_log' in state.agent_state):
            activity_log = state.agent_state['activity_log']
            if len(activity_log) >= len(activities):
                print(f"    ✓ All {len(activities)} activities logged")
            else:
                print(f"    ❌ Expected {len(activities)} activities, got {len(activity_log)}")
                return False

            # Verify last activity tracking
            if state.agent_state.get('last_activity') == activities[-1][0]:
                print(f"    ✓ Last activity tracked: {activities[-1][0]}")
            else:
                print(f"    ❌ Last activity not tracked correctly")
                return False
        else:
            print("    ❌ Activity log not created")
            return False

        # Test 2: Activity log size limit
        print("  ✓ Testing activity log size limit...")

        # Add many activities to test limit
        for i in range(110):  # More than the 100 limit
            await agent_identity.update_agent_activity(agent_id, "bulk_test", {"index": i})

        # Check that log is limited
        state = await state_manager.load()
        activity_log = state.agent_state['activity_log']
        if len(activity_log) <= 100:
            print(f"    ✓ Activity log limited to {len(activity_log)} entries")
        else:
            print(f"    ❌ Activity log should be limited to 100 entries, got {len(activity_log)}")
            return False

        await storage.close()

    print("✅ Agent state auto-update tests completed successfully!")
    return True


async def main():
    """Run all agent identity and resumption tests."""
    print("🚀 Starting agent identity and resumption tests...\n")

    success1 = await test_automatic_agent_identification()
    print()
    success2 = await test_project_resumption()
    print()
    success3 = await test_agent_state_updates()

    if success1 and success2 and success3:
        print("\n🎉 All agent identity and resumption tests passed!")
    else:
        print("\n❌ Some tests failed!")
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())