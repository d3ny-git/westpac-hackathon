"""Load a realistic demo ledger into data/guardian.db, so the system has something to work with.

    python scripts/load_fixtures.py                  # stage "start" (the demo's starting point)
    python scripts/load_fixtures.py --stage full     # everything, up to E's actions
    python scripts/load_fixtures.py --reset          # wipe an existing ledger first
    python scripts/load_fixtures.py --step hero-form # hero submits the hardship form (scripted shortcut)

Stages (the SPEC's story for hero, cust_af4200):

  start   SPEC step 1. Every customer is scored, hero has NOT sent the hardship form yet, so
          hero is HIGH with no open case: a Quiet Help candidate. This is where the live demo
          begins (D recommends -> a person approves -> E acts -> hero fills in the form ...).

  full    start + hero's hardship form + Node D's 5 recommendations + Node E's actions
          (approvals, a Quiet Help push, a meeting booked with call code U5PXLW, ...).
          R-0005 is still awaiting approval, so E's approval queue isn't empty, and P3 has
          a real call code to check.

Scripted shortcut for SPEC step 6:

  --step hero-form   hero submits the hardship form, the same as filling in the B page's mock
                     input form (ui/pages/B.py). After reset_demo.py it goes through Node B for
                     real (score 50 + a 21-day HARDSHIP_RESPONSE promise). It doesn't reset anything.

Where the data comes from: mock_input_output/ (A, B and E samples), plus the few extra entries
in data/fixtures/seed_extras.json. Nothing is copied, so there's only ever one version of it.

Until Nodes A and B are built, this is how the ledger gets its scores. Once they exist,
reset_demo.py (E5) runs the real A and B workflows instead and can still use this for the rest.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from nodes.ledger import store  # noqa: E402
from nodes.ledger.chain import verify_chain  # noqa: E402
from nodes.ledger.dashboard import risk_dashboard  # noqa: E402
from nodes.ledger.quiet_help import combined_score, has_open_hardship_case, quiet_help_candidates  # noqa: E402
from shared.config import CLEAN_INTERACTIONS_FILE, clean_dir  # noqa: E402

MOCK = REPO / "mock_input_output"
EXTRAS = REPO / "data" / "fixtures" / "seed_extras.json"
STAGES = ("start", "full")
HERO = "cust_af4200"
HERO_CUSTOMER_ID = "100200301"                     # hero's (fake) bank ID in the raw data


def _json(path: Path) -> Any:
    return json.loads(path.read_text())


def _is_hero_form(entry_type: str, data: dict) -> bool:
    """The two entries that only exist once hero has submitted the hardship form."""
    if data.get("customer_token") != HERO:
        return False
    return ((entry_type == "SCORE" and data.get("source") == "INTERACTION")
            or (entry_type == "PROMISE" and data.get("promise_type") == "HARDSHIP_RESPONSE"))


def plan(stage: str = "start") -> list[dict]:
    """The entries to load, in story order, as {entry_type, customer_token, data, created_at?}."""
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}; use one of {STAGES}")
    extras = _json(EXTRAS)

    def entry(entry_type, data, customer_token=None, created_at=None):
        return {"entry_type": entry_type, "customer_token": customer_token or data["customer_token"],
                "data": data, "created_at": created_at}

    a_scores = _json(MOCK / "A_account/output/account_scores.json")
    b_scores = _json(MOCK / "B_interaction/output/interaction_scores.json")
    promises = _json(MOCK / "B_interaction/output/promises.json")

    # 1. Older events first: the ledger never goes back in time.
    entries = [entry(e["entry_type"], e["data"], e["customer_token"], e.get("created_at"))
               for e in extras["before_scores"]]

    # 2. Everyone's scores and promises, as they were BEFORE hero's hardship form.
    entries += [entry("SCORE", s) for s in a_scores]
    entries += [entry("SCORE", s) for s in b_scores if not _is_hero_form("SCORE", s)]
    entries += [entry(e["entry_type"], e["data"], e["customer_token"]) for e in extras["hero_before_form"]]
    entries += [entry("PROMISE", p) for p in promises if not _is_hero_form("PROMISE", p)]
    if stage == "start":
        return entries

    # 3. full: hero submits the hardship form (new B score + a 21-day HARDSHIP_RESPONSE promise) ...
    entries += hero_form_entries()
    # ... Node D recommends ...
    entries += [entry("RECOMMENDATION", r) for r in _json(MOCK / "E_actions/input/recommendations.json")]
    # ... and Node E carries out what people approved.
    entries += [entry(w["entry_type"], w["data"], w["customer_token"])
                for w in _json(MOCK / "E_actions/output/ledger_writes.json")]
    return entries


def hero_form_entries() -> list[dict]:
    """What Node B writes when hero submits the hardship form (from B's mock output):
    hero's new INTERACTION score (50 MODERATE) and the HARDSHIP_RESPONSE promise (due 1 Dec 17:00)."""
    b_scores = _json(MOCK / "B_interaction/output/interaction_scores.json")
    promises = _json(MOCK / "B_interaction/output/promises.json")
    return ([{"entry_type": "SCORE", "customer_token": s["customer_token"], "data": s, "created_at": None}
             for s in b_scores if _is_hero_form("SCORE", s)]
            + [{"entry_type": "PROMISE", "customer_token": p["customer_token"], "data": p, "created_at": None}
               for p in promises if _is_hero_form("PROMISE", p)])


def hero_form_submitted(*, db_path: Optional[Path | str] = None) -> bool:
    """True if hero's hardship form is already in the ledger."""
    return any(e.data.get("promise_type") == "HARDSHIP_RESPONSE"
               for e in store.read(customer_token=HERO, entry_type="PROMISE", db_path=db_path))


def submit_hero_form(*, db_path: Optional[Path | str] = None) -> int:
    """Scripted shortcut: hero submits the hardship form (SPEC step 6). Returns ledger entries added.

    In the demo this is done on the B page's mock input form (ui/pages/B.py). This function does
    the same thing for scripts and tests. When the clean data exists (after
    `scripts/reset_demo.py`) it goes through Node B's REAL path: hero's raw form (with fake PII,
    from mock_input_output/B_interaction/input/form_submissions.json) is sanitized, added to
    data/clean/interactions.csv, and published by Node B. On a ledger loaded from the mock
    fixtures, B's mock output for hero is written instead.

    Refuses on an empty ledger (load a stage first) and if the form is already in the ledger.
    """
    if store.count(db_path=db_path) == 0:
        raise SystemExit("The ledger is empty. Load a stage first.")
    if hero_form_submitted(db_path=db_path):
        raise SystemExit("Hero's hardship form is already in the ledger.")
    if (clean_dir() / CLEAN_INTERACTIONS_FILE).exists():
        return _submit_hero_form_through_node_b(db_path)
    entries = hero_form_entries()
    for e in entries:
        store.append(e["entry_type"], e["customer_token"], e["data"], db_path=db_path)
    return len(entries)


def _submit_hero_form_through_node_b(db_path: Optional[Path | str]) -> int:
    """Sanitize hero's raw form -> add it to the clean interactions -> Node B publishes hero."""
    import sanitize                                  # scripts may use the sanitizer; MCP code never does
    from nodes import interaction

    raw_form = next(f for f in _json(MOCK / "B_interaction/input/form_submissions.json")
                    if f["customer_id"] == HERO_CUSTOMER_ID)
    sanitize.add_interaction(raw_form)                # the same call the B page's form makes

    before = store.count(db_path=db_path)
    if db_path is not None:
        os.environ["GUARDIAN_DB"] = str(db_path)     # Node B writes to the default ledger
    interaction.publish(HERO)
    return store.count(db_path=db_path) - before


def load(stage: str = "start", *, db_path: Optional[Path | str] = None, reset: bool = False) -> int:
    """Load a stage into the ledger and return how many entries were added.

    Refuses to load into a ledger that already has entries unless reset=True (which wipes it
    first), so you can't accidentally mix two demo runs together.
    """
    if store.count(db_path=db_path) > 0:
        if not reset:
            raise SystemExit("The ledger already has entries. Run again with --reset to wipe it "
                             "and load fresh demo data.")
        store.reset(db_path=db_path)

    entries = plan(stage)
    for e in entries:
        created_at = datetime.fromisoformat(e["created_at"]) if e["created_at"] else None
        store.append(e["entry_type"], e["customer_token"], e["data"], created_at=created_at, db_path=db_path)
    return len(entries)


def summary(db_path: Optional[Path | str] = None) -> str:
    """A short description of what's in the ledger, printed after loading."""
    report = verify_chain(db_path)
    types = Counter(e.entry_type for e in store.read(db_path=db_path))
    hero = combined_score(HERO, db_path=db_path)
    lines = [
        f"Ledger: {report.entries_checked} entries, chain {'VALID' if report.valid else 'BROKEN'}, "
        f"head {report.head_hash[:12]}…",
        "  " + ", ".join(f"{n} {t}" for t, n in sorted(types.items())),
        f"Hero {HERO}: {hero.score} {hero.band}, open hardship case: "
        f"{'yes' if has_open_hardship_case(HERO, db_path=db_path) else 'no'}",
        "Quiet Help list: " + (", ".join(f"{c.customer_token} ({c.score})"
                                         for c in quiet_help_candidates(db_path=db_path)) or "nobody"),
        f"Risk Dashboard: {sum(1 for r in risk_dashboard(db_path=db_path))} open promises, "
        f"{sum(1 for r in risk_dashboard(db_path=db_path) if r.urgency == 'OVERDUE')} overdue",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load demo data into the Promise Ledger.")
    parser.add_argument("--stage", choices=STAGES, default="start", help="how far through the story (default: start)")
    parser.add_argument("--reset", action="store_true", help="wipe the existing ledger first")
    parser.add_argument("--db", help="ledger file (default: GUARDIAN_DB or data/guardian.db)")
    parser.add_argument("--step", choices=["hero-form"],
                        help="add one story step to the current ledger instead of loading a stage")
    args = parser.parse_args()

    db = Path(args.db or os.getenv("GUARDIAN_DB", store.DEFAULT_DB))
    if args.step == "hero-form":
        added = submit_hero_form(db_path=db)
        print(f"Hero submitted the hardship form: {added} entries added to {db}.\n")
        print(summary(db))
        return
    added = load(args.stage, db_path=db, reset=args.reset)
    print(f"Loaded stage '{args.stage}' into {db}: {added} entries.\n")
    print(summary(db))


if __name__ == "__main__":
    main()
