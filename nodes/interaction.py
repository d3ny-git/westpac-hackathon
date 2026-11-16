"""Node B: Interactions. Scores customers from their contacts with the bank, and works out
what the bank promised them (AB-3).

    mock input form / history CSV (PII)  ->  sanitize.py  ->  data/clean/interactions.csv  ->  THIS FILE  ->  ledger

This file only ever reads the CLEAN interactions file (tokens + keyword flags; the free text
was already deleted by sanitize.py). It never sees raw data.

Plain Python, no AI:
    score_customer(token)        the INTERACTION ScoreMessage (rules below)
    customer_promises(token)     the promises the rules produce, with their ledger ID if published
    publish(token=None)          write SCORE + new PROMISE entries to the ledger (one customer, or everyone)
    RULES                        the rule table

MCP tools (register() at the bottom): interaction_score, interaction_promises,
interaction_publish, interaction_rules.

Rules (exact definitions in mock_input_output/README.md), counted back from config.now():
    submitted HARDSHIP_FORM in the last 30 days    +40  HARDSHIP_FORM
    any keyword flag in the last 30 days           +25  HARDSHIP_KEYWORDS
    3+ interactions in the last 14 days            +10  REPEAT_CONTACT
    ABANDONED hardship form in the last 30 days    +15  ABANDONED_FORM
    capped at 100

Promises (fixed templates, never customer text):
    submitted HARDSHIP_FORM  ->  HARDSHIP_RESPONSE due 17:00 on the form date + 21 days, made by SYSTEM
    CALLBACK_REQUEST         ->  CALLBACK due at the requested callback time, made by the staff member
"""
from __future__ import annotations

import csv
from datetime import date, datetime, time, timedelta
from typing import Any, Optional

from nodes.ledger import store
from nodes.ledger.store import LedgerError
from shared.config import (CLEAN_INTERACTIONS_FILE, HARDSHIP_RESPONSE_DAYS, SYSTEM_ACTOR, band,
                           clean_dir, now)
from shared.pii_guard import KEYWORD_FLAGS, safe_tool
from shared.schemas import CleanInteraction, CustomerToken, Promise, ScoreMessage

# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------
RULES = [
    {"code": "HARDSHIP_FORM", "points": 40, "rule": "A hardship form was SUBMITTED in the last 30 days"},
    {"code": "HARDSHIP_KEYWORDS", "points": 25,
     "rule": "The customer used hardship words (e.g. 'lost my job', 'can't afford') in the last 30 days"},
    {"code": "REPEAT_CONTACT", "points": 10, "rule": "3 or more contacts with the bank in the last 14 days"},
    {"code": "ABANDONED_FORM", "points": 15, "rule": "A hardship form was started but ABANDONED in the last 30 days"},
]
SCORE_CAP = 100
FORM_WINDOW_DAYS = 30           # forms and keywords count if they're at most 30 days old
CONTACT_WINDOW_DAYS = 14        # contacts count if they're at most 14 days old
REPEAT_CONTACTS = 3

HARDSHIP_RESPONSE_HOUR = 17     # a hardship response is due at 5pm, 21 days after the form
HARDSHIP_RESPONSE_DESCRIPTION = f"Respond to hardship request within {HARDSHIP_RESPONSE_DAYS} days"
CALLBACK_DESCRIPTION = "Hardship team to call back"


# ---------------------------------------------------------------------------
# Reading the clean data
# ---------------------------------------------------------------------------
def load_interactions() -> list[CleanInteraction]:
    """Every row of data/clean/interactions.csv, in file order (date, then customer).

    Each row is checked against the shared CleanInteraction model (tokens, enums, dates)."""
    path = clean_dir() / CLEAN_INTERACTIONS_FILE
    if not path.is_file():
        raise LedgerError(f"no clean interactions file at {path}: run `python sanitize.py` first")
    with open(path, newline="", encoding="utf-8") as f:
        return [CleanInteraction(**row) for row in csv.DictReader(f)]


def customer_interactions(customer_token: str, rows: Optional[list[CleanInteraction]] = None) -> list[CleanInteraction]:
    """One customer's interactions. Raises LedgerError if they have none in the clean data."""
    rows = load_interactions() if rows is None else rows
    mine = [r for r in rows if r.customer_token == customer_token]
    if not mine:
        raise LedgerError(f"{customer_token} has no interactions in the clean data")
    return mine


