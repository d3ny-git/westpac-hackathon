"""Node D: the Policy Agent (D-1 gatekeeper, D-2 caller check, D-3 deadline watcher, D-4 recommendations,
D-5 explain).

D has two jobs:
  1. Gatekeeper, check_action(): before the bank does something to a customer (sends a default
     notice, offers a credit card, trusts someone who says they're calling from Westpac), it asks
     D first. D looks the customer up in the ledger and answers ALLOW or BLOCK, with the policy and
     a plain-English reason. Every answer is written back to the ledger.
  2. Watcher, check_deadlines(): looks through every open promise and flags the ones that are
     about to be missed (ALERT) or already were (ESCALATE).
  3. Recommender, recommend(): turns what the ledger shows into suggestions (Quiet Help push,
     book a meeting, escalate). Nothing happens until a PERSON approves one in Node E.
  4. Explainer, explain(entry_id): gathers the facts behind a recorded decision or recommendation,
     so a person (or the AI, via shared.llm.explain) can say WHY in plain English.

MCP tools (D-6, see register() at the bottom): policy_check_action, policy_deadlines,
policy_recommend, policy_explain.

The rules are plain Python, not AI: the same ledger and the same request always give the same answer.

Policies:
    P1  promise due within 24 hours -> ALERT, already overdue -> ESCALATE  (D-3)
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
from typing import Any, Optional

from pydantic import BaseModel

from nodes.ledger import store
from nodes.ledger.quiet_help import (CombinedScore, combine, combined_score, open_hardship_case, open_promises,
                                     quiet_help_candidates, tracked_recommendations)
from shared.config import (QUIET_HELP_COOLDOWN, COLLECTIONS_ACTIONS, CREDIT_OFFER_ACTIONS, HARDSHIP_RESPONSE_DAYS, HIGH_OR_ABOVE,
                           P1_ALERT_WINDOW, RECOMMENDATION_COOLDOWN, ActionType, DeadlineLevel, DecisionResult,
                           EntryType, PolicyId, PromiseType, RecommendationType, band, now)
from shared.pii_guard import safe_tool
from shared.schemas import (ActionRequest, Actor, ContactScheduled, CustomerToken, DeadlineAlert, Decision,
                            EntryId, LedgerEntry, Promise, Recommendation)

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


# ---------------------------------------------------------------------------
# P1: the deadline watcher (D-3)
# ---------------------------------------------------------------------------
_PROMISE_LABELS = {"CALLBACK": "Callback", "MEETING": "Meeting", "EMAIL": "Email reply",
                   "DECISION": "Decision", "HARDSHIP_RESPONSE": "Hardship response"}


def _hours_text(hours: float) -> str:
    """Rough, readable time: 'less than an hour', '5 hours', '2 days'."""
    if hours < 1:
        return "less than an hour"
    if hours < 48:
        whole = int(hours)
        return "1 hour" if whole == 1 else f"{whole} hours"
    return _days(int(hours // 24))


def p1_deadline(promise: Promise, at: datetime) -> Optional[DeadlineAlert]:
    """P1 for one open promise: ESCALATE if it's overdue, ALERT if it's due within 24 hours,
    otherwise None. Pure function: pass in the promise and the time to check it at."""
    hours = (promise.due - at).total_seconds() / 3600
    label = _PROMISE_LABELS.get(promise.promise_type, promise.promise_type.title())
    when = f"{promise.due:%d %b %H:%M}"

    if hours < 0:
        level = DeadlineLevel.ESCALATE
        reason = f"{label} was due {_hours_text(-hours)} ago ({when}) and hasn't been done"
    elif hours <= P1_ALERT_WINDOW.total_seconds() / 3600:
        level = DeadlineLevel.ALERT
        reason = f"{label} is due in {_hours_text(hours)} ({when})"
    else:
        return None

    return DeadlineAlert(customer_token=promise.customer_token, promise_id=promise.promise_id,
                         promise_type=promise.promise_type, due=promise.due, level=level,
                         hours_to_due=round(hours, 1), reason=reason)


def check_deadlines(*, db_path: DbPath = None) -> list[DeadlineAlert]:
    """P1 across the whole ledger: every open promise that's overdue or due within 24 hours.

    Escalations come first (most overdue first), then alerts (soonest first).
    This only READS the ledger: running it twice gives the same list and writes nothing.
    D-4 turns escalations into ESCALATE recommendations, which is what gets recorded.
    """
    at = now()
    alerts = [a for t in open_promises(db_path=db_path) if (a := p1_deadline(t.promise, at))]
    alerts.sort(key=lambda a: (a.level != DeadlineLevel.ESCALATE.value, a.hours_to_due, a.promise_id))
    return alerts


# ---------------------------------------------------------------------------
# Recommendations (D-4)
# ---------------------------------------------------------------------------
# Statuses that mean "this recommendation is still in play", so D must not suggest it again.
_STILL_OPEN = {"AWAITING_APPROVAL", "APPROVED"}


def _already_recommended(token: str, kind: str, history, at: datetime) -> bool:
    """True if D already suggested `kind` for this customer and shouldn't again:
    it's still waiting / approved, or it was made (and then done or rejected) within the last 30 days."""
    for t in history:
        r = t.recommendation
        if r.customer_token != token or r.recommendation != kind:
            continue
        if t.current_status in _STILL_OPEN or t.recorded_at > at - RECOMMENDATION_COOLDOWN:
            return True
    return False


