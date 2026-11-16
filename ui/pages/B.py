"""Node B – Interactions page with the mock input form (B5).

    streamlit run ui/pages/B.py

Shows:
  1. The mock input form: a customer calls, chats, emails or fills in a form. Type it in as it
     would really arrive, fake personal information included.
  2. On submit: what the sanitizer KEPT vs THREW AWAY (the text becomes keyword flags, then is
     deleted), then Node B's workflow (runbooks/b_interaction.md) runs for that customer
  3. The promises the bank has made to that customer, as they now are in the ledger
  4. All clean interactions (tokens and flags only) and Node B's ledger entries

The raw panels are a LOCAL view for the demo (docs/MCP_PLAN.md §6): raw data never goes through
MCP or the AI. Node B itself only ever reads the clean data.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, time, timedelta
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
from nodes import interaction  # noqa: E402
from nodes.ledger import store  # noqa: E402
from nodes.ledger.quiet_help import combined_score, has_open_hardship_case  # noqa: E402
from server import build_server  # noqa: E402
from shared.config import CLEAN_INTERACTIONS_FILE, Channel, FormStatus, InteractionType, clean_dir, now  # noqa: E402

RUNBOOK = REPO / "runbooks" / "b_interaction.md"
EXAMPLES = REPO / "mock_input_output" / "B_interaction" / "input" / "form_submissions.json"
NO_STAFF = "— self-service (no staff member)"


@st.cache_resource
def mcp_server():
    """One in-process MCP server for this page's runbook runs."""
    return build_server()[0]


def fake_customers() -> dict[str, dict]:
    """The (fake) customers in the raw bank data: customer_id -> name, email, phone."""
    rows = sanitize.read_csv(sanitize.RAW_DIR / sanitize.RAW_TRANSACTIONS)
    return {r["customer_id"]: {"full_name": r["full_name"], "email": r["email"], "phone": r["phone"]} for r in rows}


def fake_staff() -> dict[str, str]:
    """The (fake) staff in the raw interaction history: staff_id -> name."""
    rows = sanitize.read_csv(sanitize.RAW_DIR / sanitize.RAW_INTERACTIONS)
    return {r["staff_id"]: r["staff_name"] for r in rows if r["staff_id"]}


def prefill(example: dict) -> None:
    """Put a mock submission (from mock_input_output) into the form fields."""
    st.session_state.f_customer = example["customer_id"]
    st.session_state.f_staff = example["staff_id"] or NO_STAFF
    st.session_state.f_date = datetime.fromisoformat(example["date"]).date()
    st.session_state.f_channel = example["channel"]
    st.session_state.f_type = example["type"]
    st.session_state.f_status = example["form_status"] or FormStatus.SUBMITTED.value
    st.session_state.f_text = example["text"]


st.set_page_config(page_title="Customer Guardian | Interactions", layout="wide")
st.title("Customer Guardian")
st.subheader("Node B – Interactions")
st.caption("**Gets data from:** customers' calls, chats, emails and forms (sanitized first: no personal "
           "information)  ·  **Sends data to:** C (an interaction hardship SCORE and the PROMISES the bank "
           f"made)  ·  Demo time: {now():%d %b %Y %H:%M}")

with st.sidebar:
    st.header("Demo controls")
    if st.button("🔄 Reset demo (real pipeline)", width="stretch", key="reset",
                 help="Raw data -> sanitize -> Node A and Node B -> a fresh ledger (scripts/reset_demo.py)"):
        reset_demo.reset(quiet=True)
        st.session_state.pop("submission", None)
        st.toast("Demo reset: A and B have scored everyone")
        st.rerun()

if not (clean_dir() / CLEAN_INTERACTIONS_FILE).exists():
    st.warning("There's no clean interaction data yet. Use **Reset demo (real pipeline)** in the sidebar "
               "(or run `python scripts/reset_demo.py`).")
    st.stop()

customers, staff = fake_customers(), fake_staff()
examples = json.loads(EXAMPLES.read_text())
# Form defaults, set once (the "Fill in" buttons below change them).
st.session_state.setdefault("f_date", now().date())
st.session_state.setdefault("f_due_day", now().date() + timedelta(days=2))
st.session_state.setdefault("f_due_time", time(14, 0))

# ---- 1. The mock input form ----
st.header("1. Mock input form")
st.caption("Type an interaction as it would really reach the bank, personal details and all. "
           "Only the sanitized version ever reaches Node B, the ledger or the AI.")
e1, e2 = st.columns(2)
if e1.button("📝 Fill in: hero's hardship form (SPEC step 6)", width="stretch", key="example_hero"):
    prefill(examples[0])
if e2.button("💬 Fill in: steady_bnpl's chat", width="stretch", key="example_chat"):
    prefill(examples[1])

c1, c2, c3 = st.columns(3)
customer_id = c1.selectbox("Customer", list(customers), key="f_customer",
                           format_func=lambda cid: f"{customers[cid]['full_name']} ({cid})")
staff_id = c2.selectbox("Handled by", [NO_STAFF, *staff], key="f_staff",
                        format_func=lambda sid: sid if sid == NO_STAFF else f"{staff[sid]} ({sid})")
