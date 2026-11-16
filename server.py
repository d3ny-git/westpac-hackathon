"""The ONE MCP server for Customer Guardian. Every node's tools are added here.

You don't need to edit this file to add tools. Write a `register(mcp)` function in your
node's file (see nodes/README.md) and the server picks it up automatically.

Run it:
    python server.py --list     show every tool, grouped by node (handy check after adding yours)
    python server.py            start the server over stdio (agent.py does this for you)

Nodes that haven't been built yet are skipped, so the server always starts.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import logging
import sys

from mcp.server.mcpserver import MCPServer

# Each node's module and the label used in logs. A module just needs a register(mcp) function.
NODE_MODULES = {
    "nodes.account": "A  Account",
    "nodes.interaction": "B  Interactions",
    "nodes.ledger.tools": "C  Ledger",
    "nodes.policy": "D  Policy",
    "nodes.actions": "E  Actions",
}

INSTRUCTIONS = (
    "Customer Guardian tools for a bank hardship workflow. Customers are tokens like cust_af4200 "
    "and staff are tokens like staff_19c; there is no personal information. Ledger tools are "
    "read-only. Use only the values tools return; never invent customers, numbers or reasons."
)

# Logs go to stderr: over stdio, stdout is reserved for the MCP protocol itself.
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[server] %(message)s")
log = logging.getLogger("customer-guardian")


def build_server() -> tuple[MCPServer, dict[str, list[str]]]:
    """Create the server and let every built node add its tools.

    Returns the server and {node label: [tool names]} so callers can see what loaded.
    """
    mcp = MCPServer(name="customer-guardian", instructions=INSTRUCTIONS)
    loaded: dict[str, list[str]] = {}

    for module_name, label in NODE_MODULES.items():
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:          # the node's file doesn't exist yet: fine, skip it
                log.info("%-16s not built yet, skipped", label)
                continue
            raise                                # something INSIDE the node is missing: show it

        register = getattr(module, "register", None)
        if register is None:
            log.warning("%-16s has no register(mcp) function, skipped", label)
            continue

        before = {t.name for t in asyncio.run(mcp.list_tools())}
        register(mcp)
        added = sorted({t.name for t in asyncio.run(mcp.list_tools())} - before)
        loaded[label] = added
        log.info("%-16s %d tool(s): %s", label, len(added), ", ".join(added) or "-")

    return mcp, loaded


def main() -> None:
    parser = argparse.ArgumentParser(description="Customer Guardian MCP server")
    parser.add_argument("--list", action="store_true", help="list the tools and exit")
    args = parser.parse_args()

    mcp, loaded = build_server()
    if args.list:
        for label, tools in loaded.items():
            print(label)
            for name in tools:
                print(f"    {name}")
        return
    mcp.run("stdio")


if __name__ == "__main__":
    main()