def recommend(*, db_path: DbPath = None) -> list[Recommendation]:
    """Turn what the ledger shows into NEW recommendations, record them, and return them.

    The rules (plain Python, in this order):
      ESCALATE         a promise to the customer is overdue (P1)
      BOOK_MEETING     the customer has an open hardship case but no meeting booked
      QUIET_HELP_PUSH  the customer is on the Quiet Help list (C-6)

    No repeats: D skips a recommendation if the same one for the same customer is still awaiting
    approval / approved, or was made in the last 30 days (so a rejection isn't re-suggested the
    next day). Running it twice in a row therefore creates nothing the second time.

    Each new recommendation is written to the ledger as AWAITING_APPROVAL. Nothing is sent to a
    customer until a person approves it in Node E.
    """
    at = now()
    history = tracked_recommendations(db_path=db_path)
    wanted: list[tuple[str, str, list[str]]] = []          # (customer, recommendation, why)

    # 1. ESCALATE: overdue promises (one recommendation per customer, listing what's overdue).
    overdue: dict[str, list[str]] = {}
    for alert in check_deadlines(db_path=db_path):
        if alert.level == DeadlineLevel.ESCALATE.value:
            overdue.setdefault(alert.customer_token, []).append(f"{alert.promise_type}_OVERDUE")
    for token, whys in overdue.items():
        wanted.append((token, RecommendationType.ESCALATE.value, ["P1_PROMISE_MISSED", *dict.fromkeys(whys)]))

    # 2. BOOK_MEETING: open hardship case, but no meeting promise yet.
    open_now = open_promises(db_path=db_path)
    has_meeting = {t.promise.customer_token for t in open_now if t.promise.promise_type == PromiseType.MEETING.value}
    cases = sorted({t.promise.customer_token for t in open_now
                    if t.promise.promise_type == PromiseType.HARDSHIP_RESPONSE.value} - has_meeting)
    for token in cases:
        wanted.append((token, RecommendationType.BOOK_MEETING.value, ["HARDSHIP_CASE_OPEN", "NO_MEETING_BOOKED"]))

    # 3. QUIET_HELP_PUSH: the Quiet Help list (already sorted, highest score first).
    for c in quiet_help_candidates(db_path=db_path):
        wanted.append((c.customer_token, RecommendationType.QUIET_HELP_PUSH.value,
                       [f"SCORE_{c.band}", *c.reasons]))

    # 4. Record the ones that aren't repeats.
    created: list[Recommendation] = []
    for token, kind, why in wanted:
        if _already_recommended(token, kind, history, at):
            continue
        rec = Recommendation(rec_id=store.next_id("R", db_path=db_path), customer_token=token,
                             recommendation=kind, why=why)
        store.append(EntryType.RECOMMENDATION, token, rec.model_dump(mode="json"), db_path=db_path)
        created.append(rec)
    return created


# ---------------------------------------------------------------------------
# Explain (D-5)
# ---------------------------------------------------------------------------
class PolicyError(ValueError):
    """D was asked something it can't answer (e.g. to explain an entry that isn't a decision)."""


# The rules in fixed words. The AI may rephrase these; it never decides what they say.
POLICY_RULES = {
    "P1": "A promise that is overdue is escalated; one due within 24 hours raises an alert.",
    "P2": "No collections or default notice may be sent while the customer has an open hardship case.",
    "P3": "A caller claiming to be from Westpac is only genuine if they quote the call code of a call "
          "Westpac booked for this customer; otherwise treat it as a possible scam.",
    "P4": "No credit card, loan or limit-increase offers to customers whose hardship score is HIGH or CRITICAL.",
}
RECOMMENDATION_RULES = {
    "ESCALATE": "A promise to the customer is overdue, so a team lead should step in.",
    "BOOK_MEETING": "The customer has an open hardship case but no meeting booked, so book a call with a specialist.",
    "QUIET_HELP_PUSH": "The customer's hardship score is HIGH or CRITICAL, they have no open hardship case and no "
                       "Quiet Help message in the last 30 days, so offer help privately in the app.",
}
_HIDDEN = "(hidden)"


