"""Node C's MCP tools: what the AI is allowed to ask the ledger.

All ledger tools are READ-ONLY. Writing (store.append) is plain Python only, so the AI can
never add, change or remove ledger entries.

Tools:
    ledger_get_history              (C-7)
    ledger_verify_chain             (C-3)
    ledger_combined_score           (C-5)
    ledger_quiet_help_candidates    (C-6)
    ledger_risk_dashboard           (C-6)

This file is also the example to copy for your own node: see nodes/README.md.
"""
from __future__ import annotations

from typing import Optional

from nodes.ledger import store
from nodes.ledger.chain import verify_chain
from nodes.ledger.dashboard import risk_dashboard
from nodes.ledger.quiet_help import combined_score, open_hardship_case, quiet_help_candidates
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

    @mcp.tool()
    @safe_tool
    def ledger_verify_chain() -> dict:
        """Check that nobody has changed, removed or inserted ledger entries since they were written.

        Returns valid (true/false), entries_checked, and if something is wrong: first_bad_entry,
        problem (EDITED, BROKEN_LINK, MISSING_ENTRY or UNREADABLE) and a one-line detail.
        Also returns last_entry_id and head_hash (the fingerprint of the newest entry).
        If valid is false, the ledger can't be trusted: stop and report "LEDGER TAMPERED".
        """
        return verify_chain()

    @mcp.tool()
    @safe_tool
    def ledger_combined_score(customer_token: CustomerToken) -> dict:
        """A customer's overall hardship score and whether they have an open hardship case.

        score = the higher of the account (A) and interaction (B) scores plus a quarter of the
        lower one, capped at 100. band is LOW (<30), MODERATE (30-59), HIGH (60-79) or CRITICAL (80+).
        Also returns account_score, interaction_score, the reason codes behind them, and
        open_hardship_case (the open hardship promise with its due date, or null).
        If the customer has never been scored, scored is false.
        """
        score = combined_score(customer_token)
        case = open_hardship_case(customer_token)
        result = {"customer_token": customer_token, "scored": score is not None,
                  "open_hardship_case": case}
        if score:
            result.update(score.model_dump())
        return result

    @mcp.tool()
    @safe_tool
    def ledger_quiet_help_candidates() -> list[dict]:
        """Customers who should be RECOMMENDED a Quiet Help push, highest hardship score first.

        Rule: combined score HIGH or CRITICAL, AND no open hardship case, AND no Quiet Help push
        in the last 30 days. Each item has customer_token, score, band, reasons, last_quiet_help.
        This is only a list: nothing is sent until a recommendation is approved by a person.
        """
        return quiet_help_candidates()

    @mcp.tool()
    @safe_tool
    def ledger_risk_dashboard() -> list[dict]:
        """Every promise the bank hasn't kept yet, most at-risk customers first, then soonest due.

        Each row has promise_id, customer_token, promise_type, description, due, hours_to_due
        (negative = overdue), urgency (OVERDUE, DUE_SOON within 24h, UPCOMING), score and band.
        """
        return risk_dashboard()
