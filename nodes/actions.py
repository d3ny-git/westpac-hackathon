
"""Node E – Actions.

Human approval and rejection backed by the Promise Ledger, and carrying out
approved recommendations (FLOW-1):

    approve(rec_id, staff) / reject(rec_id, staff)   a PERSON decides (UI only, never a tool)
    actions_pending()                                recommendations awaiting approval
    actions_status(rec_id)                           AWAITING_APPROVAL / APPROVED / REJECTED / DONE
    actions_execute_approved(rec_id=None)            carry out APPROVED recommendations
    actions_inbox(customer_token)                    what the customer's app shows

MCP tools (FLOW-3, register() at the bottom): actions_pending, actions_execute_approved,
actions_status, actions_inbox. approve/reject are NEVER tools: only a person can decide.
Call codes are hidden in everything a tool returns, so the AI never sees one.

What actions_execute_approved() writes (same order as mock_input_output/E_actions):
    QUIET_HELP_PUSH   ACTION (QuietHelpPush, message M-xxxx, OFFER or TIP)           -> STATUS_UPDATE DONE
    BOOK_MEETING      ACTION (MeetingBooking) -> CONTACT_SCHEDULED (call code)
                      -> PROMISE (MEETING)                                            -> STATUS_UPDATE DONE
    ESCALATE          ACTION (Escalation)                                             -> STATUS_UPDATE DONE
"""

import base64
import hashlib
import hmac
import os
from datetime import timedelta
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from nodes.ledger import store
from nodes.policy import check_action
from shared.config import now
from shared.pii_guard import safe_tool
from shared.schemas import (Approval, ContactScheduled, CustomerToken, Escalation, MeetingBooking, Promise,
                            QuietHelpPush, RecId, Recommendation, StatusUpdate)

load_dotenv(Path(__file__).resolve().parents[1] / ".env")    # CALL_CODE_SECRET lives in .env


def _recommendations():
    """Load actual Node D recommendations from the ledger."""
    result = {}

    for entry in store.read(entry_type="RECOMMENDATION"):
        rec = Recommendation.model_validate(entry.data)
        result[rec.rec_id] = rec

    return result


def _statuses():
    """Reconstruct recommendation statuses from ledger history."""
    recommendations = _recommendations()

    statuses = {
        rec_id: rec.status
        for rec_id, rec in recommendations.items()
    }

    # Ledger entries are ordered oldest first.
    for entry in store.read():
        if entry.entry_type == "APPROVAL":
            rec_id = entry.data["rec_id"]

            if rec_id in statuses:
                statuses[rec_id] = (
                    "APPROVED"
                    if entry.data["approved"]
                    else "REJECTED"
                )

        elif entry.entry_type == "STATUS_UPDATE":
            rec_id = entry.data["ref_id"]

            if rec_id in statuses:
                statuses[rec_id] = entry.data["status"]

    return statuses


def _decide(rec_id: str, staff: str, approved: bool) -> dict:
    """Record a human decision in the ledger."""

    recommendations = _recommendations()

    if rec_id not in recommendations:
        return {"error": "Recommendation not found in ledger"}

    statuses = _statuses()

    if statuses[rec_id] != "AWAITING_APPROVAL":
        return {
            "error": "Recommendation already processed",
            "status": statuses[rec_id],
        }

    rec = recommendations[rec_id]

    # Validate staff token and approval data first.
    approval = Approval(
        rec_id=rec_id,
        approved_by=staff,
        approved=approved,
    )

    new_status = "APPROVED" if approved else "REJECTED"

    status_update = StatusUpdate(
        customer_token=rec.customer_token,
        ref_id=rec_id,
        status=new_status,
        updated_by=staff,
    )

    # Persist the actual human decision.
    approval_entry_id = store.append(
        "APPROVAL",
        rec.customer_token,
        approval.model_dump(mode="json"),
    )

    # Record the resulting recommendation status.
    try:
        status_entry_id = store.append(
            "STATUS_UPDATE",
            rec.customer_token,
            status_update.model_dump(mode="json"),
        )
    except Exception as exc:
        # Approval was already written. Do not claim that
        # the whole operation failed or retry automatically.
        return {
            "rec_id": rec_id,
            "status": new_status,
            "approval_entry_id": approval_entry_id,
            "warning": (
                "Approval saved, but STATUS_UPDATE failed: "
                + str(exc)
            ),
        }

    return {
        "rec_id": rec_id,
        "status": new_status,
        "approval": approval.model_dump(mode="json"),
        "approval_entry_id": approval_entry_id,
        "status_entry_id": status_entry_id,
    }