class Explanation(BaseModel):
    """The facts behind one decision or recommendation, as they were WHEN it was made."""
    entry_id: str
    entry_type: str                    # BLOCKED, ACTION or RECOMMENDATION
    customer_token: str
    recorded_at: str
    outcome: dict[str, Any]            # the decision / recommendation itself
    rule: str                          # the policy or recommendation rule, in fixed words
    facts: dict[str, Any]              # combined score, open case, overdue promises... at that moment
    evidence: list[dict[str, Any]]     # the ledger entries the decision relied on (call codes hidden)


def _hide_codes(data: dict[str, Any]) -> dict[str, Any]:
    """Call codes are secrets: they must never reach the AI or a screen through an explanation."""
    return {k: (_HIDDEN if k == "call_code" else v) for k, v in data.items()}


def _as_evidence(e: LedgerEntry) -> dict[str, Any]:
    return {"entry_id": e.entry_id, "entry_type": e.entry_type,
            "recorded_at": e.created_at.isoformat(), "data": _hide_codes(e.data)}


def _facts_before(prior: list[LedgerEntry], at: datetime) -> tuple[dict[str, Any], dict[str, list[LedgerEntry]]]:
    """Work out the customer's situation from the entries that existed at the time.

    Returns (facts, groups) where groups holds the entries behind each fact, so the right ones
    can be shown as evidence."""
    scores: dict[str, LedgerEntry] = {}
    promises: dict[str, LedgerEntry] = {}
    status: dict[str, str] = {}
    contacts: list[LedgerEntry] = []
    pushes: list[LedgerEntry] = []
    for e in prior:
        d = e.data
        if e.entry_type == "SCORE":
            scores[d["source"]] = e                                    # latest per source wins
        elif e.entry_type == "PROMISE":
            promises[d["promise_id"]], status[d["promise_id"]] = e, d["status"]
        elif e.entry_type == "STATUS_UPDATE" and d["ref_id"] in promises:
            status[d["ref_id"]] = d["status"]
        elif e.entry_type == "CONTACT_SCHEDULED":
            contacts.append(e)
        elif e.entry_type == "ACTION" and d.get("action") == "QUIET_HELP_PUSH" and "message_id" in d:
            pushes.append(e)

    a = scores["ACCOUNT"].data["score"] if "ACCOUNT" in scores else None
    b = scores["INTERACTION"].data["score"] if "INTERACTION" in scores else None
    open_p = [e for pid, e in promises.items() if status[pid] == "OPEN"]
    cases = [e for e in open_p if e.data["promise_type"] == "HARDSHIP_RESPONSE"]
    meetings = [e for e in open_p if e.data["promise_type"] == "MEETING"]
    overdue = [e for e in open_p if datetime.fromisoformat(e.data["due"]) < at]
    combined = combine(a, b) if scores else None

    facts = {
        "combined_score": combined,
        "band": band(combined).value if combined is not None else None,
        "account_score": a,
        "interaction_score": b,
        "open_hardship_case": ({"promise_id": cases[-1].data["promise_id"], "due": cases[-1].data["due"]}
                               if cases else None),
        "meeting_booked": bool(meetings),
        "overdue_promises": [{"promise_id": e.data["promise_id"], "promise_type": e.data["promise_type"],
                              "due": e.data["due"]} for e in overdue],
        "calls_booked": len(contacts),                                 # how many, never the codes
        "last_quiet_help_push": pushes[-1].created_at.isoformat() if pushes else None,
        "quiet_help_push_in_last_30_days": bool(pushes and pushes[-1].created_at > at - QUIET_HELP_COOLDOWN),
    }
    groups = {"scores": list(scores.values()), "cases": cases, "meetings": meetings,
              "overdue": overdue, "contacts": contacts, "pushes": pushes[-1:]}
    return facts, groups


