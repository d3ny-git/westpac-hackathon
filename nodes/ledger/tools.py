"""Node C's MCP tools: what the AI is allowed to ask the ledger.

All ledger tools are READ-ONLY. Writing (store.append) is plain Python only, so the AI can
never add, change or remove ledger entries.

Tools:
    ledger_get_history              (C-7, now)
    ledger_verify_chain             (added in C-3)
    ledger_combined_score           (added in C-5)
    ledger_quiet_help_candidates    (added in C-6)
    ledger_risk_dashboard           (added in C-6)

This file is also the example to copy for your own node: see nodes/README.md.
"""
from __future__ import annotations

from typing import Optional

from nodes.ledger import store
from shared.config import EntryType
from shared.pii_guard import safe_tool
from shared.schemas import CustomerToken


def register(mcp) -> None:
    """Called once by server.py to add this node's tools to the MCP server."""

    @mcp.tool()
    @safe_tool
    def ledger_get_history(customer_token: CustomerToken,
                           entry_type: Optional[EntryType] = None) -> list[dict]:
        """Everything the ledger holds about one customer, oldest first.

        Each entry has: entry_id, entry_type, data (the message), created_at, prev_hash, hash.
        Optionally filter by entry_type, e.g. "PROMISE" for just their promises.
        Customers are tokens like cust_af4200.
        """
        return store.read(customer_token=customer_token, entry_type=entry_type)