# ---------------------------------------------------------------------------
# Scoring (pure: rows + a date in, score + reasons out)
# ---------------------------------------------------------------------------
def score_interactions(rows: list[CleanInteraction], as_of: date) -> tuple[int, list[str]]:
    """The B rules on one customer's interactions. Returns (score, reason codes)."""
    def within(row: CleanInteraction, days: int) -> bool:
        return 0 <= (as_of - row.date).days <= days

    recent = [r for r in rows if within(r, FORM_WINDOW_DAYS)]
    score, reasons = 0, []
    if any(r.type == "HARDSHIP_FORM" and r.form_status == "SUBMITTED" for r in recent):
        score += 40
        reasons.append("HARDSHIP_FORM")
    if any(r.flags for r in recent):
        score += 25
        reasons.append("HARDSHIP_KEYWORDS")
    if sum(1 for r in rows if within(r, CONTACT_WINDOW_DAYS)) >= REPEAT_CONTACTS:
        score += 10
        reasons.append("REPEAT_CONTACT")
    if any(r.type == "HARDSHIP_FORM" and r.form_status == "ABANDONED" for r in recent):
        score += 15
        reasons.append("ABANDONED_FORM")
    return min(score, SCORE_CAP), reasons


def score_customer(customer_token: str, rows: Optional[list[CleanInteraction]] = None) -> ScoreMessage:
    """The customer's INTERACTION score message, as of config.now()."""
    at = now()
    score, reasons = score_interactions(customer_interactions(customer_token, rows), at.date())
    return ScoreMessage(customer_token=customer_token, source="INTERACTION", score=score,
                        band=band(score).value, reasons=reasons, timestamp=at)


# ---------------------------------------------------------------------------
# Promises
# ---------------------------------------------------------------------------
def promise_drafts(rows: list[CleanInteraction]) -> list[dict[str, Any]]:
    """The promises the rules produce from these interactions, in row order, WITHOUT an ID.

    A CALLBACK_REQUEST with no callback time can't become a promise (there's nothing to be due),
    so it's skipped.
    """
    drafts = []
    for r in rows:
        if r.type == "HARDSHIP_FORM" and r.form_status == "SUBMITTED":
            due = datetime.combine(r.date, time(HARDSHIP_RESPONSE_HOUR)) + timedelta(days=HARDSHIP_RESPONSE_DAYS)
            drafts.append({"customer_token": r.customer_token, "promise_type": "HARDSHIP_RESPONSE",
                           "description": HARDSHIP_RESPONSE_DESCRIPTION, "made_by": SYSTEM_ACTOR,
                           "made_via": r.channel, "due": due, "status": "OPEN"})
        elif r.type == "CALLBACK_REQUEST" and r.callback_due is not None:
            drafts.append({"customer_token": r.customer_token, "promise_type": "CALLBACK",
                           "description": CALLBACK_DESCRIPTION, "made_by": r.staff_token or SYSTEM_ACTOR,
                           "made_via": r.channel, "due": r.callback_due, "status": "OPEN"})
    return drafts


def _promise_key(customer_token: str, promise_type: str, due: datetime | str) -> tuple[str, str, str]:
    """What makes a promise 'the same promise': customer + type + due time."""
    due_text = due.isoformat() if isinstance(due, datetime) else str(due)
    return customer_token, promise_type, due_text


def _published_promises(customer_token: Optional[str] = None) -> dict[tuple[str, str, str], str]:
    """Promises already in the ledger: {(customer, type, due): promise_id}."""
    return {_promise_key(e.customer_token, e.data["promise_type"], e.data["due"]): e.data["promise_id"]
            for e in store.read(customer_token=customer_token, entry_type="PROMISE")}


def customer_promises(customer_token: str) -> list[dict[str, Any]]:
    """The promises the rules produce for one customer, each with `promise_id` = its ledger ID if
    it's already been published, else None. Read-only: writes nothing, uses up no IDs."""
    published = _published_promises(customer_token)
    result = []
    for d in promise_drafts(customer_interactions(customer_token)):
        key = _promise_key(d["customer_token"], d["promise_type"], d["due"])
        result.append({"promise_id": published.get(key), **d, "due": key[2]})
    return result


# ---------------------------------------------------------------------------
# Publishing to the ledger (idempotent: running it twice writes nothing new)
# ---------------------------------------------------------------------------
def _latest_interaction_score(customer_token: str) -> Optional[dict[str, Any]]:
    scores = [e.data for e in store.read(customer_token=customer_token, entry_type="SCORE")
              if e.data["source"] == "INTERACTION"]
    return scores[-1] if scores else None