def approve(rec_id: str, staff: str) -> dict:
    """Approve a recommendation after a human UI action."""
    return _decide(rec_id, staff, approved=True)


def reject(rec_id: str, staff: str) -> dict:
    """Reject a recommendation after a human UI action."""
    return _decide(rec_id, staff, approved=False)


def actions_pending() -> list[dict]:
    """Return recommendations still awaiting approval."""

    recommendations = _recommendations()
    statuses = _statuses()

    return [
        rec.model_dump(mode="json")
        for rec_id, rec in recommendations.items()
        if statuses[rec_id] == "AWAITING_APPROVAL"
    ]


def actions_status(rec_id: str) -> dict:
    """Return the current recommendation status."""

    recommendations = _recommendations()

    if rec_id not in recommendations:
        return {"error": "Recommendation not found"}

    statuses = _statuses()

    return {
        "rec_id": rec_id,
        "status": statuses[rec_id],
    }


# ============================================================
# Carrying out approved recommendations (FLOW-1)
# ============================================================

QUIET_HELP_OPTIONS = ["PAUSE_REPAYMENTS", "REDUCE_REPAYMENTS", "BOOK_CALL"]     # the support OFFER
QUIET_HELP_TIP_OPTIONS = ["SEE_MONEY_TIPS"]                                       # the gentle TIP

# What the customer's app shows for each Quiet Help message. D chooses OFFER (they reached out
# first) or TIP (they didn't); a person approves it. The TIP never mentions hardship or implies
# the customer is struggling, so nobody who hasn't asked for help is offended.
QUIET_HELP_TEXT = {
    "OFFER": {"in_app_title": "We're here if you need a hand",
              "in_app_body": "If things are tight right now, you have options. "
                             "Choose one below or ignore this message."},
    "TIP": {"in_app_title": "A tip from Westpac: plan ahead with confidence",
            "in_app_body": "Set up bill reminders, see where your money goes each month, and remember: "
                           "if things ever change, we can work with you on your repayments."},
}
MEETING_DAYS_AHEAD = 2           # meetings are booked 2 days ahead...
MEETING_HOUR = 14                # ...at 2pm (16 Nov 10:00 -> 18 Nov 14:00, as in the SPEC)
MEETING_DESCRIPTION = "Hardship specialist to call at the booked time and quote the call code"
LOCK_SCREEN = "You have a new message from Westpac"   # the ONLY thing ever shown on the lock screen

# TODO (before going beyond the demo): remove this default and require CALL_CODE_SECRET.
# It's here so the demo works without .env. It's the same secret E's mock data used, so
# demo call codes match mock_input_output (hero's meeting R-0004 -> U5PXLW).
DEMO_CALL_CODE_SECRET = "mock-call-code-secret"


class ExecutionError(ValueError):
    """Something stops an action being carried out (e.g. CALL_CODE_SECRET is missing)."""


def call_code(rec_id: str) -> str:
    """The 6-character code a real Westpac caller will quote: hmac(CALL_CODE_SECRET, rec_id).

    The same recommendation always gives the same code, and without the secret nobody can work
    it out. Letters A-Z and digits 2-7 only (base32), e.g. "U5PXLW".
    Uses CALL_CODE_SECRET from .env, or the DEMO default if it isn't set (demo only, see above).
    """
    secret = os.getenv("CALL_CODE_SECRET") or DEMO_CALL_CODE_SECRET
    digest = hmac.new(secret.encode(), rec_id.encode(), hashlib.sha256).digest()
    return base64.b32encode(digest).decode()[:6]


