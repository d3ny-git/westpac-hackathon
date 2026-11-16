"""Node D: the Policy Agent's gatekeeper (D-1, D-2).

Before the bank does something to a customer (sends a default notice, offers a credit card,
trusts someone who says they're calling from Westpac), it asks Node D first. D looks the
customer up in the ledger and answers ALLOW or BLOCK, with the policy and a plain-English reason.
Every answer is written back to the ledger, so there's a record of what was asked and decided.

The rules are plain Python, not AI: the same ledger and the same request always give the same answer.

Policies:
    P1  promise or deadline near / missed      -> alert / escalate   (D-3, not in this file yet)
    P2  collections or default notice while a hardship case is open  -> BLOCK
    P3  "calling from Westpac": ALLOW if the call code matches a CONTACT_SCHEDULED entry,
        otherwise BLOCK, possible scam  (D-2)
    P4  credit card or loan offer to a HIGH or CRITICAL customer     -> BLOCK

Usage:
    from nodes.policy import check_action

    decision = check_action({"customer_token": "cust_af4200",
                             "action": "SEND_DEFAULT_NOTICE",
                             "requested_by": "staff_44a"})
    decision.decision   # "BLOCK"
    decision.policy     # "P2"
    decision.reason     # "Hardship request received 6 days ago, response due in 15 days"
"""
from __future__ import annotations

import hmac
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from nodes.ledger import store
from nodes.ledger.quiet_help import CombinedScore, combined_score, open_hardship_case
from shared.config import (COLLECTIONS_ACTIONS, CREDIT_OFFER_ACTIONS, HARDSHIP_RESPONSE_DAYS, HIGH_OR_ABOVE,
                           ActionType, DecisionResult, EntryType, PolicyId, now)
from shared.schemas import ActionRequest, ContactScheduled, Decision, Promise

DbPath = Optional[Path | str]

# The action groups as plain strings, because models store enums as strings (use_enum_values).
_COLLECTIONS = {a.value for a in COLLECTIONS_ACTIONS}
_CREDIT_OFFERS = {a.value for a in CREDIT_OFFER_ACTIONS}
_HIGH_OR_ABOVE = {b.value for b in HIGH_OR_ABOVE}


def _days(n: int) -> str:
    """'1 day' or 'N days'."""
    return f"{n} day" if n == 1 else f"{n} days"


def _block(request: ActionRequest, policy: PolicyId, reason: str, flags: Optional[list[str]] = None) -> Decision:
    return Decision(customer_token=request.customer_token, action=request.action,
                    decision=DecisionResult.BLOCK, policy=policy, reason=reason, flags=flags or [])


# ---------------------------------------------------------------------------
# The policies. Each one is a pure function: it gets the facts it needs passed in (no database),
# and returns a BLOCK Decision if it applies, or None if it has nothing to say.
# ---------------------------------------------------------------------------
def p2_collections_during_hardship(request: ActionRequest, case: Optional[Promise],
                                   at: datetime) -> Optional[Decision]:
    """P2: no collections or default notices while the customer has an open hardship case.

    `case` is the open HARDSHIP_RESPONSE promise (or None). Days are counted in calendar days,
    so a form received on 10 Nov is "6 days ago" on 16 Nov, whatever the time of day.
    """
    if request.action not in _COLLECTIONS or case is None:
        return None

    received = case.due - timedelta(days=HARDSHIP_RESPONSE_DAYS)
    days_ago = (at.date() - received.date()).days
    received_text = "received today" if days_ago <= 0 else f"received {_days(days_ago)} ago"

    if at <= case.due:
        days_left = (case.due.date() - at.date()).days
        due_text = "response due today" if days_left == 0 else f"response due in {_days(days_left)}"
    else:
        days_over = (at.date() - case.due.date()).days
        due_text = "response was due earlier today" if days_over == 0 else f"response was due {_days(days_over)} ago"

    return _block(request, PolicyId.P2, f"Hardship request {received_text}, {due_text}")


