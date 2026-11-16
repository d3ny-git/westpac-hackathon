"""Account (Node A) endpoints. Same features as ui/pages/A.py:
  1. raw data -> clean data (which columns are kept / tokenised / dropped, one customer's raw row
     next to its clean row)
  2. run Node A's workflow (runbooks/a_account.md, with or without the AI)
  3. every customer's account score, reasons, signals and whether it's in the ledger; the rules
  4. Node A's SCORE entries in the ledger

The raw sample (GET /api/account/raw-sample) is a LOCAL view for the demo (docs/MCP_PLAN.md §6):
raw data never goes through MCP or the AI. It's one of the few responses on the PII-check
allow-list (api/main.py RAW_VIEWS). Node A itself only ever reads the clean data.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

import agent
import sanitize
from api.common import REPO, RUN_LOCK, mcp_server, present_run
from nodes import account
from nodes.ledger import store
from shared.config import CLEAN_TRANSACTION_COLUMNS

router = APIRouter(prefix="/api/account", tags=["account"])

RUNBOOK = REPO / "runbooks" / "a_account.md"


def _raw_rows() -> list[dict[str, str]]:
    path = sanitize.RAW_DIR / sanitize.RAW_TRANSACTIONS
    return sanitize.read_csv(path) if path.exists() else []


def _column_status(column: str) -> str:
    if column in CLEAN_TRANSACTION_COLUMNS:
        return "kept"
    return "customer_token" if column == "customer_id" else "dropped"


@router.get("/overview")
def overview() -> dict[str, Any]:
    """Is the clean data there, which raw columns survive sanitizing, and account.check_data().
    Column NAMES only: no raw values (those are in the raw sample, a local view)."""
    rows = _raw_rows()
    ready = account.clean_file().exists()
    return {"clean_ready": ready,
            "raw_file": f"data/raw/{sanitize.RAW_TRANSACTIONS}" if rows else None,
            "columns": [{"column": c, "status": _column_status(c)} for c in (rows[0] if rows else [])],
            "check": account.check_data() if ready else None}


@router.get("/raw-sample")
def raw_sample(customer_id: Optional[str] = Query(default=None)) -> dict[str, Any]:
    """LOCAL VIEW (fake PII): the people in the raw data, and one customer's first raw transaction
    next to sanitize.sanitize_transactions([row])[0], i.e. exactly what Node A sees."""
    rows = _raw_rows()
    if not rows:
        raise HTTPException(404, "There's no raw transaction file.")
    people = {r["customer_id"]: r["full_name"] for r in rows}
    pick = customer_id if customer_id in people else next(iter(people))
    raw_row = next(r for r in rows if r["customer_id"] == pick)
    return {"people": [{"customer_id": cid, "full_name": name} for cid, name in people.items()],
            "customer_id": pick, "raw": raw_row, "clean": sanitize.sanitize_transactions([raw_row])[0]}


@router.get("/scores")
def scores() -> list[dict[str, Any]]:
    """Every customer's account score from the clean data (highest first), the signals behind it,
    and whether the ledger already has exactly this score."""
    if not account.clean_file().exists():
        return []
    rows = account.load_transactions()
    published = {e.customer_token: e.data for e in store.read(entry_type="SCORE") if e.data["source"] == "ACCOUNT"}
    return [{**m.model_dump(mode="json"),
             "signals": account.account_signals([r for r in rows if r.customer_token == m.customer_token]).model_dump(),
             "in_ledger": published.get(m.customer_token, {}).get("score") == m.score}
            for m in sorted(account.score_all_customers(), key=lambda m: -m.score)]


@router.get("/rules")
def rules() -> list[dict[str, Any]]:
    """Node A's rule table (account.RULES)."""
    return account.RULES


@router.get("/entries")
def entries() -> list[dict[str, Any]]:
    """The SCORE entries Node A has written to the ledger, newest first."""
    mine = [e for e in store.read(entry_type="SCORE") if e.data["source"] == "ACCOUNT"]
    return [{"entry_id": e.entry_id, "customer_token": e.customer_token, "score": e.data["score"],
             "band": e.data["band"], "reasons": e.data["reasons"]} for e in reversed(mine)]


@router.post("/run")
def run(ai: bool = Query(default=False)) -> dict[str, Any]:
    """Run Node A's workflow (runbooks/a_account.md) with or without the AI: check the data ->
    score everyone -> publish to the ledger -> verify the ledger. Unchanged scores aren't written twice."""
    if not account.clean_file().exists():
        raise HTTPException(400, "There's no clean transaction data yet: reset the demo first.")
    with RUN_LOCK:
        return present_run(agent.run(RUNBOOK, ai=ai, server=mcp_server()))
