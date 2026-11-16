"""Node A – Account page (AB-5).

    streamlit run ui/pages/A.py

Shows:
  1. Raw data -> clean data: which columns are kept and which are dropped, with one customer's
     raw row next to its clean row
  2. Run Node A's workflow (runbooks/a_account.md, with or without the AI) and its step log
  3. Every customer's account score, the reasons and the signals behind them
  4. The SCORE entries Node A has written to the ledger

The raw-data panel is a LOCAL view for the demo (docs/MCP_PLAN.md §6): raw data never goes
through MCP or the AI. Node A itself only ever reads the clean data.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

REPO = Path(__file__).resolve().parents[2]
for p in (REPO, REPO / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import agent  # noqa: E402
import reset_demo  # noqa: E402
import sanitize  # noqa: E402
from nodes import account  # noqa: E402
from nodes.ledger import store  # noqa: E402
from server import build_server  # noqa: E402
from shared.config import CLEAN_TRANSACTION_COLUMNS, now  # noqa: E402

RUNBOOK = REPO / "runbooks" / "a_account.md"


@st.cache_resource
def mcp_server():
    """One in-process MCP server for this page's runbook runs."""
    return build_server()[0]


def show_run(result) -> None:
    box = st.success if result.status == "COMPLETED" else st.error
    box(f"**{result.status}** · {result.runbook} ({result.mode})" + (f"  \n{result.error}" if result.error else ""))
    for s in result.steps:
        with st.expander(f"{'✔' if s.ok else '✘'} Step {s.n}: {s.tool}"):
            st.json(s.output)
    if result.summary:
        st.info(result.summary)


st.set_page_config(page_title="Customer Guardian | Account", layout="wide")
st.title("Customer Guardian")
st.subheader("Node A – Account")
st.caption("**Gets data from:** the bank's transactions (sanitized first: no personal information)  ·  "
           "**Sends data to:** C (an account hardship SCORE per customer)  ·  "
           f"Demo time: {now():%d %b %Y %H:%M}")

with st.sidebar:
    st.header("Demo controls")
    if st.button("🔄 Reset demo (real pipeline)", width="stretch", key="reset",
                 help="Raw data -> sanitize -> Node A and Node B -> a fresh ledger (scripts/reset_demo.py)"):
        reset_demo.reset(quiet=True)
        st.session_state.pop("a_run", None)
        st.toast("Demo reset: A and B have scored everyone")
        st.rerun()

raw_path = sanitize.RAW_DIR / sanitize.RAW_TRANSACTIONS
if not account.clean_file().exists():
    st.warning("There's no clean transaction data yet. Use **Reset demo (real pipeline)** in the sidebar "
               "(or run `python scripts/reset_demo.py`).")
    st.stop()

# ---- 1. Raw -> clean ----
st.header("1. Raw data → clean data")
st.caption("Local view for the demo only: raw data never goes through MCP or the AI. The sanitizer "
           "(plain code) keeps only the allowed columns and swaps the customer ID for a token.")
raw_rows = sanitize.read_csv(raw_path) if raw_path.exists() else []
if raw_rows:
    raw_columns = list(raw_rows[0])
    st.dataframe(pd.DataFrame([{
        "Raw column": c,
        "In clean data": "✅ kept" if c in CLEAN_TRANSACTION_COLUMNS else
                         ("🔁 becomes customer_token" if c == "customer_id" else "❌ dropped (personal information)"),
    } for c in raw_columns]), hide_index=True, width="stretch")

    people = {r["customer_id"]: r["full_name"] for r in raw_rows}
    pick = st.selectbox("Show one customer's first transaction", list(people),
                        format_func=lambda cid: f"{people[cid]} ({cid})", key="sample_customer")
    raw_row = next(r for r in raw_rows if r["customer_id"] == pick)
    clean_row = sanitize.sanitize_transactions([raw_row])[0]
    left, right = st.columns(2)
    left.markdown("**Raw (fake personal information)**")
    left.dataframe(pd.DataFrame(raw_row.items(), columns=["Field", "Value"]), hide_index=True, width="stretch")
    right.markdown("**Clean (what Node A sees)**")
    right.dataframe(pd.DataFrame(clean_row.items(), columns=["Field", "Value"]), hide_index=True, width="stretch")
else:
    st.info(f"No raw file at {raw_path}.")

check = account.check_data()
if check["columns_ok"]:
    st.caption(f"Clean file: {check['rows']} transactions for {check['customers']} customers, "
               f"{check['first_date']} to {check['last_date']}.")
else:
    st.error("The clean transaction file has unexpected columns. Re-run the sanitizer (reset the demo).")

# ---- 2. Run the workflow ----
st.header("2. Run Node A's workflow")
st.caption("`runbooks/a_account.md`: check the data → score everyone → publish to the ledger → verify the "
           "ledger. With the AI, it follows the checklist and writes a summary; without it, the same steps "
           "run directly. Unchanged scores aren't written twice.")
b1, b2 = st.columns(2)
use_ai = None
if b1.button("🤖 Run with the AI", width="stretch", key="run_ai"):
    use_ai = True
if b2.button("⚙️ Run without the AI", width="stretch", key="run_no_ai"):
    use_ai = False
if use_ai is not None:
    with st.spinner("Running Node A's workflow..."):
        st.session_state.a_run = agent.run(RUNBOOK, ai=use_ai, server=mcp_server())
if "a_run" in st.session_state:
    show_run(st.session_state.a_run)

# ---- 3. Scores ----
st.header("3. Account scores")
scores = account.score_all_customers()
rows = account.load_transactions()
published = {e.customer_token: e.data for e in store.read(entry_type="SCORE") if e.data["source"] == "ACCOUNT"}
st.dataframe(pd.DataFrame([{
    "Customer": m.customer_token, "Score": m.score, "Band": m.band, "Reasons": ", ".join(m.reasons) or "–",
    **{k.replace("_", " ").capitalize(): v for k, v in
       account.account_signals([r for r in rows if r.customer_token == m.customer_token]).model_dump().items()},
    "In the ledger": "✅" if published.get(m.customer_token, {}).get("score") == m.score else "not yet",
} for m in sorted(scores, key=lambda m: -m.score)]), hide_index=True, width="stretch")
with st.expander("The rules"):
    st.dataframe(pd.DataFrame(account.RULES), hide_index=True, width="stretch")

# ---- 4. Ledger entries from A ----
st.header("4. Node A's entries in the ledger")
mine = [e for e in store.read(entry_type="SCORE") if e.data["source"] == "ACCOUNT"]
if mine:
    st.dataframe(pd.DataFrame([{"Entry": e.entry_id, "Customer": e.customer_token,
                                "Score": f"{e.data['score']} {e.data['band']}",
                                "Reasons": ", ".join(e.data["reasons"]) or "–"} for e in reversed(mine)]),
                 hide_index=True, width="stretch")
else:
    st.info("Node A hasn't written any scores yet. Run the workflow above.")
