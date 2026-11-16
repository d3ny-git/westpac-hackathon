"""Actions (Node E) endpoints: the approval queue, carrying out approved actions, the customer's
phone view and the caller check. Same features as ui/pages/E.py.

Approve / Reject are HUMAN actions: these endpoints exist only for the UI's buttons, and they are
never MCP tools (the MCP server in server.py is unchanged). The staff token must be a person
(Approval.approved_by is a StaffToken, so SYSTEM is refused).

Call codes appear in exactly one place: GET /api/actions/inbox/{token}, the customer's phone view."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi import Path as PathParam
from pydantic import BaseModel

from api.common import hide_call_codes
from api.policy import decide
from nodes.actions import actions_execute_approved, actions_inbox, actions_status, approve, reject
from nodes.ledger import store
from shared.config import CUSTOMER_TOKEN_PATTERN, REC_ID_PATTERN
from shared.schemas import Recommendation

router = APIRouter(prefix="/api/actions", tags=["actions"])


class StaffDecision(BaseModel):
    staff: str                      # the person clicking, e.g. staff_19c


class CallerCheck(BaseModel):
    customer_token: str
    call_code: str = ""             # the code the CALLER quoted (may be wrong: that's the point)
    staff: str                      # who is asking (requested_by)


def load_recommendations() -> list[dict[str, Any]]:
    """Every recommendation with its current ledger-backed status (as ui/pages/E.py does)."""
    items = []
    for entry in store.read(entry_type="RECOMMENDATION"):
        rec = Recommendation.model_validate(entry.data)
        items.append({**rec.model_dump(mode="json"), "status": actions_status(rec.rec_id)["status"]})
    return items


@router.get("")
def queue() -> dict[str, Any]:
    """The approval queue and status of every recommendation, plus the counts for the metrics."""
    items = load_recommendations()
    count = {s: sum(1 for i in items if i["status"] == s)
             for s in ("AWAITING_APPROVAL", "APPROVED", "DONE", "REJECTED")}
    return {"items": items,
            "counts": {"pending": count["AWAITING_APPROVAL"], "approved": count["APPROVED"],
                       "completed": count["DONE"], "rejected": count["REJECTED"], "total": len(items)}}


def _decided(result: dict[str, Any]) -> dict[str, Any]:
    if "error" in result:
        status = f" ({result['status']})" if result.get("status") else ""
        raise HTTPException(400, f"{result['error']}{status}")
    return result                   # may carry a "warning" (approval saved, status update failed)


@router.post("/{rec_id}/approve")
def approve_rec(body: StaffDecision, rec_id: str = PathParam(pattern=REC_ID_PATTERN)) -> dict[str, Any]:
    """A person approves a recommendation (writes APPROVAL + STATUS_UPDATE to the ledger)."""
    return _decided(approve(rec_id, body.staff))


@router.post("/{rec_id}/reject")
def reject_rec(body: StaffDecision, rec_id: str = PathParam(pattern=REC_ID_PATTERN)) -> dict[str, Any]:
    """A person rejects a recommendation. Nothing is sent to the customer."""
    return _decided(reject(rec_id, body.staff))


@router.post("/{rec_id}/execute")
def execute(rec_id: str = PathParam(pattern=REC_ID_PATTERN)) -> dict[str, Any]:
    """Carry out one APPROVED recommendation (re-checked by Node D first). The result says what was
    done, or {"blocked": decision} if D blocked it. The call code is hidden: it's only on the phone."""
    return hide_call_codes(actions_execute_approved(rec_id)[0])


@router.get("/inbox/{token}")
def inbox(token: str = PathParam(pattern=CUSTOMER_TOKEN_PATTERN)) -> list[dict[str, Any]]:
    """What the customer's Westpac app shows. The ONLY response that contains a call code."""
    return actions_inbox(token)


@router.post("/verify-caller")
def verify_caller(body: CallerCheck) -> dict[str, Any]:
    """Someone calls saying they're from Westpac: check the code they quoted with D's policy P3.
    The answer never repeats the real code. The check is recorded in the ledger."""
    return decide({"customer_token": body.customer_token, "action": "VERIFY_CALLER",
                   "requested_by": body.staff, "call_code": body.call_code.strip() or None})
