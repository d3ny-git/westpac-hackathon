"""Reset the demo by running the REAL pipeline: raw data -> sanitize -> Nodes A and B -> ledger.

    python scripts/reset_demo.py          # runbooks without the AI (fast, no key needed)
    python scripts/reset_demo.py --ai     # A's and B's runbooks run with the AI (slower)
    python scripts/reset_demo.py --empty  # steps 1, 2 and 5 only: run A and B yourself on their pages

Steps (docs/MCP_PLAN.md, E5):
  1. sanitize      data/raw/*.csv (fake PII)  ->  data/clean/*.csv (tokens only)
  2. fresh ledger  wipe the demo ledger; add the one older event the mock data doesn't produce
                   (recent_push's Quiet Help push 12 days ago, from data/fixtures/seed_extras.json)
  3. Node A        runbooks/a_account.md      every customer's account score
  4. Node B        runbooks/b_interaction.md  once per customer: interaction score + promises
  5. PII check     no fake name, email, phone, DOB, address, BSB, account number or text from
                   data/raw may appear in data/clean, the ledger or the run logs (plan, Verification 2)

The result is the SPEC's starting point: hero (cust_af4200) is 63 HIGH with no open case, so
D's first sweep recommends a Quiet Help push. This is the same story state as
`load_fixtures.py --stage start`, but now built by A and B themselves.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import agent  # noqa: E402
import load_fixtures  # noqa: E402
import sanitize  # noqa: E402
from nodes.ledger import store  # noqa: E402
from server import build_server  # noqa: E402
from shared.config import CLEAN_INTERACTIONS_FILE, clean_dir  # noqa: E402

RUNBOOKS = REPO / "runbooks"
EXTRAS = REPO / "data" / "fixtures" / "seed_extras.json"
PII_COLUMNS = ["customer_id", "full_name", "email", "phone", "dob", "address", "bsb", "account_number",
               "description", "staff_id", "staff_name", "text"]


class ResetError(RuntimeError):
    """A step of the reset failed; the message says which and why."""


def raw_pii_values(raw_dir: Path) -> set[str]:
    """Every personal value in the raw files (whole values, plus each part of a name)."""
    values: set[str] = set()
    for name in (sanitize.RAW_TRANSACTIONS, sanitize.RAW_INTERACTIONS):
        for row in sanitize.read_csv(raw_dir / name):
            for col in PII_COLUMNS:
                value = (row.get(col) or "").strip()
                if value:
                    values.add(value)
                    if col in ("full_name", "staff_name"):
                        values.update(value.split())
    return {v for v in values if len(v) > 2}


def pii_leaks(raw_dir: Path, places: list[str]) -> int:
    """How many raw personal values appear in the given texts (the values themselves are never printed)."""
    blob = "\n".join(places)
    return sum(1 for v in raw_pii_values(raw_dir) if re.search(rf"(?<![\w]){re.escape(v)}(?![\w])", blob))


def _run(runbook: str, server, ai: bool, variables=None) -> agent.RunResult:
    result = agent.run(RUNBOOKS / runbook, variables, ai=ai, server=server)
    if result.status != "COMPLETED":
        who = f" for {variables['token']}" if variables else ""
        raise ResetError(f"{runbook}{who} ended {result.status}: {result.error or result.summary}")
    return result


def run_node_a(server, ai: bool = False) -> agent.RunResult:
    """Node A's workflow (runbooks/a_account.md) for every customer."""
    return _run("a_account.md", server, ai)


def run_node_b_for_everyone(server, ai: bool = False) -> list[agent.RunResult]:
    """Node B's workflow (runbooks/b_interaction.md) once per customer in the clean interactions,
    in token order. Used by the reset and by the B page's "Run Node B for all customers" button."""
    tokens = sorted({r["customer_token"] for r in sanitize.read_csv(clean_dir() / CLEAN_INTERACTIONS_FILE)})
    return [_run("b_interaction.md", server, ai, {"token": token}) for token in tokens]


def reset(*, ai: bool = False, raw_dir: Path = sanitize.RAW_DIR, quiet: bool = False, empty: bool = False) -> dict:
    """Run the whole reset. Returns a small report; raises ResetError if any step fails.

    empty=True stops after the fresh ledger: the clean data is ready, but Nodes A and B haven't
    run yet, so the ledger holds only the one older event. Run A and B on their pages to fill it."""
    say = (lambda *a: None) if quiet else print
    started = datetime.now()                                   # only to find this reset's run logs

    # 1. Sanitize raw -> clean.
    counts = sanitize.sanitize_all(raw_dir)
    say(f"1. Sanitized: {counts[sanitize.CLEAN_TRANSACTIONS]} transactions, "
        f"{counts[sanitize.CLEAN_INTERACTIONS]} interactions -> {clean_dir()}")

    # 2. Fresh ledger, plus the older events A and B don't produce.
    store.reset()
    store.db_file().with_name(f"{store.db_file().stem}_checkpoint.json").unlink(missing_ok=True)
    for e in json.loads(EXTRAS.read_text())["before_scores"]:
        store.append(e["entry_type"], e["customer_token"], e["data"],
                     created_at=datetime.fromisoformat(e["created_at"]) if e.get("created_at") else None)
    say("2. Fresh ledger (plus recent_push's Quiet Help push from 12 days ago)")

    # 3 + 4. Nodes A and B, through their runbooks, on one in-process MCP server.
    customers = promises = 0
    if empty:
        say("3-4. Skipped (--empty): run Node A and Node B on their pages to fill the ledger")
    else:
        server, _ = build_server()
        a = run_node_a(server, ai)
        say(f"3. Node A ({'AI' if ai else 'no AI'}): {a.steps[2].output['written']} account scores written")
        runs = run_node_b_for_everyone(server, ai)
        customers = len(runs)
        promises = sum(len(r.steps[2].output["promises_written"]) for r in runs)
        say(f"4. Node B ({'AI' if ai else 'no AI'}): {customers} customers, {promises} promises written")

    # 5. PII check across everything this reset produced.
    places = [p.read_text() for p in clean_dir().glob("*.csv")]
    places += [json.dumps([e.data for e in store.read()])]
    places += [p.read_text() for p in agent.RUNS_DIR.glob("*.jsonl")
               if p.name != "llm_calls.jsonl" and datetime.fromtimestamp(p.stat().st_mtime) >= started]
    leaks = pii_leaks(raw_dir, places)
    if leaks:
        raise ResetError(f"PII check FAILED: {leaks} personal value(s) from data/raw found in the output")
    say("5. PII check: 0 personal values from data/raw in data/clean, the ledger or the run logs")
    return {"transactions": counts[sanitize.CLEAN_TRANSACTIONS], "customers": customers,
            "promises": promises, "entries": store.count()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset the demo with the real A and B pipeline.")
    parser.add_argument("--ai", action="store_true", help="run A's and B's runbooks with the AI (needs .env)")
    parser.add_argument("--raw", default=str(sanitize.RAW_DIR), help="folder with the raw CSVs (default: data/raw)")
    parser.add_argument("--empty", action="store_true",
                        help="sanitize and start a fresh ledger, but don't run A or B (do that on their pages)")
    args = parser.parse_args()
    try:
        reset(ai=args.ai, raw_dir=Path(args.raw), empty=args.empty)
    except ResetError as exc:
        print(f"RESET FAILED: {exc}")
        return 1
    print()
    if args.empty:
        print(f"Ledger: {store.count()} entry. Next: Run Node A's workflow on the A page, then "
              f"Run Node B for all customers on the B page.")
    else:
        print(load_fixtures.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
