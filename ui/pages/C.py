"""Node C – Promise Ledger page (C-9).

    streamlit run ui/pages/C.py          # on its own
    (or as a page of the full app once ui/app.py exists)

Shows:
  1. Integrity: is the ledger untouched? (green/red badge, plus a checkpoint check)
  2. Risk Dashboard: every promise the bank hasn't kept yet
  3. Quiet Help list: who the rules say should get a private nudge
  4. Customer lookup: one customer's combined score, open case and history
  5. The full ledger: every entry with its hash chain

The sidebar has demo controls: load demo data, simulate an insider edit, record a checkpoint.
Everything here is read straight from the ledger with plain Python; no AI is involved.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pandas as pd
import streamlit as st

REPO = Path(__file__).resolve().parents[2]
for p in (REPO, REPO / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import load_fixtures  # noqa: E402
from nodes.ledger import store  # noqa: E402
from nodes.ledger.chain import checkpoint_holds, verify_chain  # noqa: E402
from nodes.ledger.dashboard import risk_dashboard  # noqa: E402
from nodes.ledger.quiet_help import (combined_score, open_hardship_case,  # noqa: E402
                                     quiet_help_candidates)
from shared.config import now  # noqa: E402
from shared.schemas import LedgerEntry  # noqa: E402

URGENCY_ICON = {"OVERDUE": "🔴 OVERDUE", "DUE_SOON": "🟠 DUE SOON", "UPCOMING": "🟢 UPCOMING"}


# ---------------------------------------------------------------------------
# Helpers
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
    """The checkpoint lives next to the ledger it belongs to, e.g. data/guardian_checkpoint.json (gitignored)."""
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
# Page
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Customer Guardian | Ledger", layout="wide")
st.title("Customer Guardian")
st.subheader("Node C – Promise Ledger")
st.caption("**Gets data from:** A (account scores), B (interaction scores + promises), D (decisions, "
           "recommendations), E (actions)  ·  **Sends data to:** D (policy checks) and this Risk Dashboard  ·  "
           f"Demo time: {now():%d %b %Y %H:%M}")

# ---- Sidebar: demo controls ----
with st.sidebar:
    st.header("Demo controls")
    stage = st.selectbox("Story stage", load_fixtures.STAGES, key="stage",
                         help="start = before hero's hardship form · full = after D's recommendations and E's actions")
    if st.button("Load demo data", width="stretch",
                 help="Wipes the demo ledger and loads the chosen stage"):
        load_fixtures.load(stage, reset=True)
        checkpoint_file().unlink(missing_ok=True)
        st.toast(f"Loaded stage '{stage}'")
        st.rerun()
    st.divider()
    if st.button("📌 Record checkpoint", width="stretch",
                 help="Remember the newest entry's hash, so cutting off or rebuilding history is caught later"):
        save_checkpoint(verify_chain())
        st.toast("Checkpoint recorded")
        st.rerun()
    if st.button("⚠️ Simulate insider edit", width="stretch", type="primary",
                 disabled=store.count() == 0,
                 help="DEMO ONLY: removes the protection and lowers the highest score. Reload demo data to undo."):
        changed = simulate_insider_edit()
        st.toast(f"{changed} was quietly edited")
        st.rerun()

if store.count() == 0:
    st.warning("The ledger is empty. Use **Load demo data** in the sidebar "
               "(or run `python scripts/load_fixtures.py`).")
    st.stop()

# ---- 1. Integrity ----
st.header("1. Integrity")
report = verify_chain()
if report.valid:
    st.success(f"✅ **Chain verified**: {report.entries_checked} entries, nothing changed, removed or inserted. "
               f"Newest {report.last_entry_id}, head hash `{report.head_hash[:16]}…`")
else:
    st.error(f"❌ **LEDGER TAMPERED**: {report.problem} at **{report.first_bad_entry}**. {report.detail}")

checkpoint = read_checkpoint()
if checkpoint is None:
    st.caption("No checkpoint recorded yet. Record one in the sidebar to also catch the newest entries "
               "being cut off.")
elif checkpoint_holds(checkpoint["last_entry_id"], checkpoint["head_hash"]):
    st.caption(f"📌 Checkpoint OK: {checkpoint['last_entry_id']} still has hash "
               f"`{checkpoint['head_hash'][:16]}…`, so history up to it is intact.")
else:
    st.error(f"📌 **Checkpoint broken**: {checkpoint['last_entry_id']} no longer has the recorded hash. "
             f"Entries were removed or history was rebuilt since the checkpoint.")

# ---- 2. Risk Dashboard ----
st.header("2. Risk Dashboard")
st.caption("Every promise the bank hasn't kept yet, most at-risk customers first, then soonest due.")
rows = risk_dashboard()
if rows:
    st.dataframe(pd.DataFrame([{
        "Urgency": URGENCY_ICON[r.urgency], "Customer": r.customer_token, "Score": f"{r.score} {r.band}",
        "Promise": f"{r.promise_id} {r.promise_type}", "Due": r.due[:16].replace("T", " "),
        "Hours to due": r.hours_to_due, "Made by": r.made_by, "Description": r.description,
    } for r in rows]), hide_index=True, width="stretch")
else:
    st.info("No open promises.")

# ---- 3. Quiet Help ----
st.header("3. Quiet Help list")
st.caption("HIGH or CRITICAL, no open hardship case, and no Quiet Help push in the last 30 days. "
           "This is only a list: D recommends, and a person approves before anything is sent.")
candidates = quiet_help_candidates()
if candidates:
    st.dataframe(pd.DataFrame([{
        "Customer": c.customer_token, "Score": c.score, "Band": c.band, "Reasons": ", ".join(c.reasons),
        "Last Quiet Help": c.last_quiet_help or "never",
    } for c in candidates]), hide_index=True, width="stretch")
else:
    st.info("Nobody needs a Quiet Help nudge right now.")

# ---- 4. Customer lookup ----
st.header("4. Customer lookup")
entries = store.read()
tokens = sorted({e.customer_token for e in entries})
token = st.selectbox("Customer", tokens, key="customer", index=tokens.index("cust_af4200") if "cust_af4200" in tokens else 0)
score = combined_score(token)
case = open_hardship_case(token)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Combined score", f"{score.score} {score.band}" if score else "not scored")
c2.metric("Account (A)", score.account_score if score and score.account_score is not None else "–")
c3.metric("Interactions (B)", score.interaction_score if score and score.interaction_score is not None else "–")
c4.metric("Open hardship case", f"due {case.due:%d %b}" if case else "no")
if score and score.reasons:
    st.caption("Reasons: " + ", ".join(score.reasons))
st.dataframe(pd.DataFrame([{"Entry": e.entry_id, "Time": e.created_at.strftime("%d %b %H:%M"),
                            "Type": e.entry_type, "What": describe(e)}
                           for e in entries if e.customer_token == token]),
             hide_index=True, width="stretch")

# ---- 5. The full ledger ----
st.header("5. The full ledger")
st.caption("Append-only: entries are never edited or deleted. Each entry's prev hash is the hash of the "
           "entry above it, which is what makes any change detectable.")
f1, f2 = st.columns(2)
type_filter = f1.multiselect("Entry types", sorted({e.entry_type for e in entries}), key="type_filter")
customer_filter = f2.multiselect("Customers", tokens, key="customer_filter")
shown = [e for e in entries
         if (not type_filter or e.entry_type in type_filter)
         and (not customer_filter or e.customer_token in customer_filter)]
table = pd.DataFrame([{"Entry": e.entry_id, "Time": e.created_at.strftime("%d %b %H:%M"),
                       "Customer": e.customer_token, "Type": e.entry_type, "What": describe(e),
                       "Prev hash": e.prev_hash[:10] + "…", "Hash": e.hash[:10] + "…"} for e in shown])


def highlight_bad(row):
    bad = not report.valid and row["Entry"] == report.first_bad_entry
    return ["background-color: rgba(255, 0, 0, 0.25)" if bad else "" for _ in row]


if not table.empty:
    st.dataframe(table.style.apply(highlight_bad, axis=1), hide_index=True, width="stretch")
    with st.expander("Show one entry in full"):
        pick = st.selectbox("Entry", [e.entry_id for e in shown], key="entry_pick")
        st.json(next(e for e in shown if e.entry_id == pick).model_dump(mode="json"))
else:
    st.info("No entries match the filters.")