def _approval_for(rec_id: str) -> Optional[Approval]:
    """The latest APPROVAL entry for a recommendation (None if a person never decided)."""
    approvals = [Approval.model_validate(e.data) for e in store.read(entry_type="APPROVAL")
                 if e.data["rec_id"] == rec_id]
    return approvals[-1] if approvals else None


def _execute_one(rec: Recommendation, approval: Approval) -> dict:
    """Carry out one approved recommendation and write everything to the ledger."""
    token = rec.customer_token

    # 1. Re-check with Node D first. Nothing is recorded if D allows it (the action entries
    #    below are the record); a block IS recorded, and the action is not carried out.
    decision = check_action({"customer_token": token, "action": rec.recommendation,
                             "requested_by": "SYSTEM"}, record=False)
    if decision.decision == "BLOCK":
        store.append("BLOCKED", token, decision.model_dump(mode="json"))
        return {"rec_id": rec.rec_id, "blocked": decision.model_dump(mode="json")}

    # 2. Carry it out.
    if rec.recommendation == "QUIET_HELP_PUSH":
        message = rec.quiet_help_message                     # OFFER or TIP, as D chose and a person approved
        options = QUIET_HELP_TIP_OPTIONS if message == "TIP" else QUIET_HELP_OPTIONS
        result = QuietHelpPush(customer_token=token, message_id=store.next_id("M"), options=options,
                               message=message)
        store.append("ACTION", token, result.model_dump(mode="json"))

    elif rec.recommendation == "BOOK_MEETING":
        when = (now() + timedelta(days=MEETING_DAYS_AHEAD)).replace(hour=MEETING_HOUR, minute=0, second=0)
        code = call_code(rec.rec_id)
        staff = approval.approved_by                         # the person who approved runs the meeting
        result = MeetingBooking(customer_token=token, meeting_time=when, staff=staff, call_code=code)
        store.append("ACTION", token, result.model_dump(mode="json"))
        store.append("CONTACT_SCHEDULED", token, ContactScheduled(
            customer_token=token, call_code=code, contact_time=when, staff=staff).model_dump(mode="json"))
        store.append("PROMISE", token, Promise(
            customer_token=token, promise_id=store.next_id("P"), promise_type="MEETING",
            description=MEETING_DESCRIPTION, made_by=staff, made_via="CALL", due=when).model_dump(mode="json"))

    else:                                                    # ESCALATE
        result = Escalation(customer_token=token, why=rec.why)
        store.append("ACTION", token, result.model_dump(mode="json"))

    # 3. Mark the recommendation done.
    store.append("STATUS_UPDATE", token, StatusUpdate(
        customer_token=token, ref_id=rec.rec_id, status="DONE", updated_by="SYSTEM").model_dump(mode="json"))
    return {"rec_id": rec.rec_id, **result.model_dump(mode="json")}


def actions_execute_approved(rec_id: Optional[str] = None) -> list[dict]:
    """Carry out every APPROVED recommendation (or just `rec_id`), oldest first.

    Runs ONLY recommendations with an APPROVAL entry from a person (approved=true) that aren't
    done yet, after re-checking policy with Node D. Returns one result per recommendation:
    what was carried out (as in mock_input_output/E_actions/output/action_results.json),
    or {"rec_id", "blocked": decision} if D blocked it.
    """
    recommendations = _recommendations()
    statuses = _statuses()
    if rec_id is not None and rec_id not in recommendations:
        raise ExecutionError(f"{rec_id} isn't in the ledger")

    results = []
    for rid, rec in recommendations.items():
        if rec_id is not None and rid != rec_id:
            continue
        approval = _approval_for(rid)
        if statuses[rid] != "APPROVED" or approval is None or not approval.approved:
            if rec_id is not None:
                raise ExecutionError(f"{rid} is {statuses[rid]}: only APPROVED recommendations can be carried out")
            continue
        results.append(_execute_one(rec, approval))
    return results


