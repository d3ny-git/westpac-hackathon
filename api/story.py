"""The SPEC's 10-step story for hero (cust_af4200), worked out from the ledger, and the live
pipeline counts for the Home page.

progress() is a pure function of the ledger: the same ledger always gives the same ticks. It never
writes anything and never does a step itself: staff still click Approve / Execute themselves.

    1  A → C            hero has an ACCOUNT score
    2  C → D            hero is (or was) on the Quiet Help list
    3  D → E            a QUIET_HELP_PUSH recommendation exists for hero
    4  Human → E        a person approved it
    5  E → Customer     a QuietHelpPush ACTION exists for hero
    6  Customer → B     hero has a HARDSHIP_RESPONSE promise
    7  B → C            hero has an INTERACTION score and an open case (combined 75)
    8  D → E            a BOOK_MEETING recommendation for hero is approved and carried out (CONTACT_SCHEDULED)
    9  Collections → D  a BLOCKED P2 decision exists for hero
    10 Scam caller → D  a BLOCKED P3 decision exists for hero
"""
from __future__ import annotations

from typing import Any, Optional

import sanitize
from api.common import HERO
from nodes.actions import actions_inbox
from nodes.ledger import store
from nodes.ledger.chain import verify_chain
from nodes.ledger.quiet_help import (combined_score, open_hardship_case, open_promises, quiet_help_candidates,
                                     tracked_recommendations)
from nodes.policy import check_deadlines
from shared.config import CLEAN_INTERACTIONS_FILE, CLEAN_TRANSACTIONS_FILE, clean_dir

# (route, what the SPEC says happens). Titles follow the SPEC's "one customer, start to finish" table.
STEPS = [
    ("A → C", "Account score arrives: 63 HIGH, SALARY_STOPPED"),
    ("C → D", "Quiet Help rule: hero is a Quiet Help candidate"),
    ("D → E", "D recommends a Quiet Help push"),
    ("Human → E", "A person approves it"),
    ("E → Customer", "E sends the push notification"),
    ("Customer → B", "Hero submits the hardship form"),
    ("B → C", "Score 50 + a 21-day HARDSHIP_RESPONSE promise: combined 75, case open"),
    ("D → E", "BOOK_MEETING recommended → approved → call booked with a call code"),
    ("Collections → D", "SEND_DEFAULT_NOTICE → BLOCKED (P2)"),
    ("Scam caller → D", "Wrong call code → BLOCKED (P3)"),
]

PAGES = {"Home": "/", "Account": "/account", "Interactions": "/interactions", "Ledger": "/ledger",
         "Policy": "/policy", "Actions": "/actions"}


def _hint(page: str, text: str) -> dict[str, str]:
    return {"page": page, "path": PAGES[page], "text": text}


def _rec_hint(recs: list, kind: str, customer: str, sweep_text: str) -> dict[str, str]:
    """What to do next for the newest recommendation of a kind: sweep, approve, or execute."""
    if not recs:
        return _hint("Policy", sweep_text)
    latest = recs[-1]
    rid = latest.recommendation.rec_id
    if latest.current_status == "AWAITING_APPROVAL":
        return _hint("Actions", f"Approval Queue: approve {rid} ({kind} for {customer})")
    if latest.current_status == "APPROVED":
        return _hint("Actions", f"Approval Queue: Execute {rid} ({kind} for {customer})")
    if latest.current_status == "REJECTED":
        return _hint("Home", f"{rid} was rejected, so nothing was sent. Reset the demo to play it again")
    return _hint("Actions", f"{rid} is {latest.current_status}")


