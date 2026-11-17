"""The customer app's API (/customer): what a Westpac customer sees in their app.

    sign-in options     the (fake) customers to sign in as (demo: no passwords)
    overview            their OWN accounts and recent transactions (raw rows of that customer only)
    messages            actions_inbox(token): Quiet Help offers, booked calls with the call code,
                        each with seen (opened in the app) and answered (the customer acted on it)
    messages/seen       the app marks the messages it has shown as seen (clears the unread badge)
    promises            what the bank has promised them, in plain words
    hardship / callback the customer contacts the bank: sanitized + stored straight away, then the
                        intake review runs (api/live.py: Node B + the AI hardship assessment)
    verify-call         "Is this call really Westpac?": check_action(VERIFY_CALLER), requested_by SYSTEM

The customer never sees scores, bands, flags, tokens or policy names: the token is worked out on the
server from the signed-in customer ID (tokenise) and never returned.

PII: the sign-in list and the overview show the customer's OWN name and transactions (personal
data, shown only to that customer); they're on the RAW_VIEWS allow-list as customer-only views.
Everything else is PII-checked. What the customer types is sanitized before it's stored: only the
clean row is written, and the AI only ever sees the sanitized results.
"""
from __future__ import annotations

import re
import sqlite3
from collections import OrderedDict
from contextlib import closing
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import sanitize
from api.common import RUN_LOCK
from api.integrity import ledger_problem
from api.interaction import fake_customers
from api.live import worker
from nodes.actions import actions_inbox
from nodes.ledger import store
from nodes.ledger.quiet_help import open_promises
from nodes.policy import check_action
from shared.config import CLEAN_INTERACTIONS_FILE, HASH_PATTERN, SYSTEM_ACTOR, clean_dir, now
from shared.pii_guard import tokenise

router = APIRouter(prefix="/api/customer", tags=["customer"])

RECENT_TRANSACTIONS = 12
ACCOUNT_NAMES = {"TRANSACTION": "Everyday account", "CREDIT_CARD": "Credit card", "HOME_LOAN": "Home loan"}
PROMISE_WORDS = {
    "HARDSHIP_RESPONSE": "We'll respond to your hardship request by {when}",
    "CALLBACK": "We'll call you back on {when}",
    "MEETING": "A hardship specialist will call you on {when}",
    "EMAIL": "We'll reply to your email by {when}",
    "DECISION": "We'll give you a decision by {when}",
}


class HardshipForm(BaseModel):
    customer_id: str
    text: str = Field(default="", max_length=2000)    # in their own words (sanitized before it's stored)


class CallbackRequest(BaseModel):
    customer_id: str
    day: str                                            # YYYY-MM-DD
    time: str = "14:00"                                 # HH:MM
    text: str = Field(default="", max_length=2000)


class SeenMessages(BaseModel):
    customer_id: str
    ids: list[str] = Field(default_factory=list, max_length=50)


class CallCheck(BaseModel):
    customer_id: str
    code: str = Field(default="", max_length=12)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _customer(customer_id: str) -> dict[str, str]:
    people = fake_customers()
    if customer_id not in people:
        raise HTTPException(404, "Unknown customer: sign in again.")
    return people[customer_id]


def _token(customer_id: str) -> str:
    _customer(customer_id)
    return tokenise(customer_id)


def _nice(when: datetime) -> str:
    """'Tue 1 Dec, 5:00 pm' (no time zone: the demo's fixed clock)."""
    hour = when.strftime("%I").lstrip("0") or "12"
    return f"{when:%a} {when.day} {when:%b}, {hour}:{when:%M} {when:%p}".replace("AM", "am").replace("PM", "pm")


# ---- messages: seen and answered -------------------------------------------------
# A message's id is the hash of the ledger entry that sent it (no customer token, no entry ID).
# "Seen" is app state, not a ledger fact, so it lives in its own small table in the same SQLite
# file, OUTSIDE the hash chain: the ledger's entries table is never touched. Keeping it in that
# file means a demo reset (which deletes the file) also forgets what was seen, even though the
# rebuilt ledger repeats the same hashes.
SEEN_TABLE = "app_message_seen"
_HASH = re.compile(HASH_PATTERN)
ANSWERS = {"HARDSHIP_RESPONSE", "CALLBACK"}       # a later hardship form or callback request answers an offer


