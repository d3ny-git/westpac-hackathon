"""Live mode (`python app.py --live`): automatic sweeps and the AI intake review, with no buttons.

A background worker in the app process (one workflow at a time: the shared RUN_LOCK).

1. Intake, on each customer submission (immediately). The customer app has already sanitized and
   stored the submission and told the customer "received". The worker then runs
   runbooks/b_intake_review.md WITH the AI: the same steps as b_interaction.md (score -> promises
   -> publish -> verify), plus a hardship assessment for staff written by the AI from the
   sanitized results. The score and the promises come from Node B's fixed rules; the AI only
   assesses and explains. If the AI fails, the same runbook runs without it (the ledger ends up
   identical) and the assessment says "AI unavailable".

2. Cycle, every CYCLE_SECONDS, but ONLY when something changed (the ledger or the clean data moved
   since the last cycle):
     a. scoring    reset_demo.run_node_a + run_node_b_for_everyone, without the AI (deterministic;
                   unchanged scores aren't rewritten)
     b. sweep      runbooks/policy_sweep.md WITH the AI, falling back to no AI on any AI failure
     c. execute    actions_execute_approved(): carries out what a PERSON approved (re-checked by D)
   A customer submission or a staff approval / rejection wakes the worker straight away.
   Idle = nothing changed = nothing runs = no AI calls.

The AI can be switched off with GUARDIAN_LIVE_AI=0 (tests, the repeatable e2e). Without --live the
worker never starts and everything stays manual, except that a customer submission's intake review
runs right away in the request (so staff still see it on the New contacts tab).
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter

from api.common import REPO, RUN_LOCK, hide_call_codes, mcp_server, present_run  # first: puts scripts/ on sys.path
import agent  # noqa: E402
import reset_demo  # noqa: E402
from nodes.actions import actions_execute_approved
from nodes.ledger.chain import verify_chain
from nodes.ledger import store
from shared.config import CLEAN_INTERACTIONS_FILE, CLEAN_TRANSACTIONS_FILE, clean_dir, now

router = APIRouter(prefix="/api/live", tags=["live"])

INTAKE_RUNBOOK = REPO / "runbooks" / "b_intake_review.md"
SWEEP_RUNBOOK = REPO / "runbooks" / "policy_sweep.md"
CYCLE_SECONDS = float(os.getenv("GUARDIAN_LIVE_INTERVAL", "30"))
# A run with the AI ended like this: the AI (not the data) was the problem, so run it again without.
_NOT_AI_FAILURES = {"COMPLETED", "STOPPED", "TOOL_ERROR"}


def ai_wanted() -> bool:
    """Use the AI for intake reviews and sweeps? Off with GUARDIAN_LIVE_AI=0, or without an OpenRouter key."""
    if os.getenv("GUARDIAN_LIVE_AI", "1").strip().lower() in {"0", "off", "false", "no"}:
        return False
    return bool(os.getenv("OPENROUTER_API_KEY") and os.getenv("OPENROUTER_MODEL"))


def run_with_fallback(runbook, variables: Optional[dict[str, str]] = None) -> tuple[Any, Optional[str]]:
    """Run a runbook with the AI if wanted; on an AI failure run the same steps without it.
    Returns (result, why_the_AI_was_not_used or None). Every step is idempotent, so a second,
    AI-free run leaves the ledger exactly as an AI-free run alone would."""
    why: Optional[str] = None
    if ai_wanted():
        try:
            result = agent.run(runbook, variables, ai=True, server=mcp_server())
            if result.status in _NOT_AI_FAILURES:
                return result, None
            why = f"{result.status}: {result.error or 'the AI run did not complete'}"
        except Exception as exc:                          # network, timeout, ...: never stop the worker
            why = f"{type(exc).__name__}"
    else:
        why = "AI switched off" if os.getenv("GUARDIAN_LIVE_AI", "1").strip().lower() in {"0", "off", "false", "no"} \
            else "no OpenRouter key"
    return agent.run(runbook, variables, ai=False, server=mcp_server()), why


# ---------------------------------------------------------------------------
# Intake review
# ---------------------------------------------------------------------------
def _facts_assessment(result) -> str:
    """When the AI isn't available: the same facts, in fixed words (no judgement added)."""
    steps = {s.tool: s.output for s in result.steps}
    score = steps.get("interaction_score") or {}
    promises = steps.get("interaction_promises") or []
    lines = []
    if isinstance(score, dict) and "score" in score:
        reasons = ", ".join(score.get("reasons") or []) or "no signals"
        lines.append(f"Signs: interaction score {score['score']} {score.get('band', '')} ({reasons}).")
    if isinstance(promises, list):
        owed = "; ".join(f"{p.get('promise_type')} due {str(p.get('due', ''))[:16].replace('T', ' ')}"
                         + (f" ({p['promise_id']})" if p.get("promise_id") else "") for p in promises)
        lines.append(f"Promises owed: {owed or 'None'}.")
    return "\n".join(lines)