def actions_inbox(customer_token: str) -> list[dict]:
    """What the customer's app shows, oldest first (format of mock_input_output/E_actions/output/customer_inbox.json).

    The lock screen only ever says "You have a new message from Westpac"; the options, meeting
    time and call code are only shown inside the app. A Quiet Help message has `variant`: OFFER
    (the support offer) or TIP (a gentle money tip, no hardship wording). Older pushes are OFFERs.
    """
    inbox = []
    for entry in store.read(customer_token=customer_token, entry_type="ACTION"):
        d = entry.data
        if d.get("action") == "QUIET_HELP_PUSH" and "message_id" in d:
            variant = d.get("message") or "OFFER"
            inbox.append({"message_id": d["message_id"], "kind": "QUIET_HELP", "lock_screen": LOCK_SCREEN,
                          **QUIET_HELP_TEXT[variant], "options": d["options"], "variant": variant})
        elif d.get("action") == "BOOK_MEETING" and "call_code" in d:
            inbox.append({"message_id": None, "kind": "MEETING", "lock_screen": LOCK_SCREEN,
                          "in_app_title": "Your call with a hardship specialist",
                          "in_app_body": "A Westpac hardship specialist will call you at the time below. "
                                         "They will say this code. If a caller can't tell you the code, hang up.",
                          "meeting_time": d["meeting_time"], "call_code": d["call_code"]})
    return inbox


# ============================================================
# MCP tools (FLOW-3): what the AI is allowed to ask Node E
# ============================================================

def _hide_call_codes(value):
    """Call codes are secrets between the bank and the customer: never hand one to the AI."""
    if isinstance(value, list):
        return [_hide_call_codes(v) for v in value]
    if isinstance(value, dict):
        return {k: ("(hidden)" if k == "call_code" else _hide_call_codes(v)) for k, v in value.items()}
    return value


def register(mcp) -> None:
    """Called once by server.py to add Node E's tools to the MCP server.

    There is deliberately NO approve or reject tool: only a person, clicking in the UI, can decide.
    """

    # The tool names are set explicitly: the Python functions are named tool_* so they don't
    # hide the real functions above (calling actions_pending() inside a function also called
    # actions_pending would call itself forever).

    @mcp.tool(name="actions_pending")
    @safe_tool
    def tool_pending() -> list[dict]:
        """Recommendations from Node D that are still waiting for a PERSON to approve or reject them.

        Each item has rec_id, customer_token, recommendation (QUIET_HELP_PUSH, BOOK_MEETING or
        ESCALATE) and why (reason codes). You cannot approve anything: only staff can.
        """
        return actions_pending()

    @mcp.tool(name="actions_execute_approved")
    @safe_tool
    def tool_execute_approved() -> list[dict]:
        """Carry out every recommendation a PERSON has already approved (never anything else).

        Each is re-checked by Node D's policies first. QUIET_HELP_PUSH sends the customer a private
        message; BOOK_MEETING books a call with a specialist (the call code is hidden); ESCALATE
        escalates to a team lead. Returns one result per recommendation carried out, or
        {"rec_id", "blocked": ...} if a policy blocked it. Returns [] if nothing was approved.
        """
        return _hide_call_codes(actions_execute_approved())

    @mcp.tool(name="actions_status")
    @safe_tool
    def tool_status(rec_id: RecId) -> dict:
        """Where a recommendation is now: AWAITING_APPROVAL, APPROVED, REJECTED or DONE. e.g. rec_id "R-0004"."""
        return actions_status(rec_id)

    @mcp.tool(name="actions_inbox")
    @safe_tool
    def tool_inbox(customer_token: CustomerToken) -> list[dict]:
        """The messages a customer can see in their Westpac app (Quiet Help messages, booked calls).

        A Quiet Help message has variant OFFER (support offer) or TIP (gentle money tip).
        The lock screen only ever says "You have a new message from Westpac". Call codes are hidden.
        """
        return _hide_call_codes(actions_inbox(customer_token))
