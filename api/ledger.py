"""Ledger (Node C) endpoints: integrity + checkpoint, the full ledger, Risk Dashboard, Quiet Help
and customer lookup. Same features as ui/pages/C.py, read straight from the ledger (no AI)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi import Path as PathParam

from api.common import hide_call_codes
from nodes.ledger import store
from nodes.ledger.chain import ChainReport, checkpoint_holds, verify_chain
from nodes.ledger.dashboard import risk_dashboard
from nodes.ledger.quiet_help import combined_score, open_hardship_case, quiet_help_candidates
from shared.config import CUSTOMER_TOKEN_PATTERN
from shared.schemas import LedgerEntry

router = APIRouter(prefix="/api/ledger", tags=["ledger"])


# ---------------------------------------------------------------------------
# Helpers COPIED from ui/pages/C.py (not moved: the Streamlit page stays unchanged).
# ---------------------------------------------------------------------------
def describe(entry: LedgerEntry) -> str:
    """One short line saying what an entry is about, for the ledger table."""
    d, t = entry.data, entry.entry_type
    if t == "SCORE":
        return f"{d['source']} score {d['score']} ({d['band']}): {', '.join(d['reasons']) or 'no signals'}"
    if t == "PROMISE":
        return f"{d['promise_id']} {d['promise_type']} due {d['due'][:16].replace('T', ' ')}"
    if t == "RECOMMENDATION":
        return f"{d['rec_id']} recommend {d['recommendation']} ({', '.join(d['why'])})"
    if t == "APPROVAL":
        return f"{d['rec_id']} {'approved' if d['approved'] else 'rejected'} by {d['approved_by']}"
    if t == "STATUS_UPDATE":
        return f"{d['ref_id']} → {d['status']}"
    if t == "CONTACT_SCHEDULED":
        return f"call at {d['contact_time'][:16].replace('T', ' ')}, code {d['call_code']}"
    if t in ("ACTION", "BLOCKED") and "decision" in d:
        policy = f" ({d['policy']})" if d.get("policy") else ""
        return f"{d['action']} → {d['decision']}{policy}: {d['reason']}"
    if t == "ACTION":
        extra = d.get("message_id") or d.get("call_code") or ", ".join(d.get("why", []))
        return f"{d['action']} {extra}".strip()
    return json.dumps(d)[:80]


def checkpoint_file() -> Path:
    """The checkpoint lives next to the ledger it belongs to, e.g. data/guardian_checkpoint.json (gitignored).
    The same file as ui/pages/C.py, so both UIs see the same checkpoint."""
    db = store.db_file()
    return db.with_name(f"{db.stem}_checkpoint.json")


def read_checkpoint() -> dict | None:
    try:
        return json.loads(checkpoint_file().read_text())
    except (FileNotFoundError, ValueError):
        return None


def save_checkpoint(report) -> None:
    checkpoint_file().parent.mkdir(parents=True, exist_ok=True)
    checkpoint_file().write_text(json.dumps({"last_entry_id": report.last_entry_id, "head_hash": report.head_hash,
                                           "entries": report.entries_checked}, indent=2))


# ---------------------------------------------------------------------------
# Presenters
# ---------------------------------------------------------------------------
def present(entry: LedgerEntry) -> dict[str, Any]:
    """An entry for the screen. Call codes are hidden (they only appear on the customer's phone)."""
    safe = entry.model_copy(update={"data": hide_call_codes(entry.data)})
    return {"entry_id": safe.entry_id, "created_at": safe.created_at.isoformat(),
            "customer_token": safe.customer_token, "entry_type": safe.entry_type, "what": describe(safe),
            "data": safe.data, "prev_hash": safe.prev_hash, "hash": safe.hash}


def integrity_report() -> dict[str, Any]:
    report: ChainReport = verify_chain()
    saved = read_checkpoint()
    checkpoint: Optional[dict[str, Any]] = None
    if saved and saved.get("last_entry_id") and saved.get("head_hash"):
        checkpoint = {**saved, "holds": checkpoint_holds(saved["last_entry_id"], saved["head_hash"])}
    return {"count": store.count(), "report": report.model_dump(), "checkpoint": checkpoint}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("/integrity")
def integrity() -> dict[str, Any]:
    """Is the ledger untouched (chain.verify_chain), and does the recorded checkpoint still hold?"""
    return integrity_report()


@router.post("/checkpoint")
def record_checkpoint() -> dict[str, Any]:
    """Remember the newest entry's hash, so cutting off or rebuilding history is caught later."""
    if store.count() == 0:
        raise HTTPException(400, "The ledger is empty: load demo data first.")
    save_checkpoint(verify_chain())
    return integrity_report()


@router.get("/entries")
def entries(customer: list[str] = Query(default=[]), type: list[str] = Query(default=[])) -> dict[str, Any]:  # noqa: A002
    """The full ledger, oldest first, optionally filtered by customers and entry types
    (e.g. ?type=SCORE&type=PROMISE&customer=cust_af4200)."""
    everything = store.read()
    report = verify_chain()
    shown = [e for e in everything
             if (not type or e.entry_type in type) and (not customer or e.customer_token in customer)]
    return {"entries": [present(e) for e in shown],
            "customers": sorted({e.customer_token for e in everything}),
            "types": sorted({e.entry_type for e in everything}),
            "bad_entry": None if report.valid else report.first_bad_entry}


@router.get("/dashboard")
def dashboard() -> list[dict[str, Any]]:
    """Risk Dashboard: every promise the bank hasn't kept yet, most at-risk first, then soonest due."""
    return [r.model_dump() for r in risk_dashboard()]


@router.get("/quiet-help")
def quiet_help() -> list[dict[str, Any]]:
    """Quiet Help list: HIGH or CRITICAL, no open hardship case, no push in the last 30 days."""
    return [c.model_dump() for c in quiet_help_candidates()]


@router.get("/customers")
def customers() -> list[str]:
    """Every customer token in the ledger, sorted."""
    return sorted({e.customer_token for e in store.read()})


@router.get("/customers/{token}")
def customer(token: str = PathParam(pattern=CUSTOMER_TOKEN_PATTERN)) -> dict[str, Any]:
    """One customer: combined score (A + B), open hardship case and their full history."""
    history = store.read(customer_token=token)
    if not history:
        raise HTTPException(404, f"{token} isn't in the ledger")
    score = combined_score(token)
    case = open_hardship_case(token)
    return {"customer_token": token,
            "score": score.model_dump() if score else None,
            "open_case": case.model_dump(mode="json") if case else None,
            "history": [present(e) for e in history]}
