"""Call one MCP tool by hand, exactly as the AI would, and print the result.

Use it to check your tools work, without needing the AI or an API key:

    python scripts/try_tool.py                                   # list all tools and their inputs
    python scripts/try_tool.py ledger_get_history '{"customer_token": "cust_af4200"}'
    python scripts/try_tool.py account_score_all                 # a tool with no inputs

The second argument is the tool's inputs as JSON (use single quotes around it in the terminal).
It goes through the real MCP server, including @safe_tool's PII check.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # so `server`, `nodes`, `shared` import

from mcp import Client  # noqa: E402

from server import build_server  # noqa: E402


async def list_tools(mcp) -> None:
    async with Client(mcp) as client:
        for tool in (await client.list_tools()).tools:
            inputs = tool.input_schema.get("properties", {})
            required = set(tool.input_schema.get("required", []))
            args = ", ".join(f"{k}{'' if k in required else '?'}" for k in inputs) or "no inputs"
            first_line = (tool.description or "").strip().splitlines()[0] if tool.description else ""
            print(f"{tool.name}({args})\n    {first_line}")


async def call(mcp, name: str, arguments: dict) -> int:
    async with Client(mcp) as client:
        result = await client.call_tool(name, arguments)
    text = "\n".join(getattr(c, "text", "") for c in result.content)
    if result.is_error:
        print(f"ERROR: {text}")
        return 1
    if result.structured_content is not None:
        data = result.structured_content.get("result", result.structured_content)
        print(json.dumps(data, indent=2))
    else:
        print(text)
    return 0


def main() -> int:
    mcp, _ = build_server()
    if len(sys.argv) < 2:
        asyncio.run(list_tools(mcp))
        return 0
    name = sys.argv[1]
    arguments = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    return asyncio.run(call(mcp, name, arguments))


if __name__ == "__main__":
    sys.exit(main())
