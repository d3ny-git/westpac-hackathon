"""The Westpac dashboard's API (/westpac): what staff need to operate Customer Guardian.

Most tabs reuse the existing endpoints (ledger, policy, actions, live). This module adds only:
  - staff sign-in options (staff TOKENS only)
  - approve / reject that also wake the live worker, so an approved item is carried out by the
    next sweep straight away (approve / reject themselves are the existing human-only functions:
    a staff token is required, and they are never MCP tools)
  - the actions Node E carried out, for the Audit tab

Tokens only, every response PII-checked (nothing here is on the RAW_VIEWS allow-list).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi import Path as PathParam

from api.actions import StaffDecision, approve_rec, reject_rec
from api.common import STAFF, hide_call_codes
from api.live import worker
from nodes.ledger import store
from shared.config import REC_ID_PATTERN

router = APIRouter(prefix="/api/westpac", tags=["westpac"])


@router.get("/staff")
def staff() -> list[str]:
    """Who can sign in to the dashboard in the demo (staff tokens, no names)."""
    return STAFF


@router.post("/recommendations/{rec_id}/approve")
def approve(body: StaffDecision, rec_id: str = PathParam(pattern=REC_ID_PATTERN)) -> dict[str, Any]:
    """A person approves; the live sweep carries it out (Node D re-checks it first)."""
    result = approve_rec(body, rec_id)
    worker.wake()
    return {**result, "live": worker.enabled}


@router.post("/recommendations/{rec_id}/reject")
def reject(body: StaffDecision, rec_id: str = PathParam(pattern=REC_ID_PATTERN)) -> dict[str, Any]:
    """A person rejects: nothing is sent to the customer."""
    result = reject_rec(body, rec_id)
    worker.wake()
    return {**result, "live": worker.enabled}


@router.get("/actions-done")
def actions_done() -> list[dict[str, Any]]:
    """What Node E carried out (ACTION entries that aren't D's decisions), newest first. Call codes hidden."""
    done = [e for e in store.read(entry_type="ACTION") if "decision" not in e.data]
    return [{"entry_id": e.entry_id, "created_at": e.created_at.isoformat(), "customer_token": e.customer_token,
             **hide_call_codes(e.data)} for e in reversed(done)]