when = c3.date_input("Date", key="f_date")
c4, c5, c6 = st.columns(3)
channel = c4.selectbox("Channel", [c.value for c in Channel], key="f_channel")
kind = c5.selectbox("Type", [t.value for t in InteractionType], key="f_type")
form_status, callback_due = "", ""
if kind == InteractionType.HARDSHIP_FORM.value:
    form_status = c6.selectbox("Form status", [s.value for s in FormStatus], key="f_status")
elif kind == InteractionType.CALLBACK_REQUEST.value:
    due_day = c6.date_input("Call back on", key="f_due_day")
    due_time = st.time_input("Call back at", key="f_due_time")
    callback_due = datetime.combine(due_day, due_time).isoformat(timespec="seconds")
text = st.text_area("What the customer said / wrote", key="f_text", height=110,
                    placeholder="e.g. Hi, it's Jane Citizen. I lost my job and can't afford my repayments...")
use_ai = st.checkbox("Run Node B's workflow with the AI (slower; needs the .env key)", key="f_ai")

if st.button("Submit to Node B", type="primary", key="submit"):
    person = customers[customer_id]
    raw = {"customer_id": customer_id, **person,
           "staff_id": "" if staff_id == NO_STAFF else staff_id,
           "staff_name": "" if staff_id == NO_STAFF else staff[staff_id],
           "date": when.isoformat(), "channel": channel, "type": kind,
           "form_status": form_status, "callback_due": callback_due, "text": text}
    clean = sanitize.add_interaction(raw)                            # sanitize, then store ONLY the clean row
    with st.spinner("Running Node B's workflow..."):
        run = agent.run(RUNBOOK, {"token": clean["customer_token"]}, ai=use_ai, server=mcp_server())
    st.session_state.submission = {"raw": raw, "clean": clean, "run": run}

# ---- 2. Kept vs thrown away, and the workflow run ----
if "submission" in st.session_state:
    sub = st.session_state.submission
    raw, clean, run = sub["raw"], sub["clean"], sub["run"]
    st.header("2. What the sanitizer kept and threw away")
    left, right = st.columns(2)
    left.markdown("**✅ Kept (all Node B ever sees)**")
    left.dataframe(pd.DataFrame(clean.items(), columns=["Field", "Value"]), hide_index=True, width="stretch")
    right.markdown("**❌ Thrown away (local view only)**")
    dropped = {k: v for k, v in raw.items() if k not in clean and v}
    right.dataframe(pd.DataFrame(dropped.items(), columns=["Field", "Value"]), hide_index=True, width="stretch")
    right.caption(f"The text became the flags `{clean['flags'] or 'none'}` and was deleted.")

    st.subheader("Node B's workflow")
    box = st.success if run.status == "COMPLETED" else st.error
    box(f"**{run.status}** · b_interaction for {clean['customer_token']} ({run.mode})"
        + (f"  \n{run.error}" if run.error else ""))
    for s in run.steps:
        with st.expander(f"{'✔' if s.ok else '✘'} Step {s.n}: {s.tool}"):
            st.json(s.output)
    if run.summary:
        st.info(run.summary)

    # ---- 3. The customer's promises, as they now are ----
    token = clean["customer_token"]
    st.header(f"3. {token} now")
    score = combined_score(token)
    m1, m2, m3 = st.columns(3)
    m1.metric("Combined score", f"{score.score} {score.band}" if score else "not scored")
    m2.metric("Interaction score (B)", score.interaction_score if score and score.interaction_score is not None else "–")
    m3.metric("Open hardship case", "yes" if has_open_hardship_case(token) else "no")
    promises = interaction.customer_promises(token)
    if promises:
        st.dataframe(pd.DataFrame([{"Promise": p["promise_id"] or "not published", "Type": p["promise_type"],
                                    "Due": p["due"][:16].replace("T", " "), "Made by": p["made_by"],
                                    "Description": p["description"]} for p in promises]),
                     hide_index=True, width="stretch")
    else:
        st.caption("No promises for this customer.")

# ---- 4. All clean interactions and B's ledger entries ----
st.header("4. Clean interaction data and Node B's ledger entries")
clean_rows = sanitize.read_csv(clean_dir() / CLEAN_INTERACTIONS_FILE)
st.caption(f"`data/clean/interactions.csv`: {len(clean_rows)} interactions, tokens and keyword flags only "
           "(no names, contact details or text).")
st.dataframe(pd.DataFrame(clean_rows), hide_index=True, width="stretch")
mine = [e for e in store.read(entry_type=["SCORE", "PROMISE"])
        if e.entry_type == "PROMISE" or e.data["source"] == "INTERACTION"]
if mine:
    st.dataframe(pd.DataFrame([{
        "Entry": e.entry_id, "Customer": e.customer_token, "Type": e.entry_type,
        "What": (f"score {e.data['score']} {e.data['band']} ({', '.join(e.data['reasons']) or 'no signals'})"
                 if e.entry_type == "SCORE" else
                 f"{e.data['promise_id']} {e.data['promise_type']} due {e.data['due'][:16].replace('T', ' ')}"),
    } for e in reversed(mine)]), hide_index=True, width="stretch")