def explain(entry_id: str, *, db_path: DbPath = None) -> Explanation:
    """The facts behind a recorded decision (BLOCKED / ACTION from check_action) or a RECOMMENDATION.

    Only entries that existed when it was made are used, so an old decision is explained by what
    was known then. Call codes are always hidden. Pass the result to shared.llm.explain() to get
    a plain-English sentence; the AI only rephrases these facts.
    """
    entry = store.get(entry_id, db_path=db_path)
    if entry is None:
        raise PolicyError(f"{entry_id} isn't in the ledger")
    is_decision = entry.entry_type in ("BLOCKED", "ACTION") and "decision" in entry.data
    if not (is_decision or entry.entry_type == "RECOMMENDATION"):
        raise PolicyError(f"{entry_id} is a {entry.entry_type} entry; only D's decisions and "
                          f"recommendations can be explained")

    history = store.read(customer_token=entry.customer_token, db_path=db_path)
    prior = [e for e in history if int(e.entry_id[2:]) < int(entry_id[2:])]    # strictly before it
    facts, groups = _facts_before(prior, entry.created_at)
    d = entry.data

    if is_decision:
        action, policy = d["action"], d.get("policy")
        if policy:
            rule = POLICY_RULES[policy]
        elif action == ActionType.VERIFY_CALLER.value:
            rule = POLICY_RULES["P3"]                                  # an ALLOWED caller passed P3
        else:
            rule = "No policy blocks this action."
        if action in _COLLECTIONS:
            evidence = groups["cases"]
        elif action in _CREDIT_OFFERS:
            evidence = groups["scores"]
        elif action == ActionType.VERIFY_CALLER.value:
            evidence = groups["contacts"]
        else:
            evidence = groups["scores"] + groups["cases"]
    else:
        kind = d["recommendation"]
        rule = RECOMMENDATION_RULES[kind]
        evidence = {"ESCALATE": groups["overdue"],
                    "BOOK_MEETING": groups["cases"] + groups["meetings"],
                    "QUIET_HELP_PUSH": groups["scores"] + groups["cases"] + groups["pushes"]}[kind]

    return Explanation(entry_id=entry.entry_id, entry_type=entry.entry_type,
                       customer_token=entry.customer_token, recorded_at=entry.created_at.isoformat(),
                       outcome=_hide_codes(d), rule=rule, facts=facts,
                       evidence=[_as_evidence(e) for e in sorted(evidence, key=lambda e: e.entry_id)])


def explain_in_words(entry_id: str, *, db_path: DbPath = None) -> str:
    """explain() + the AI: a short plain-English explanation for a bank staff member.

    The AI only rephrases the facts from explain(); it can't change the decision. Needs the
    OpenRouter key in .env. Used by the D page's "Explain" button.
    """
    from shared.llm import explain as llm_explain       # imported here so the policies never need the AI
    facts = explain(entry_id, db_path=db_path).model_dump()
    return llm_explain(facts, "Explain to a bank staff member why this decision or recommendation was made.")


# ---------------------------------------------------------------------------
# MCP tools (D-6): what the AI is allowed to ask Node D
# ---------------------------------------------------------------------------
def register(mcp) -> None:
    """Called once by server.py to add Node D's tools to the MCP server.

    None of these tools can approve or carry out anything. Recommendations wait for a person in
    Node E, and decisions only say ALLOW or BLOCK.
    """

    @mcp.tool()
    @safe_tool
    def policy_check_action(customer_token: CustomerToken, action: ActionType, requested_by: Actor,
                            call_code: Optional[str] = None) -> dict:
        """Ask whether an action is allowed for a customer, BEFORE anyone does it.

        Returns decision (ALLOW or BLOCK), policy (P2, P3 or P4 when blocked), a plain-English
        reason, and flags (e.g. POSSIBLE_SCAM). The decision is recorded in the ledger.
        Policies: P2 no collections/default notice during an open hardship case; P3 a caller
        claiming to be Westpac must quote the booked call code (pass it as call_code with
        action VERIFY_CALLER); P4 no credit offers to HIGH or CRITICAL customers.
        requested_by is the staff token asking (e.g. staff_44a) or SYSTEM.
        """
        return check_action({"customer_token": customer_token, "action": action,
                             "requested_by": requested_by, "call_code": call_code})

    @mcp.tool()
    @safe_tool
    def policy_deadlines() -> list[dict]:
        """Policy P1: every open promise that is overdue (ESCALATE) or due within 24 hours (ALERT).

        Each item has customer_token, promise_id, promise_type, due, level, hours_to_due
        (negative = overdue) and a plain-English reason. Escalations first. Read-only.
        """
        return check_deadlines()

    @mcp.tool()
    @safe_tool
    def policy_recommend() -> list[dict]:
        """Create NEW recommendations from the ledger and return them (an empty list if there's nothing new).

        ESCALATE for overdue promises, BOOK_MEETING for an open hardship case with no meeting,
        QUIET_HELP_PUSH for customers on the Quiet Help list. Each is recorded as
        AWAITING_APPROVAL: nothing happens until a PERSON approves it. Never repeats a
        recommendation that is still waiting or was made in the last 30 days.
        """
        return recommend()

    @mcp.tool()
    @safe_tool
    def policy_explain(entry_id: EntryId) -> dict:
        """The facts behind one recorded decision or recommendation, e.g. entry_id "E-0041".

        Returns the outcome, the rule in fixed words, the customer's situation at that moment
        (scores, open hardship case, overdue promises...) and the ledger entries it relied on.
        Use these facts to explain the decision; don't add anything that isn't in them.
        Call codes are always hidden.
        """
        return explain(entry_id)