def _seen_db() -> sqlite3.Connection:
    conn = sqlite3.connect(store.db_file(), isolation_level=None, timeout=10)
    conn.execute(f"CREATE TABLE IF NOT EXISTS {SEEN_TABLE} (message_hash TEXT PRIMARY KEY, seen_at TEXT NOT NULL)")
    return conn


def _seen_hashes(hashes: list[str]) -> set[str]:
    if not hashes or not store.db_file().exists():
        return set()
    with closing(_seen_db()) as conn:
        marks = ",".join("?" * len(hashes))
        return {r[0] for r in conn.execute(f"SELECT message_hash FROM {SEEN_TABLE} WHERE message_hash IN ({marks})",
                                           hashes)}


def _message_entries(token: str) -> tuple[list, list]:
    """The ledger entries behind actions_inbox(token) (same filter, same order), and the
    customer's whole history (to tell whether an offer has been answered)."""
    history = store.read(customer_token=token)
    sent = [e for e in history if e.entry_type == "ACTION" and (
        (e.data.get("action") == "QUIET_HELP_PUSH" and "message_id" in e.data)
        or (e.data.get("action") == "BOOK_MEETING" and "call_code" in e.data))]
    return sent, history


def _answered_on(entry, history: list) -> str | None:
    """A Quiet Help offer is answered once the customer asks for help after it (a hardship form or
    callback request becomes a PROMISE) or a call with a specialist is booked."""
    if entry.data.get("action") != "QUIET_HELP_PUSH":
        return None
    later = history[[e.entry_id for e in history].index(entry.entry_id) + 1:]
    for e in later:
        if (e.entry_type == "PROMISE" and e.data.get("promise_type") in ANSWERS) or \
                (e.entry_type == "ACTION" and e.data.get("action") == "BOOK_MEETING"):
            when = datetime.fromisoformat(str(e.created_at))
            return f"{when:%a} {when.day} {when:%b}"
    return None


def _contact(customer_id: str, **fields: str) -> dict[str, Any]:
    """Sanitize + store one contact from the app, then hand it to the intake review."""
    person = _customer(customer_id)
    if not (clean_dir() / CLEAN_INTERACTIONS_FILE).exists():
        raise HTTPException(503, "We can't take requests right now. Please try again later.")
    raw = {"customer_id": customer_id, **person, "staff_id": "", "staff_name": "",
           "date": now().date().isoformat(), "channel": "FORM", "form_status": "", "callback_due": "", **fields}
    with RUN_LOCK:
        clean = sanitize.add_interaction(raw)                # only the clean row is ever stored
    worker.submit(clean)
    return clean


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("/sign-in-options")
def sign_in_options() -> list[dict[str, str]]:
    """CUSTOMER-ONLY VIEW (fake PII): who you can sign in as in the demo."""
    return [{"customer_id": cid, "full_name": p["full_name"]} for cid, p in fake_customers().items()]


@router.get("/overview")
def overview(customer_id: str = Query()) -> dict[str, Any]:
    """CUSTOMER-ONLY VIEW: the signed-in customer's own accounts (latest balance) and recent
    transactions, from their own raw rows. Nobody else's data, and nothing Westpac worked out."""
    person = _customer(customer_id)
    raw_path = sanitize.RAW_DIR / sanitize.RAW_TRANSACTIONS
    rows = [r for r in sanitize.read_csv(raw_path) if r["customer_id"] == customer_id] if raw_path.exists() else []
    rows.sort(key=lambda r: r["date"])
    accounts: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    for r in rows:
        accounts[r["account_type"]] = {"account_type": r["account_type"],
                                       "name": ACCOUNT_NAMES.get(r["account_type"], r["account_type"].title()),
                                       "number": f"•••• {r.get('account_number', '')[-4:]}", "bsb": r.get("bsb", ""),
                                       "balance": float(r["balance_after"]), "as_of": r["date"]}
    recent = [{"date": r["date"], "account": ACCOUNT_NAMES.get(r["account_type"], r["account_type"]),
               "description": r.get("description") or r.get("merchant") or r["category"].title(),
               "amount": float(r["amount"]), "balance_after": float(r["balance_after"])}
              for r in reversed(rows[-RECENT_TRANSACTIONS:])]
    return {"first_name": person["full_name"].split()[0], "full_name": person["full_name"],
            "accounts": list(accounts.values()), "transactions": recent, "today": now().date().isoformat()}


