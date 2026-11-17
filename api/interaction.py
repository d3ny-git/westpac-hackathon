"""Interactions (Node B) endpoints with the mock input form (B5). Same features as ui/pages/B.py:
  1. run Node B for all customers (reset_demo.run_node_b_for_everyone, with or without the AI)
  2. the mock input form: the (fake) customers and staff to pick from, and the two examples
  3. submit: sanitize.add_interaction(raw) -> runbooks/b_interaction.md for that customer; returns
     what was KEPT (the clean row) vs THROWN AWAY, the flags, the run and the customer now
  4. all clean interactions and Node B's ledger entries

PII: the form's raw data is a LOCAL view for the demo (docs/MCP_PLAN.md §6). The pickers and
examples (GET /api/interaction/form-options) and the submit response's "thrown_away" field are on
the PII-check allow-list (api/main.py RAW_VIEWS); everything else is checked. The raw submission is
never stored or logged: add_interaction() writes only the clean row, the runbook only gets the
customer's token, and error messages never echo the input.
"""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import agent
import reset_demo
import sanitize
from api.common import REPO, RUN_LOCK, mcp_server, present_run
from nodes import interaction
from nodes.ledger import store
from nodes.ledger.quiet_help import combined_score, has_open_hardship_case
from shared.config import CLEAN_INTERACTIONS_FILE, Channel, FormStatus, InteractionType, clean_dir, now

router = APIRouter(prefix="/api/interaction", tags=["interaction"])

RUNBOOK = REPO / "runbooks" / "b_interaction.md"
EXAMPLES = REPO / "mock_input_output" / "B_interaction" / "input" / "form_submissions.json"
CALLBACK_DAYS_AHEAD, CALLBACK_HOUR = 2, 14            # B.py's default call-back time: +2 days, 14:00


class Submission(BaseModel):
    """What the mock input form sends. Names and contact details come from the raw customer table
    (as on B.py), so only the customer_id and staff_id are picked."""
    customer_id: str
    staff_id: str = ""                                # "" = self-service (no staff member)
    date: str                                         # YYYY-MM-DD
    channel: Literal[tuple(c.value for c in Channel)]
    type: Literal[tuple(t.value for t in InteractionType)]
    form_status: str = ""                             # only for HARDSHIP_FORM
    callback_due: str = ""                            # only for CALLBACK_REQUEST, YYYY-MM-DDTHH:MM:SS
    text: str = Field(default="", max_length=2000)
    ai: bool = False


# ---------------------------------------------------------------------------
# The raw tables, as on ui/pages/B.py
# ---------------------------------------------------------------------------
def fake_customers() -> dict[str, dict]:
    """The (fake) customers in the raw bank data: customer_id -> name, email, phone."""
    rows = sanitize.read_csv(sanitize.RAW_DIR / sanitize.RAW_TRANSACTIONS)
    return {r["customer_id"]: {"full_name": r["full_name"], "email": r["email"], "phone": r["phone"]} for r in rows}


def fake_staff() -> dict[str, str]:
    """The (fake) staff in the raw interaction history: staff_id -> name."""
    rows = sanitize.read_csv(sanitize.RAW_DIR / sanitize.RAW_INTERACTIONS)
    return {r["staff_id"]: r["staff_name"] for r in rows if r["staff_id"]}


def _clean_path():
    return clean_dir() / CLEAN_INTERACTIONS_FILE


def _need_clean_data() -> None:
    if not _clean_path().exists():
        raise HTTPException(400, "There's no clean interaction data yet: reset the demo first.")


def _entries() -> list[dict[str, Any]]:
    """Node B's ledger entries (INTERACTION scores and promises), newest first."""
    mine = [e for e in store.read(entry_type=["SCORE", "PROMISE"])
            if e.entry_type == "PROMISE" or e.data["source"] == "INTERACTION"]
    return [{"entry_id": e.entry_id, "customer_token": e.customer_token, "entry_type": e.entry_type,
             "what": (f"score {e.data['score']} {e.data['band']} ({', '.join(e.data['reasons']) or 'no signals'})"
                      if e.entry_type == "SCORE" else
                      f"{e.data['promise_id']} {e.data['promise_type']} due {e.data['due'][:16].replace('T', ' ')}")}
            for e in reversed(mine)]