def progress(customer: str = HERO) -> dict[str, Any]:
    """Which of the 10 story steps have happened, each with a detail line and a 'next' hint."""
    entries = store.read(customer_token=customer)
    recs = tracked_recommendations(customer)
    by_kind = {kind: [t for t in recs if t.recommendation.recommendation == kind]
               for kind in ("QUIET_HELP_PUSH", "BOOK_MEETING")}

    def of(entry_type: str, **match: Any) -> list:
        return [e for e in entries if e.entry_type == entry_type
                and all(e.data.get(k) == v for k, v in match.items())]

    account = of("SCORE", source="ACCOUNT")
    interaction = of("SCORE", source="INTERACTION")
    on_list = any(c.customer_token == customer for c in quiet_help_candidates())
    approved = lambda ts: [t for t in ts if t.decided_by and t.current_status in ("APPROVED", "DONE")]  # noqa: E731
    pushes = [e for e in of("ACTION", action="QUIET_HELP_PUSH") if "message_id" in e.data]
    cases = of("PROMISE", promise_type="HARDSHIP_RESPONSE")
    case = open_hardship_case(customer)
    score = combined_score(customer)
    contacts = of("CONTACT_SCHEDULED")
    p2 = of("BLOCKED", policy="P2")
    p3 = of("BLOCKED", policy="P3")
    qh, bm = by_kind["QUIET_HELP_PUSH"], by_kind["BOOK_MEETING"]

    load_hint = _hint("Home", "Demo controls: Reset demo (real pipeline)")
    run_a_hint = _hint("Account", "Run Node A's workflow (with or without the AI)")
    form_hint = _hint("Interactions", "Mock input form: 'Fill in: hero's hardship form' → Submit to Node B")
    done: list[tuple[bool, Optional[str], dict[str, str]]] = [
        (bool(account),
         f"ACCOUNT score {account[-1].data['score']} {account[-1].data['band']}" if account else None,
         run_a_hint),
        (on_list or bool(qh),
         "On the Quiet Help list" if on_list else ("Was on the list (D recommended a push)" if qh else None),
         _hint("Home", "Hero must be HIGH with no open case and no recent push: Reset demo (real pipeline)")),
        (bool(qh), f"{qh[0].recommendation.rec_id} QUIET_HELP_PUSH" if qh else None,
         _hint("Policy", "Policy sweep: run it (with or without the AI)")),
        (bool(approved(qh)),
         f"{approved(qh)[0].recommendation.rec_id} approved by {approved(qh)[0].decided_by}" if approved(qh) else None,
         _rec_hint(qh, "Quiet Help push", customer, "Policy sweep: run it (with or without the AI)")),
        (bool(pushes), f"Message {pushes[-1].data['message_id']} sent" if pushes else None,
         _rec_hint(qh, "Quiet Help push", customer, "Policy sweep: run it (with or without the AI)")),
        (bool(cases), f"{cases[-1].data['promise_id']} due {cases[-1].data['due'][:10]}" if cases else None,
         form_hint),
        (bool(interaction) and case is not None,
         f"Combined score {score.score} {score.band}, case open" if score and interaction and case else None,
         form_hint),
        (bool(approved(bm)) and bool(contacts),
         f"Call booked for {contacts[-1].data['contact_time'][:16].replace('T', ' ')}" if contacts else None,
         _rec_hint(bm, "book a meeting", customer,
                   "Policy sweep: run it again, so D recommends BOOK_MEETING for the open case")),
        (bool(p2), f"{p2[-1].entry_id}: {p2[-1].data['reason']}" if p2 else None,
         _hint("Policy", f"Check an action: SEND_DEFAULT_NOTICE for {customer}")),
        (bool(p3), f"{p3[-1].entry_id}: {p3[-1].data['reason']}" if p3 else None,
         _hint("Actions", f"Caller verification: type a wrong code (e.g. K7P4QX) for {customer}")),
    ]

    steps = [{"n": n, "route": route, "title": title, "done": ok, "detail": detail if ok else None,
              "hint": None if ok else hint}
             for n, ((route, title), (ok, detail, hint)) in enumerate(zip(STEPS, done), start=1)]
    if store.count() == 0:                                # empty ledger: everything starts with a reset
        for s in steps:
            s["hint"] = load_hint
    elif not entries:                                     # "Start empty": A hasn't scored anyone yet
        for s in steps:
            s["hint"] = run_a_hint
    current = next((s for s in steps if not s["done"]), None)
    return {"customer_token": customer, "steps": steps, "done_count": sum(s["done"] for s in steps),
            "total": len(steps), "current": current["n"] if current else None,
            "next": current["hint"] if current else None, "complete": current is None}


def _clean_rows(name: str) -> Optional[int]:
    """How many rows a clean CSV has (None when the real-pipeline reset hasn't made it yet)."""
    path = clean_dir() / name
    return len(sanitize.read_csv(path)) if path.exists() else None


def pipeline() -> dict[str, Any]:
    """Live counts per node, worked out from the ledger (no AI)."""
    entries = store.read()
    report = verify_chain()

    def count(entry_type: str, **match: Any) -> int:
        return sum(1 for e in entries if e.entry_type == entry_type
                   and all(e.data.get(k) == v for k, v in match.items()))

    recs = tracked_recommendations()
    status = {s: sum(1 for t in recs if t.current_status == s)
              for s in ("AWAITING_APPROVAL", "APPROVED", "DONE", "REJECTED")}
    decisions = [e for e in entries if e.entry_type in ("ACTION", "BLOCKED") and "decision" in e.data]
    customers = sorted({e.customer_token for e in entries})
    messages = sum(len(actions_inbox(c)) for c in customers) if entries else 0
    return {
        "A": {"clean_transactions": _clean_rows(CLEAN_TRANSACTIONS_FILE),
              "account_scores": count("SCORE", source="ACCOUNT")},
        "B": {"clean_interactions": _clean_rows(CLEAN_INTERACTIONS_FILE),
              "interaction_scores": count("SCORE", source="INTERACTION"),
              "promises": sum(1 for e in entries if e.entry_type == "PROMISE"
                              and e.data.get("promise_type") != "MEETING")},
        "C": {"entries": len(entries), "valid": report.valid, "customers": len(customers),
              "open_promises": len(open_promises()), "quiet_help": len(quiet_help_candidates())},
        "D": {"recommendations": len(recs), "deadline_alerts": len(check_deadlines()),
              "allowed": sum(1 for e in decisions if e.data["decision"] == "ALLOW"),
              "blocked": sum(1 for e in decisions if e.data["decision"] == "BLOCK")},
        "E": {"awaiting_approval": status["AWAITING_APPROVAL"], "approved": status["APPROVED"],
              "done": status["DONE"], "rejected": status["REJECTED"], "messages_sent": messages},
    }
