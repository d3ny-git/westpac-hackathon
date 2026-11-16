"""Policy (Node D) endpoints: check an action, deadlines, recommendations, decisions, explain, and
the policy sweep with its run logs. Same features as ui/pages/D.py.

Nothing here can approve a recommendation: that's a person's job on the Actions page."""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi import Path as PathParam
from pydantic import BaseModel

import agent
from api.common import REPO, hide_call_codes
from nodes.ledger import store
from nodes.ledger.quiet_help import tracked_recommendations
from nodes.policy import check_action, check_deadlines, explain, explain_in_words
from shared.config import ENTRY_ID_PATTERN

router = APIRouter(prefix="/api/policy", tags=["policy"])

SWEEP = REPO / "runbooks" / "policy_sweep.md"
_RUN_ID = re.compile(r"^[A-Za-z0-9_.-]+$")       # run ids are file names: never let a path through
_sweep_lock = threading.Lock()                    # one sweep at a time (a double click waits its turn)


class CheckRequest(BaseModel):
    """What the "Check an action" form sends. check_action() validates it (ActionRequest)."""
    customer_token: str
    action: str
    requested_by: str
    call_code: Optional[str] = None


def decide(request: dict[str, Any]) -> dict[str, Any]:
    """Run policy.check_action (which records the decision) and say which entry it became."""
    decision = check_action(request)
    return {"entry_id": store.read()[-1].entry_id, "decision": decision.model_dump(mode="json")}


@router.post("/check")
def check(body: CheckRequest) -> dict[str, Any]:
    """Ask D whether an action is allowed: ALLOW or BLOCK with the policy and reason. Recorded in the ledger."""
    return decide({**body.model_dump(), "call_code": body.call_code or None})


@router.get("/deadlines")
def deadlines() -> list[dict[str, Any]]:
    """P1: open promises that are overdue (ESCALATE) or due within 24 hours (ALERT). Read-only."""
    return [a.model_dump(mode="json") for a in check_deadlines()]


@router.get("/recommendations")
def recommendations() -> list[dict[str, Any]]:
    """Everything D has recommended, with where each one is now (oldest first)."""
    return [{**t.recommendation.model_dump(mode="json"), "status": t.current_status, "decided_by": t.decided_by,
             "entry_id": t.entry_id, "recorded_at": t.recorded_at.isoformat()}
            for t in tracked_recommendations()]


@router.get("/decisions")
def decisions() -> list[dict[str, Any]]:
    """Every ALLOW / BLOCK decision D recorded (BLOCKED / ACTION entries with a decision), newest first."""
    found = [e for e in store.read(entry_type=["BLOCKED", "ACTION"]) if "decision" in e.data]
    return [{"entry_id": e.entry_id, "created_at": e.created_at.isoformat(), "customer_token": e.customer_token,
             **{k: e.data.get(k) for k in ("action", "decision", "policy", "reason")},
             "flags": e.data.get("flags", [])} for e in reversed(found)]


@router.get("/explain/{entry_id}")
def explain_entry(entry_id: str = PathParam(pattern=ENTRY_ID_PATTERN)) -> dict[str, Any]:
    """The facts behind a decision or recommendation, as they were when it was made (call codes hidden)."""
    return explain(entry_id).model_dump()


@router.post("/explain/{entry_id}/words")
def explain_entry_in_words(entry_id: str = PathParam(pattern=ENTRY_ID_PATTERN)) -> dict[str, Any]:
    """The same facts in plain English, from the AI (it only rephrases them)."""
    explain(entry_id)                    # a bad entry is a PolicyError (400) before the AI is asked
    try:
        return {"entry_id": entry_id, "text": explain_in_words(entry_id)}
    except Exception as exc:             # no key / no network: the facts are still the full explanation
        raise HTTPException(503, f"The AI couldn't be reached ({type(exc).__name__}). "
                                 f"The facts are the full explanation.") from exc


@router.post("/sweep")
def sweep(ai: bool = Query(default=False)) -> dict[str, Any]:
    """Run runbooks/policy_sweep.md (agent.run), with the AI or without it. Both leave the ledger identical."""
    with _sweep_lock:
        result = agent.run(SWEEP, ai=ai)
    return {"run_id": result.run_id, "status": result.status, "mode": result.mode,
            "summary": result.summary, "error": result.error}


# ---------------------------------------------------------------------------
# Run logs (data/runs/<run_id>.jsonl, written by agent.py)
# ---------------------------------------------------------------------------
def _run_files() -> list[Path]:
    runs_dir = Path(agent.RUNS_DIR)
    if not runs_dir.exists():
        return []
    return sorted((p for p in runs_dir.glob("*.jsonl") if p.name != "llm_calls.jsonl"), reverse=True)


def _events(path: Path) -> list[dict[str, Any]]:
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
    return hide_call_codes(events)


def _summary(path: Path, events: list[dict[str, Any]]) -> dict[str, Any]:
    start = next((e for e in events if e.get("event") == "start"), {})
    finish = next((e for e in events if e.get("event") == "finish"), {})
    return {"run_id": path.stem, "runbook": start.get("runbook"), "mode": start.get("mode"),
            "status": finish.get("status", "RUNNING")}


@router.get("/runs")
def runs() -> list[dict[str, Any]]:
    """Every run log, newest first."""
    return [_summary(p, _events(p)) for p in _run_files()]


@router.get("/runs/{run_id}")
def run_log(run_id: str) -> dict[str, Any]:
    """One run, event by event, to replay it (each step's output, stops, off-script calls, summary)."""
    path = Path(agent.RUNS_DIR) / f"{run_id}.jsonl"
    if not _RUN_ID.match(run_id) or run_id == "llm_calls" or not path.is_file():
        raise HTTPException(404, f"No run log called {run_id}")
    events = _events(path)
    finish = next((e for e in events if e.get("event") == "finish"), {})
    return {**_summary(path, events), "summary": finish.get("summary") or "", "error": finish.get("error"),
            "events": events}
