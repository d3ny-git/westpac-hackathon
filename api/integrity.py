"""Fail closed: the live apps don't act on a ledger they can't trust.

Node D's rules read the ledger. If someone has rewritten an entry (for example, to make a customer's
hardship request look cancelled), check_action would read the forged data and could ALLOW
something it should block. So before the live apps act, they check the ledger first:

    - the hash chain verifies (chain.verify_chain), and
    - the recorded checkpoint still holds, if one was recorded (cutting off or rebuilding
      history would otherwise go unnoticed)

If either fails, the Westpac dashboard's "Check an action", approve/reject, the customer's "Is this
call really Westpac?" check, and the automatic sweep's scoring and execute steps all refuse,
saying why. Nothing is written to a ledger that can't be trusted.

This lives in the live apps' API on purpose: the nodes themselves are unchanged, and the
walkthrough's /api/policy/check still shows the raw policy check, as it explains how D works.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from api.ledger import integrity_report

PAUSED = "Ledger integrity check failed: actions are paused until the ledger is verified"


def ledger_problem() -> Optional[str]:
    """None if the ledger can be trusted; otherwise a short description of what's wrong."""
    report = integrity_report()
    chain = report["report"]
    if not chain["valid"]:
        return f"{chain['problem']} at {chain['first_bad_entry']}"
    checkpoint = report["checkpoint"]
    if checkpoint and not checkpoint["holds"]:
        return f"the checkpoint recorded at {checkpoint['last_entry_id']} no longer holds"
    return None


def require_trusted_ledger() -> None:
    """Refuse (409 Conflict) when the ledger can't be trusted."""
    problem = ledger_problem()
    if problem:
        raise HTTPException(409, f"{PAUSED} ({problem}).")
