#!/usr/bin/env python3
"""Test script to debug append_entry interface issue."""

import asyncio
import sys
from pathlib import Path

# Add MCP_SPINE to Python path
sys.path.insert(0, str(Path(__file__).parent))

async def test_append_entry():
    """Test append_entry function directly."""
    try:
        # Import after path setup
        from scribe_mcp.tools.append_entry import append_entry

        print("Testing append_entry function directly...")

        # Test with minimal parameters
        result = await append_entry(message="Test message")
        print(f"Result type: {type(result)}")
        print(f"Result content: {result}")

        return result

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    result = asyncio.run(test_append_entry())