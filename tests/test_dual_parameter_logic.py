#!/usr/bin/env python3
"""Test dual parameter logic for append_entry function.

This test validates the parameter handling logic without full integration.
"""

import asyncio
import sys
from pathlib import Path

# Add the MCP_SPINE directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp.tools.config.append_entry_config import AppendEntryConfig


def test_dual_parameter_logic():
    """Test the dual parameter logic that was implemented in append_entry."""

    print("🧪 Testing dual parameter logic...")

    # Test 1: Legacy parameters only
    print("   📋 Test 1: Legacy parameters only")
    try:
        # Simulate the logic from append_entry when no config is provided
        message = "Test legacy"
        status = "info"
        agent = "LegacyAgent"
        config = None

        if config is not None:
            # This path won't execute
            pass
        else:
            # This path simulates the actual logic
            final_config = AppendEntryConfig.from_legacy_params(
                message=message,
                status=status,
                agent=agent
            )

        assert final_config.message == "Test legacy"
        assert final_config.status == "info"
        assert final_config.agent == "LegacyAgent"
        print("      ✅ Legacy parameters only logic works")
    except Exception as e:
        print(f"      ❌ Legacy parameters test failed: {e}")
        return False

    # Test 2: Config object provided
    print("   📋 Test 2: Config object provided")
    try:
        # Simulate config object only
        message = ""
        status = None
        agent = None
        config = AppendEntryConfig(
            message="Test config only",
            status="success",
            agent="ConfigAgent"
        )

        if config is not None:
            # Create configuration object from legacy parameters to ensure precedence
            legacy_config = AppendEntryConfig.from_legacy_params(
                message=message,
                status=status,
                agent=agent
            )

            # Create merged configuration: config as base, legacy_config as override
            config_dict = config.to_dict()
            legacy_dict = legacy_config.to_dict()

            # Apply legacy overrides for non-None values
            for key, value in legacy_dict.items():
                if value is not None or key in ['message', 'auto_split']:
                    config_dict[key] = value

            # Create final configuration
            final_config = AppendEntryConfig(**config_dict)
        else:
            final_config = AppendEntryConfig.from_legacy_params(
                message=message,
                status=status,
                agent=agent
            )

        assert final_config.message == "Test config only"
        assert final_config.status == "success"
        assert final_config.agent == "ConfigAgent"
        print("      ✅ Config object only logic works")
    except Exception as e:
        print(f"      ❌ Config object test failed: {e}")
        return False

    # Test 3: Legacy parameters override config object
    print("   📋 Test 3: Legacy parameter precedence")
    try:
        # Simulate mixed parameters (both config and legacy provided)
        message = "Legacy override"
        status = "error"
        agent = "LegacyOverride"
        config = AppendEntryConfig(
            message="Config message",
            status="warn",
            agent="ConfigAgent"
        )

        if config is not None:
            # Create configuration object from legacy parameters to ensure precedence
            legacy_config = AppendEntryConfig.from_legacy_params(
                message=message,
                status=status,
                agent=agent
            )

            # Create merged configuration: config as base, legacy_config as override
            config_dict = config.to_dict()
            legacy_dict = legacy_config.to_dict()

            # Apply legacy overrides for non-None values
            for key, value in legacy_dict.items():
                if value is not None or key in ['message', 'auto_split']:
                    config_dict[key] = value

            # Create final configuration
            final_config = AppendEntryConfig(**config_dict)
        else:
            final_config = AppendEntryConfig.from_legacy_params(
                message=message,
                status=status,
                agent=agent
            )

        # Verify legacy parameters took precedence
        assert final_config.message == "Legacy override"
        assert final_config.status == "error"
        assert final_config.agent == "LegacyOverride"
        print("      ✅ Legacy parameter precedence logic works")
    except Exception as e:
        print(f"      ❌ Legacy precedence test failed: {e}")
        return False

    # Test 4: Bulk mode parameters
    print("   📋 Test 4: Bulk mode parameters")
    try:
        # Test items_list through config
        message = ""
        items = None
        items_list = None
        config = AppendEntryConfig(
            items_list=[
                {"message": "Item 1", "status": "info"},
                {"message": "Item 2", "status": "success"}
            ]
        )

        if config is not None:
            legacy_config = AppendEntryConfig.from_legacy_params(
                message=message,
                items=items,
                items_list=items_list
            )

            config_dict = config.to_dict()
            legacy_dict = legacy_config.to_dict()

            # Apply legacy overrides
            for key, value in legacy_dict.items():
                if value is not None or key in ['message', 'auto_split']:
                    config_dict[key] = value

            final_config = AppendEntryConfig(**config_dict)
        else:
            final_config = AppendEntryConfig.from_legacy_params(
                message=message,
                items=items,
                items_list=items_list
            )

        assert final_config.is_bulk_mode() == True
        assert len(final_config.items_list) == 2
        print("      ✅ Bulk mode parameters work correctly")
    except Exception as e:
        print(f"      ❌ Bulk mode test failed: {e}")
        return False

    # Test 5: Empty config with legacy parameters
    print("   📋 Test 5: Empty config with legacy parameters")
    try:
        message = "Empty config test"
        status = "info"
        config = AppendEntryConfig()  # Empty config

        if config is not None:
            legacy_config = AppendEntryConfig.from_legacy_params(
                message=message,
                status=status
            )

            config_dict = config.to_dict()
            legacy_dict = legacy_config.to_dict()

            # Apply legacy overrides
            for key, value in legacy_dict.items():
                if value is not None or key in ['message', 'auto_split']:
                    config_dict[key] = value

            final_config = AppendEntryConfig(**config_dict)
        else:
            final_config = AppendEntryConfig.from_legacy_params(
                message=message,
                status=status
            )

        assert final_config.message == "Empty config test"
        assert final_config.status == "info"
        print("      ✅ Empty config with legacy parameters works")
    except Exception as e:
        print(f"      ❌ Empty config test failed: {e}")
        return False

    print("✅ All dual parameter logic tests passed!")
    return True


def main():
    """Run logic tests."""
    print("🚀 Phase 2 Task 2.4 - Dual Parameter Logic Tests")
    print("=" * 60)

    success = test_dual_parameter_logic()

    if success:
        print("\n🎉 Dual parameter logic tests passed!")
        print("   • Legacy parameter handling: ✅")
        print("   • Config object handling: ✅")
        print("   • Legacy parameter precedence: ✅")
        print("   • Bulk mode support: ✅")
        print("   • Empty config handling: ✅")
    else:
        print("\n❌ Logic tests failed!")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)