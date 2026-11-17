"""Demo controls, in one place for every page: reset the demo with the real pipeline (or start empty),
load the mock fixture stages, simulate an insider edit, plus the story progress and pipeline counts.

Hero's hardship form (SPEC step 6) is submitted on the Interactions (B) page's mock input form.
POST /api/demo/hero-form stays as the scripted shortcut (load_fixtures --step hero-form) for scripts."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import load_fixtures
import reset_demo
from api import story
from api.common import CHECKABLE, HERO, RUN_LOCK, STAFF
from api.ledger import checkpoint_file
from nodes.ledger import store
from shared.config import CLEAN_INTERACTIONS_FILE, CLEAN_TRANSACTIONS_FILE, clean_dir, now

router = APIRouter(prefix="/api/demo", tags=["demo"])


class LoadRequest(BaseModel):
    stage: Literal[load_fixtures.STAGES]       # "start" or "full"


class ResetRequest(BaseModel):
    empty: bool = False                        # True: sanitize + fresh ledger, but don't run A or B


# ---------------------------------------------------------------------------
# COPIED from ui/pages/C.py (not moved: the Streamlit page stays unchanged).
# ---------------------------------------------------------------------------
def simulate_insider_edit() -> str:
    """DEMO ONLY: what an insider with database access might try. Removes the append-only
    protection and lowers the most worrying score in the ledger. Returns the entry changed."""
    scores = store.read(entry_type="SCORE")
    target = max(scores, key=lambda e: e.data["score"])
    forged = {**target.data, "score": 10, "band": "LOW", "reasons": []}
    with closing(sqlite3.connect(store.db_file(), isolation_level=None)) as conn:
        conn.execute("DROP TRIGGER IF EXISTS ledger_no_update")
        conn.execute("UPDATE ledger SET data = ? WHERE entry_id = ?",
                     (json.dumps(forged, sort_keys=True, separators=(",", ":")), target.entry_id))
    return target.entry_id


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("/meta")
def meta() -> dict[str, Any]:
    """Fixed values the UI needs: demo time (config.now()), the hero, stages, staff and checkable actions."""
    return {"now": now().isoformat(), "hero": HERO, "stages": list(load_fixtures.STAGES),
            "staff": STAFF, "checkable": CHECKABLE}


@router.get("/status")
def status() -> dict[str, Any]:
    """How many entries the ledger has, whether hero's hardship form is in it, and whether the clean
    data A and B read (data/clean, written by the real-pipeline reset) is there."""
    count = store.count()
    return {"count": count, "hero_form_submitted": count > 0 and load_fixtures.hero_form_submitted(),
            "clean_ready": all((clean_dir() / f).exists() for f in (CLEAN_TRANSACTIONS_FILE, CLEAN_INTERACTIONS_FILE))}


@router.post("/reset")
def reset(body: ResetRequest) -> dict[str, Any]:
    """Reset the demo with the REAL pipeline (scripts/reset_demo.py): raw data -> sanitize -> Nodes A
    and B -> a fresh ledger, with its PII self-check. empty=true stops after the fresh ledger, so A and
    B can be run live on their pages. Clears the checkpoint."""
    with RUN_LOCK:
        try:
            report = reset_demo.reset(quiet=True, empty=body.empty)
        except reset_demo.ResetError as exc:
            raise HTTPException(400, str(exc)) from None
    checkpoint_file().unlink(missing_ok=True)
    return {**report, "empty": body.empty}


@router.post("/load")
def load(body: LoadRequest) -> dict[str, Any]:
    """Wipe the demo ledger and load a story stage (load_fixtures.load(reset=True)). Clears the checkpoint."""
    added = load_fixtures.load(body.stage, reset=True)
    checkpoint_file().unlink(missing_ok=True)
    return {"stage": body.stage, "added": added}


@router.post("/hero-form")
def hero_form() -> dict[str, Any]:
    """Hero submits the hardship form: B's mock output (interaction score 50 + a 21-day
    HARDSHIP_RESPONSE promise). Refused on an empty ledger or if it's already in."""
    try:
        added = load_fixtures.submit_hero_form()
    except SystemExit as exc:                  # load_fixtures reports refusals this way (it's a CLI too)
        raise HTTPException(400, str(exc)) from None
    return {"added": added}


@router.post("/tamper")
def tamper() -> dict[str, Any]:
    """DEMO ONLY: quietly edit the highest score, as an insider might. Reload a stage to undo."""
    if store.count() == 0 or not store.read(entry_type="SCORE"):
        raise HTTPException(400, "The ledger has no scores to edit: load demo data first.")
    return {"changed": simulate_insider_edit()}


@router.get("/story")
def story_progress() -> dict[str, Any]:
    """The SPEC's 10-step story for hero, worked out from the ledger."""
    return story.progress()


@router.get("/pipeline")
def pipeline() -> dict[str, Any]:
    """Live counts per node (A, B → C → D → E) for the Home page."""
    return story.pipeline()