def publish(customer_token: Optional[str] = None) -> dict[str, Any]:
    """Write SCORE and new PROMISE entries for one customer, or for everyone in the clean data.

    - A SCORE is skipped if the customer's latest INTERACTION score already says the same thing
      (same score, band and reasons).
    - A PROMISE is skipped if the same promise (customer + type + due) is already in the ledger.
    - New promises get IDs from store.next_id("P"), in clean-file order.
    Returns a summary of what was written and skipped.
    """
    rows = load_interactions()
    if customer_token is not None:
        rows = customer_interactions(customer_token, rows)
    tokens = sorted({r.customer_token for r in rows})

    summary: dict[str, Any] = {"scores_written": [], "scores_skipped": [],
                               "promises_written": [], "promises_skipped": []}

    # 1. Scores, one per customer.
    for token in tokens:
        msg = score_customer(token, rows)
        latest = _latest_interaction_score(token)
        if latest and (latest["score"], latest["band"], latest["reasons"]) == (msg.score, msg.band, msg.reasons):
            summary["scores_skipped"].append(token)
            continue
        store.append("SCORE", token, msg.model_dump(mode="json"))
        summary["scores_written"].append(token)

    # 2. Promises, in clean-file order (so IDs are handed out in date order).
    published = _published_promises(customer_token)
    for d in promise_drafts(rows):
        key = _promise_key(d["customer_token"], d["promise_type"], d["due"])
        if key in published:
            summary["promises_skipped"].append(published[key])
            continue
        promise = Promise(promise_id=store.next_id("P"), **d)
        store.append("PROMISE", promise.customer_token, promise.model_dump(mode="json"))
        published[key] = promise.promise_id
        summary["promises_written"].append(promise.promise_id)
    return summary


def rules() -> dict[str, Any]:
    """The B rule table and the keyword phrases behind HARDSHIP_KEYWORDS."""
    return {"rules": RULES, "cap": SCORE_CAP, "keyword_flags": KEYWORD_FLAGS,
            "windows_days": {"forms_and_keywords": FORM_WINDOW_DAYS, "contacts": CONTACT_WINDOW_DAYS},
            "promises": [
                {"when": "a hardship form is SUBMITTED", "promise_type": "HARDSHIP_RESPONSE",
                 "due": f"{HARDSHIP_RESPONSE_HOUR}:00 on the form date + {HARDSHIP_RESPONSE_DAYS} days"},
                {"when": "a callback is requested", "promise_type": "CALLBACK", "due": "the requested callback time"},
            ]}


# ---------------------------------------------------------------------------
# MCP tools (what the AI is allowed to ask Node B)
# ---------------------------------------------------------------------------
def register(mcp) -> None:
    """Called once by server.py to add Node B's tools to the MCP server."""

    # The Python functions are named tool_* so they don't hide the real functions above
    # (a function calling a function with its own name would call itself forever).

    @mcp.tool(name="interaction_score")
    @safe_tool
    def tool_score(customer_token: CustomerToken) -> dict:
        """A customer's hardship score from their contacts with the bank (Node B), 0-100.

        Returns customer_token, source (INTERACTION), score, band (LOW / MODERATE / HIGH /
        CRITICAL), reasons (rule codes such as HARDSHIP_FORM, REPEAT_CONTACT) and timestamp.
        """
        return score_customer(customer_token)

    @mcp.tool(name="interaction_promises")
    @safe_tool
    def tool_promises(customer_token: CustomerToken) -> list[dict]:
        """What the bank has promised a customer, worked out from their contacts.

        Each promise has promise_type (HARDSHIP_RESPONSE or CALLBACK), due, made_by, made_via and
        promise_id (the ledger ID, or null if it hasn't been published yet). Read-only.
        """
        return customer_promises(customer_token)

    @mcp.tool(name="interaction_publish")
    @safe_tool
    def tool_publish(customer_token: Optional[CustomerToken] = None) -> dict:
        """Write Node B's scores and new promises to the ledger, for one customer or (with no
        customer_token) for everyone. Never writes the same score or promise twice.

        Returns scores_written, scores_skipped, promises_written (new promise IDs) and promises_skipped.
        """
        return publish(customer_token)

    @mcp.tool(name="interaction_rules")
    @safe_tool
    def tool_rules() -> dict:
        """Node B's scoring rules, the hardship keyword phrases, and how promises are made."""
        return rules()
