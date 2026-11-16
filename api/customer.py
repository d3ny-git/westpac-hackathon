"""The customer app's API (/customer): what a Westpac customer sees in their app.

    sign-in options     the (fake) customers to sign in as (demo: no passwords)
    overview            their OWN accounts and recent transactions (raw rows of that customer only)
    messages            actions_inbox(token): Quiet Help offers, booked calls with the call code
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

from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import sanitize
from api.common import RUN_LOCK
from api.interaction import fake_customers
from api.live import worker
from nodes.actions import actions_inbox
from nodes.ledger.quiet_help import open_promises
from nodes.policy import check_action
from shared.config import CLEAN_INTERACTIONS_FILE, SYSTEM_ACTOR, clean_dir, now
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
    code: that's the customer's own code, the one place it's meant to be seen."""
    inbox = actions_inbox(_token(customer_id))
    return [{k: v for k, v in m.items() if k != "message_id"} | {"n": n}
            for n, m in reversed(list(enumerate(inbox, start=1)))]


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
    decision = check_action({"customer_token": _token(body.customer_id), "action": "VERIFY_CALLER",
                             "requested_by": SYSTEM_ACTOR, "call_code": body.code.strip()})
    if decision.decision == "ALLOW":
        return {"genuine": True, "message": "This matches your call code. It's really Westpac."}
    return {"genuine": False, "message": "Hang up: this isn't Westpac. Westpac will always say your call "
                                         "code, and we'll never ask for your password or PIN."}