def p4_credit_offer_to_high_risk(request: ActionRequest, score: Optional[CombinedScore]) -> Optional[Decision]:
    """P4: no credit card, loan or limit-increase offers to HIGH or CRITICAL customers.

    A customer who has never been scored (score is None) isn't blocked by this policy.
    """
    if request.action not in _CREDIT_OFFERS or score is None or score.band not in _HIGH_OR_ABOVE:
        return None
    return _block(request, PolicyId.P4,
                  f"Hardship score is {score.score} ({score.band}); credit offers are blocked "
                  f"for HIGH and CRITICAL customers")


def normalise_call_code(code: str) -> str:
    """Tidy up a code as a customer might type or read it: 'u5p-xlw ' -> 'U5PXLW'."""
    return re.sub(r"[\s-]", "", code or "").upper()


def p3_verify_caller(request: ActionRequest, contacts: list[ContactScheduled]) -> Optional[Decision]:
    """P3: someone claims to be calling from Westpac. Are they real?

    When Node E books a call, it writes a CONTACT_SCHEDULED entry with a call code, and the customer
    sees that code in their app. A real Westpac caller quotes it. So:
      - this customer has a booked call with the SAME code  -> ALLOW (the caller is genuine)
      - no booked call, or a different code                  -> BLOCK, flagged as a possible scam

    `contacts` are this customer's CONTACT_SCHEDULED entries. The reason never repeats the code,
    so a scammer can't learn the right one by trying.
    """
    if request.action != ActionType.VERIFY_CALLER.value:
        return None

    quoted = normalise_call_code(request.call_code or "")
    if not contacts:
        return _block(request, PolicyId.P3,
                      "No call from Westpac is booked for this customer, so the caller can't be "
                      "confirmed: possible scam", flags=["POSSIBLE_SCAM"])

    for contact in contacts:
        # compare_digest takes the same time whether the codes match or not (no timing hints)
        if hmac.compare_digest(quoted, contact.call_code):
            return Decision(customer_token=request.customer_token, action=request.action,
                            decision=DecisionResult.ALLOW,
                            reason=f"Call code matches the call booked for "
                                   f"{contact.contact_time:%d %b %H:%M} with {contact.staff}")

    return _block(request, PolicyId.P3,
                  "The call code doesn't match the call Westpac booked for this customer: possible scam",
                  flags=["POSSIBLE_SCAM"])


# ---------------------------------------------------------------------------
# The gatekeeper
# ---------------------------------------------------------------------------
def check_action(request: ActionRequest | dict, *, record: bool = True, db_path: DbPath = None) -> Decision:
    """Check one requested action against the policies and return ALLOW or BLOCK.

    request   an ActionRequest, or a dict with the same fields
              (customer_token, action, requested_by, and call_code for VERIFY_CALLER)
    record    True (normal use): write the decision to the ledger, as a BLOCKED entry for a block
              or an ACTION entry for an allow. False: just answer (for previews and tests).

    Policies are checked in order P2, P4, P3, and the first one with an answer wins
    (P2 and P4 can only block; P3 allows a genuine caller or blocks a suspected scam).
    """
    # A dict is checked against the ActionRequest model (raises pydantic.ValidationError if invalid).
    req = request if isinstance(request, ActionRequest) else ActionRequest(**request)

    # 1. Gather the facts from the ledger (time always comes from config.now(), never the real clock).
    at = now()
    case = open_hardship_case(req.customer_token, db_path=db_path)
    score = combined_score(req.customer_token, db_path=db_path)

    contacts: list[ContactScheduled] = []
    if req.action == ActionType.VERIFY_CALLER.value:
        contacts = [ContactScheduled(**e.data) for e in store.read(
            customer_token=req.customer_token, entry_type=EntryType.CONTACT_SCHEDULED, db_path=db_path)]

    # 2. Run the policies; the first one with an answer wins.
    decision = (p2_collections_during_hardship(req, case, at)
                or p4_credit_offer_to_high_risk(req, score)
                or p3_verify_caller(req, contacts))
    if decision is None:
        decision = Decision(customer_token=req.customer_token, action=req.action,
                            decision=DecisionResult.ALLOW, reason="No policy blocks this action")

    # 3. Record it, so the ledger shows what was asked and what was decided.
    if record:
        entry_type = EntryType.BLOCKED if decision.decision == DecisionResult.BLOCK.value else EntryType.ACTION
        store.append(entry_type, req.customer_token, decision.model_dump(mode="json"), db_path=db_path)

    return decision