@router.get("/messages")
def messages(customer_id: str = Query()) -> list[dict[str, Any]]:
    """The customer's in-app messages (actions_inbox), newest first. A booked call shows its call
    code: that's the customer's own code, the one place it's meant to be seen.

    Each message also says whether the app has shown it (seen) and whether the customer has acted
    on it (answered, with the day): the app badges unseen ones and tucks answered offers away."""
    token = _token(customer_id)
    inbox = actions_inbox(token)
    sent, history = _message_entries(token)
    if len(sent) != len(inbox):                          # can't happen: same filter as actions_inbox
        raise HTTPException(500, "Your messages couldn't be loaded. Please try again.")
    seen = _seen_hashes([e.hash for e in sent])
    result = []
    for n, (m, e) in enumerate(zip(inbox, sent), start=1):
        answered_on = _answered_on(e, history)
        result.append({k: v for k, v in m.items() if k != "message_id"}
                      | {"n": n, "id": e.hash, "seen": e.hash in seen,
                         "answered": answered_on is not None, "answered_on": answered_on})
    return list(reversed(result))


@router.post("/messages/seen")
def messages_seen(body: SeenMessages) -> dict[str, int]:
    """The app has shown these messages: they're no longer new (clears the unread badge).
    Only this customer's own messages can be marked."""
    sent, _ = _message_entries(_token(body.customer_id))
    mine = {e.hash for e in sent}
    ids = [i for i in dict.fromkeys(body.ids) if _HASH.match(i) and i in mine]
    when = now().isoformat(timespec="seconds")
    with closing(_seen_db()) as conn:                   # a tiny write: no need to wait for a running sweep
        conn.executemany(f"INSERT OR IGNORE INTO {SEEN_TABLE} (message_hash, seen_at) VALUES (?, ?)",
                         [(i, when) for i in ids])
    return {"marked": len(ids)}


@router.get("/promises")
def promises(customer_id: str = Query()) -> list[dict[str, Any]]:
    """What the bank has promised this customer and hasn't done yet, in plain words."""
    result = []
    for t in sorted(open_promises(_token(customer_id)), key=lambda t: t.promise.due):
        p = t.promise
        words = PROMISE_WORDS.get(p.promise_type, "We'll get back to you by {when}")
        result.append({"kind": p.promise_type, "text": words.format(when=_nice(p.due)), "due": p.due.isoformat()})
    return result


@router.post("/hardship")
def hardship(body: HardshipForm) -> dict[str, Any]:
    """The hardship form (self-service). Received straight away; the review follows."""
    _contact(body.customer_id, type="HARDSHIP_FORM", form_status="SUBMITTED", text=body.text)
    due = datetime.combine(now().date() + timedelta(days=21), datetime.min.time()).replace(hour=17)
    return {"received": True, "message": "Thanks, we've received your hardship request. "
                                         f"We'll respond by {_nice(due)}, and you won't be charged "
                                         "late fees while we look at it."}


@router.post("/callback")
def callback(body: CallbackRequest) -> dict[str, Any]:
    """Request a call back at a day and time."""
    try:
        when = datetime.fromisoformat(f"{body.day}T{body.time}")
    except ValueError:
        raise HTTPException(422, "day / time: use YYYY-MM-DD and HH:MM") from None
    if when < now():
        raise HTTPException(422, "day / time: pick a time in the future")
    _contact(body.customer_id, type="CALLBACK_REQUEST", callback_due=when.isoformat(timespec="seconds"),
             text=body.text)
    return {"received": True, "message": f"Thanks, we'll call you on {_nice(when)}."}


@router.post("/verify-call")
def verify_call(body: CallCheck) -> dict[str, Any]:
    """"Is this call really Westpac?" The code the caller says, checked against the calls Westpac
    booked (policy P3). Recorded in the ledger. The answer never repeats the real code."""
    if not body.code.strip():
        raise HTTPException(422, "code: type the code the caller says")
    if ledger_problem():                                 # fail closed: can't vouch for any caller right now
        return {"genuine": False, "message": "We can't confirm this call right now. Hang up, and call Westpac "
                                             "on the number on the back of your card."}
    decision = check_action({"customer_token": _token(body.customer_id), "action": "VERIFY_CALLER",
                             "requested_by": SYSTEM_ACTOR, "call_code": body.code.strip()})
    if decision.decision == "ALLOW":
        return {"genuine": True, "message": "This matches your call code. It's really Westpac."}
    return {"genuine": False, "message": "Hang up: this isn't Westpac. Westpac will always say your call "
                                         "code, and we'll never ask for your password or PIN."}

