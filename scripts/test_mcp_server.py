#!/usr/bin/env python3
"""Smoke test for the Scribe MCP server."""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, Dict


INITIALIZE_REQUEST: Dict[str, Any] = {
    "jsonrpc": "2.0",
    "method": "initialize",
    "id": 1,
    "params": {
        "protocolVersion": "1.0",
        "capabilities": {
            "tools": {"listChanged": False},
            "resources": {"listChanged": False},
            "prompts": {"listChanged": False},
        },
        "clientInfo": {"name": "scribe-smoke-test", "version": "0.1"},
    },
}

INITIALIZED_NOTIFICATION: Dict[str, Any] = {
    "jsonrpc": "2.0",
    "method": "notifications/initialized",
    "params": {},
}

LIST_TOOLS_REQUEST: Dict[str, Any] = {
    "jsonrpc": "2.0",
    "method": "tools/list",
    "id": 2,
    "params": {},
}

TIMEOUT_SECONDS = 10


async def run_test() -> None:
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "MCP_SPINE.scribe_mcp.server",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        if not proc.stdin or not proc.stdout:
            raise RuntimeError("Failed to connect stdio pipes to MCP server process.")

        async def send(payload: Dict[str, Any]) -> None:
            message = json.dumps(payload) + "\n"
            proc.stdin.write(message.encode("utf-8"))
            await proc.stdin.drain()

        async def read_response(expected_id: int | None) -> Dict[str, Any]:
            while True:
                raw_line = await asyncio.wait_for(proc.stdout.readline(), timeout=TIMEOUT_SECONDS)
                if not raw_line:
                    stderr_output = (await proc.stderr.read()).decode("utf-8", errors="ignore")
                    raise RuntimeError(f"No response from MCP server.\nStderr:\n{stderr_output}")
                try:
                    message = json.loads(raw_line.decode("utf-8"))
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"Invalid JSON from MCP server: {raw_line!r}") from exc

                if expected_id is not None and message.get("id") != expected_id:
                    # Ignore notifications or responses to other requests.
                    continue
                return message

        # Initialize handshake
        await send(INITIALIZE_REQUEST)
        init_response = await read_response(expected_id=INITIALIZE_REQUEST["id"])
        if "error" in init_response:
            raise RuntimeError(f"Initialization failed: {init_response['error']}")

        await send(INITIALIZED_NOTIFICATION)

        # Request tool list
        await send(LIST_TOOLS_REQUEST)
        list_response = await read_response(expected_id=LIST_TOOLS_REQUEST["id"])
        # Debug: capture server stdout notifications from previous steps if needed.
        if "error" in list_response:
            raise RuntimeError(f"MCP server responded with error: {list_response['error']}")

        result = list_response.get("result")
        if not isinstance(result, dict) or "tools" not in result:
            raise RuntimeError(f"Unexpected response payload: {list_response}")

        tools = result["tools"]
        if not isinstance(tools, list) or not tools:
            # Try a second time after a short delay to allow initialization routines.
            await asyncio.sleep(0.1)
            await send({**LIST_TOOLS_REQUEST, "id": LIST_TOOLS_REQUEST["id"] + 1})
            list_response = await read_response(expected_id=LIST_TOOLS_REQUEST["id"] + 1)
            result = list_response.get("result") if isinstance(list_response, dict) else None
            tools = result.get("tools") if isinstance(result, dict) else None
            if not isinstance(tools, list) or not tools:
                raise RuntimeError(f"MCP server returned no tools. Payload: {list_response}")

        print("✅ MCP server responded successfully.")
        print(f"✅ Registered tools: {len(tools)}")

    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=3)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        if proc.stderr:
            leftover = await proc.stderr.read()
            if leftover:
                sys.stderr.write(leftover.decode("utf-8", errors="ignore"))


if __name__ == "__main__":
    try:
        asyncio.run(run_test())
    except Exception as exc:
        print(f"❌ {exc}", file=sys.stderr)
        sys.exit(1)