def customer_now(token: str) -> dict[str, Any]:
    """A customer as they now are: combined score, B's score, open case, the promises B finds."""
    score = combined_score(token)
    return {"customer_token": token, "score": score.model_dump() if score else None,
            "open_case": has_open_hardship_case(token), "promises": interaction.customer_promises(token)}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("/overview")
def overview() -> dict[str, Any]:
    """All clean interactions (tokens and keyword flags only) and Node B's ledger entries."""
    ready = _clean_path().exists()
    return {"clean_ready": ready, "clean_rows": sanitize.read_csv(_clean_path()) if ready else [],
            "entries": _entries()}


@router.get("/form-options")
def form_options() -> dict[str, Any]:
    """LOCAL VIEW (fake PII): who the form can be filled in for and by, the two example submissions
    from mock_input_output, and the form's choices and defaults (demo date, call back +2 days 14:00)."""
    today = now().date()
    return {"customers": [{"customer_id": cid, **p} for cid, p in fake_customers().items()],
            "staff": [{"staff_id": sid, "staff_name": name} for sid, name in fake_staff().items()],
            "examples": json.loads(EXAMPLES.read_text()),
            "channels": [c.value for c in Channel], "types": [t.value for t in InteractionType],
            "form_statuses": [s.value for s in FormStatus],
            "defaults": {"date": today.isoformat(),
                         "callback_day": (today + timedelta(days=CALLBACK_DAYS_AHEAD)).isoformat(),
                         "callback_time": f"{CALLBACK_HOUR:02d}:00"}}


@router.post("/submit")
def submit(body: Submission) -> dict[str, Any]:
    """Submit the mock form: sanitize it (only the clean row is stored), then run Node B's workflow
    for that customer. The response's "thrown_away" field is the local raw view; the rest is checked."""
    _need_clean_data()
    customers, staff = fake_customers(), fake_staff()
    if body.customer_id not in customers:
        raise HTTPException(422, "customer_id: not a customer in the raw data")
    if body.staff_id and body.staff_id not in staff:
        raise HTTPException(422, "staff_id: not a staff member in the raw data")
    raw = {"customer_id": body.customer_id, **customers[body.customer_id],
           "staff_id": body.staff_id, "staff_name": staff.get(body.staff_id, ""),
           "date": body.date, "channel": body.channel, "type": body.type,
           "form_status": body.form_status if body.type == InteractionType.HARDSHIP_FORM.value else "",
           "callback_due": body.callback_due if body.type == InteractionType.CALLBACK_REQUEST.value else "",
           "text": body.text}
    with RUN_LOCK:
        clean = sanitize.add_interaction(raw)                       # sanitize, then store ONLY the clean row
        run = agent.run(RUNBOOK, {"token": clean["customer_token"]}, ai=body.ai, server=mcp_server())
    return {"clean": clean,
            "thrown_away": {k: v for k, v in raw.items() if k not in clean and v},
            "flags": clean["flags"],
            "run": present_run(run),
            "customer": customer_now(clean["customer_token"])}


@router.post("/run-all")
def run_all(ai: bool = Query(default=False)) -> dict[str, Any]:
    """Run Node B's workflow once per customer in the clean interactions (with or without the AI).
    Anything already in the ledger is skipped, so running it twice adds nothing."""
    _need_clean_data()
    with RUN_LOCK:
        try:
            runs = reset_demo.run_node_b_for_everyone(mcp_server(), ai=ai)
        except reset_demo.ResetError as exc:
            raise HTTPException(400, str(exc)) from None
    return {"customers": len(runs), "rows": [{
        "customer_token": r.steps[0].args["customer_token"], "status": r.status,
        "score": f"{r.steps[0].output['score']} {r.steps[0].output['band']}",
        "score_written": bool(r.steps[2].output["scores_written"]),
        "promises_written": r.steps[2].output["promises_written"],
    } for r in runs]}