class Intake:
    """One customer submission: queued, then reviewed."""

    def __init__(self, n: int, clean: dict[str, str]):
        self.n = n
        self.clean = clean
        self.status = "PENDING"
        self.result: Optional[dict[str, Any]] = None
        self.assessment = ""
        self.ai_used = False
        self.ai_note: Optional[str] = None

    def view(self) -> dict[str, Any]:
        c = self.clean
        steps = {s["tool"]: s["output"] for s in (self.result or {}).get("steps", [])}
        score = steps.get("interaction_score") if isinstance(steps.get("interaction_score"), dict) else {}
        publish = steps.get("interaction_publish") if isinstance(steps.get("interaction_publish"), dict) else {}
        promises = steps.get("interaction_promises") if isinstance(steps.get("interaction_promises"), list) else []
        return {"n": self.n, "customer_token": c["customer_token"], "date": c["date"], "channel": c["channel"],
                "type": c["type"], "form_status": c.get("form_status", ""), "callback_due": c.get("callback_due", ""),
                "flags": [f for f in (c.get("flags") or "").split("|") if f], "status": self.status,
                "score": score.get("score"), "band": score.get("band"), "reasons": score.get("reasons", []),
                "promises": promises, "promises_written": publish.get("promises_written", []),
                "assessment": self.assessment, "ai_used": self.ai_used, "ai_note": self.ai_note,
                "run": self.result}


class LiveWorker:
    """The scheduler. tick() does one round synchronously (tests call it directly); start() runs
    tick() in a background thread every CYCLE_SECONDS, or straight away when woken."""

    def __init__(self, interval: float = CYCLE_SECONDS):
        self.interval = interval
        self.enabled = False                        # True once start() has run (python app.py --live)
        self._wake = threading.Event()
        self._lock = threading.Lock()               # guards the fields below
        self._pending: list[Intake] = []
        self._intakes: list[Intake] = []
        self._seen: Optional[tuple] = None          # the state after the last cycle
        self._ledger_id: Optional[tuple] = None     # (size, newest entry, its hash) at the last tick
        self.cycles = 0
        self.ticks = 0
        self.busy: Optional[str] = None
        self.last_cycle: Optional[dict[str, Any]] = None
        self._thread: Optional[threading.Thread] = None
        self._next_at: Optional[float] = None

    # ---- state -------------------------------------------------------------
    @staticmethod
    def signature() -> tuple:
        """What a cycle depends on: the ledger (size, newest hash, still valid?) and the clean data
        files. Validity is included so an insider edit (which moves neither size nor head) is noticed."""
        entries = store.read()
        files = []
        for name in (CLEAN_TRANSACTIONS_FILE, CLEAN_INTERACTIONS_FILE):
            p = clean_dir() / name
            files.append((p.stat().st_size, p.stat().st_mtime_ns) if p.exists() else None)
        return (len(entries), entries[-1].hash if entries else None, verify_chain().valid, tuple(files))

    def _forget_after_reset(self) -> None:
        """A reset (from the walkthrough) starts a new ledger: drop the old contacts feed. A reset
        rebuilds the same first entries, so it shows as the ledger shrinking, or the newest entry seen
        last time no longer being there with the same hash."""
        entries = store.read()
        seen = self._ledger_id
        if seen is not None:
            count, entry_id, entry_hash = seen
            then = store.get(entry_id) if entry_id else None
            if len(entries) < count or (entry_id and (then is None or then.hash != entry_hash)):
                with self._lock:
                    self._intakes = [i for i in self._intakes if i.status == "PENDING"]
        self._remember_ledger()

    def _remember_ledger(self) -> None:
        last = store.read()[-1:]
        self._ledger_id = (store.count(), last[0].entry_id if last else None, last[0].hash if last else None)

    # ---- triggers ----------------------------------------------------------
    def submit(self, clean: dict[str, str]) -> Intake:
        """A customer submission was stored: queue its intake review and wake the worker."""
        with self._lock:
            item = Intake(len(self._intakes) + 1, clean)
            self._intakes.append(item)
            self._pending.append(item)
        if self.enabled:
            self.wake()
        else:
            self.review_pending()                   # manual mode: review it now, in the request
        return item

    def wake(self) -> None:
        self._wake.set()

    # ---- work --------------------------------------------------------------
    def _review(self, item: Intake) -> None:
        with RUN_LOCK:
            result, why = run_with_fallback(INTAKE_RUNBOOK, {"token": item.clean["customer_token"]})
        item.result = present_run(result)
        item.ai_used = why is None and result.mode == "ai"
        item.ai_note = why
        if item.ai_used and result.summary:
            item.assessment = result.summary.strip()
        else:
            item.assessment = f"AI unavailable ({why}). {_facts_assessment(result)}".strip()
        item.status = "DONE" if result.status == "COMPLETED" else result.status

    def review_pending(self) -> int:
        done = 0
        while True:
            with self._lock:
                if not self._pending:
                    return done
                item = self._pending.pop(0)
            self.busy = f"intake review for {item.clean['customer_token']}"
            try:
                self._review(item)
            except Exception as exc:                # keep going: record it, don't kill the worker
                item.status, item.assessment = "ERROR", f"The review failed ({type(exc).__name__})."
            finally:
                self.busy = None
            done += 1

    def cycle(self, trigger: str) -> dict[str, Any]:
        """One scoring -> sweep -> execute round. Each part's failure is recorded, not raised."""
        record: dict[str, Any] = {"n": self.cycles + 1, "trigger": trigger, "demo_time": now().isoformat(),
                                  "started": datetime.now().isoformat(timespec="seconds")}
        with RUN_LOCK:
            # a. Scoring (A + B), deterministic, without the AI.
            self.busy = "scoring (A + B)"
            clean_ready = all((clean_dir() / f).exists() for f in (CLEAN_TRANSACTIONS_FILE, CLEAN_INTERACTIONS_FILE))
            if not clean_ready:
                record["scoring"] = {"status": "SKIPPED", "note": "no clean data yet (reset the demo first)"}
            else:
                try:
                    a = reset_demo.run_node_a(mcp_server(), ai=False)
                    b = reset_demo.run_node_b_for_everyone(mcp_server(), ai=False)
                    record["scoring"] = {"status": "COMPLETED", "account_scores_written": a.steps[2].output["written"],
                                         "customers": len(b),
                                         "promises_written": sum(len(r.steps[2].output["promises_written"]) for r in b)}
                except reset_demo.ResetError as exc:
                    record["scoring"] = {"status": "STOPPED", "note": str(exc)}
            # b. Policy sweep (D), with the AI, falling back to no AI.
            self.busy = "policy sweep (D)"
            sweep, why = run_with_fallback(SWEEP_RUNBOOK)
            record["sweep"] = {**present_run(sweep), "ai_used": why is None and sweep.mode == "ai", "ai_note": why}
            # c. Carry out what a person approved (E). Node D re-checks each one.
            self.busy = "carrying out approved actions (E)"
            try:
                record["executed"] = hide_call_codes(actions_execute_approved())
            except Exception as exc:
                record["executed"], record["execute_error"] = [], f"{type(exc).__name__}: {exc}"
        self.busy = None
        record["finished"] = datetime.now().isoformat(timespec="seconds")
        self.cycles += 1
        self.last_cycle = record
        return record

    def tick(self, trigger: str = "timer") -> Optional[dict[str, Any]]:
        """Review queued intakes, then run a cycle only if something changed since the last one."""
        self.ticks += 1
        self._forget_after_reset()
        self.review_pending()
        if self.signature() == self._seen:
            self._remember_ledger()
            return None                              # idle: nothing changed, nothing runs, no AI calls
        record = self.cycle(trigger)
        self._seen = self.signature()                # the cycle's own writes don't count as a change
        self._remember_ledger()
        return record

    # ---- the background thread ---------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self.enabled = True
        self._thread = threading.Thread(target=self._loop, name="guardian-live", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 60) -> None:
        """Stop the background thread (tests; the app's thread is a daemon and ends with the process)."""
        self._stopping = True
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)
        self._thread, self.enabled = None, False

    def _loop(self) -> None:
        trigger = "start"
        self._stopping = False
        while not self._stopping:
            try:
                self.tick(trigger)
            except Exception as exc:                 # never let the worker die
                self.last_cycle = {"n": self.cycles, "error": f"{type(exc).__name__}: {exc}"}
            self._next_at = time.monotonic() + self.interval
            woken = self._wake.wait(self.interval)
            self._wake.clear()
            trigger = "change" if woken else "timer"

    # ---- views ---------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        next_in = None
        if self.enabled and self._next_at is not None:
            next_in = max(0, round(self._next_at - time.monotonic()))
        return {"enabled": self.enabled, "interval_seconds": self.interval, "ai": ai_wanted(),
                "busy": self.busy, "cycles": self.cycles, "next_check_in_seconds": next_in,
                "pending_intakes": len(self._pending), "last_cycle": self.last_cycle}

    def intakes(self) -> list[dict[str, Any]]:
        with self._lock:
            return [i.view() for i in reversed(self._intakes)]


worker = LiveWorker()


def start() -> LiveWorker:
    """Called by `python app.py --live`."""
    worker.start()
    return worker


# ---------------------------------------------------------------------------
# Routes (tokens only, every response PII-checked)
# ---------------------------------------------------------------------------
@router.get("/status")
def live_status() -> dict[str, Any]:
    """Is live mode on, is the AI on, what's running, and the last cycle (scoring, sweep with its
    AI summary, what was carried out)."""
    return worker.status()


@router.get("/intake")
def live_intake() -> list[dict[str, Any]]:
    """Customer contacts from the customer app, newest first, each with its hardship assessment."""
    return worker.intakes()
