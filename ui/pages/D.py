"""Node D – Policy Agent page (D-9).

    streamlit run ui/pages/D.py          # on its own
    (or as a page of the full app once ui/app.py exists)

Shows:
  1. Check an action: ask D whether an action is allowed (ALLOW / BLOCK, policy, reason)
  2. Deadlines (P1): promises that are overdue or due within 24 hours
  3. Recommendations: everything D has suggested and where each one is now
  4. Decisions: every ALLOW / BLOCK D has recorded
  5. Explain: pick any decision or recommendation and see why (facts, plus an AI explanation)
  6. Policy sweep: run the policy_sweep runbook (with or without the AI) and replay past runs

The rules are plain Python; the AI only runs the sweep's checklist and explains. Nothing here can
approve a recommendation: that's a person's job in Node E.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

REPO = Path(__file__).resolve().parents[2]
for p in (REPO, REPO / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import agent  # noqa: E402
import load_fixtures  # noqa: E402
from nodes.ledger import store  # noqa: E402
from nodes.ledger.quiet_help import tracked_recommendations  # noqa: E402
from nodes.policy import check_action, check_deadlines, explain, explain_in_words  # noqa: E402
from shared.config import COLLECTIONS_ACTIONS, CREDIT_OFFER_ACTIONS, ActionType, now  # noqa: E402

SWEEP = REPO / "runbooks" / "policy_sweep.md"
STAFF = ["staff_44a", "staff_19c", "staff_b38", "staff_9bb"]
CHECKABLE = [a.value for a in (*COLLECTIONS_ACTIONS, *CREDIT_OFFER_ACTIONS)] + [ActionType.VERIFY_CALLER.value]
LEVEL_ICON = {"ESCALATE": "🔴 ESCALATE", "ALERT": "🟠 ALERT"}
STATUS_ICON = {"AWAITING_APPROVAL": "⏳ Awaiting approval", "APPROVED": "👍 Approved", "REJECTED": "✋ Rejected",
               "DONE": "✅ Done"}


def show_decision(d) -> None:
    """A decision as a green or red box."""
    if d["decision"] == "ALLOW":
        st.success(f"✅ **ALLOW** · {d['action']} for {d['customer_token']}  \n{d['reason']}")
    else:
        flags = f" · ⚠️ {', '.join(d['flags'])}" if d.get("flags") else ""
        st.error(f"⛔ **BLOCK ({d['policy']})** · {d['action']} for {d['customer_token']}{flags}  \n{d['reason']}")


def run_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Customer Guardian | Policy", layout="wide")
st.title("Customer Guardian")
st.subheader("Node D – Policy Agent")
st.caption("**Gets data from:** C (the ledger: scores, promises, booked calls)  ·  **Sends data to:** "
           "E (recommendations for a person to approve) and C (every decision is recorded)  ·  "
           f"Demo time: {now():%d %b %Y %H:%M}")

with st.sidebar:
    st.header("Demo controls")
    stage = st.selectbox("Story stage", load_fixtures.STAGES, key="stage",
                         help="start = before hero's hardship form · full = after D's recommendations and E's actions")
    if st.button("Load demo data", width="stretch", help="Wipes the demo ledger and loads the chosen stage"):
        load_fixtures.load(stage, reset=True)
        st.session_state.pop("last_decision", None)
        st.session_state.pop("last_run", None)
        st.toast(f"Loaded stage '{stage}'")
        st.rerun()
    st.divider()
    submitted = store.count() > 0 and load_fixtures.hero_form_submitted()
    st.caption("✅ Hero's hardship form is in the ledger" if submitted else
               "SPEC step 6: hero submits a hardship form on the **B page** (Node B's mock input form).")

if store.count() == 0:
    st.warning("The ledger is empty. Use **Load demo data** in the sidebar "
               "(or run `python scripts/load_fixtures.py`).")
    st.stop()

entries = store.read()
tokens = sorted({e.customer_token for e in entries})

# ---- 1. Check an action ----
st.header("1. Check an action")
st.caption("Before the bank does something to a customer, it asks D. P2: no collections during an open "
           "hardship case · P3: a caller must quote the booked call code · P4: no credit offers to HIGH or "
           "CRITICAL customers. Every answer is recorded in the ledger.")
with st.form("check"):
    c1, c2, c3 = st.columns(3)
    token = c1.selectbox("Customer", tokens, key="check_customer",
                         index=tokens.index("cust_af4200") if "cust_af4200" in tokens else 0)
    action = c2.selectbox("Action", CHECKABLE, key="check_action")
    staff = c3.selectbox("Requested by", STAFF, key="check_staff")
    code = st.text_input("Call code the caller quoted (only for VERIFY_CALLER)", key="check_code", max_chars=12)
    if st.form_submit_button("Check with D", type="primary"):
        try:
            decision = check_action({"customer_token": token, "action": action, "requested_by": staff,
                                     "call_code": code or None})
            new_entry = store.read()[-1].entry_id
            st.session_state.last_decision = (new_entry, decision.model_dump(mode="json"))
            st.session_state.explain_pick = new_entry       # section 5 jumps to the decision just made
        except ValueError as exc:                     # e.g. VERIFY_CALLER with no code
            st.session_state.pop("last_decision", None)
            st.warning(f"Can't check that: {str(exc).splitlines()[-1].strip()}")
if "last_decision" in st.session_state:
    entry_id, d = st.session_state.last_decision
    show_decision(d)
    st.caption(f"Recorded in the ledger as {entry_id}. Explain it in section 5.")

entries = store.read()          # read again: a check above may have just added a decision

# ---- 2. Deadlines ----
st.header("2. Deadlines (P1)")
st.caption("Open promises that are overdue (escalate) or due within 24 hours (alert). Read-only.")
alerts = check_deadlines()
if alerts:
    st.dataframe(pd.DataFrame([{"Level": LEVEL_ICON[a.level], "Customer": a.customer_token,
                                "Promise": f"{a.promise_id} {a.promise_type}", "Due": f"{a.due:%d %b %H:%M}",
                                "Hours to due": a.hours_to_due, "Reason": a.reason} for a in alerts]),
                 hide_index=True, width="stretch")
else:
    st.success("No promises are overdue or due within 24 hours.")

# ---- 3. Recommendations ----
st.header("3. Recommendations")
st.caption("What D has suggested. Nothing reaches a customer until a person approves it in Node E. "
           "Run the policy sweep (section 6) to create new ones.")
recs = tracked_recommendations()
if recs:
    st.dataframe(pd.DataFrame([{"Rec": t.recommendation.rec_id, "Customer": t.recommendation.customer_token,
                                "Recommendation": t.recommendation.recommendation,
                                "Why": ", ".join(t.recommendation.why), "Status": STATUS_ICON[t.current_status],
                                "Decided by": t.decided_by or "", "Made": f"{t.recorded_at:%d %b %H:%M}"}
                               for t in recs]), hide_index=True, width="stretch")
else:
    st.info("No recommendations yet. Run the policy sweep in section 6.")

# ---- 4. Decisions ----
st.header("4. Decisions")
decisions = [e for e in entries if e.entry_type in ("BLOCKED", "ACTION") and "decision" in e.data]
if decisions:
    st.dataframe(pd.DataFrame([{"Entry": e.entry_id, "Time": f"{e.created_at:%d %b %H:%M}",
                                "Customer": e.customer_token, "Action": e.data["action"],
                                "Decision": ("✅ ALLOW" if e.data["decision"] == "ALLOW" else f"⛔ BLOCK ({e.data['policy']})"),
                                "Reason": e.data["reason"]} for e in reversed(decisions)]),
                 hide_index=True, width="stretch")
else:
    st.info("No decisions yet. Check an action in section 1.")

# ---- 5. Explain ----
st.header("5. Explain a decision or recommendation")
explainable = [e for e in entries if e.entry_type == "RECOMMENDATION" or e in decisions]
if explainable:
    labels = {e.entry_id: f"{e.entry_id} · {e.customer_token} · " + (
        f"recommend {e.data['recommendation']}" if e.entry_type == "RECOMMENDATION"
        else f"{e.data['action']} → {e.data['decision']}") for e in reversed(explainable)}
    pick = st.selectbox("Pick one", list(labels), format_func=labels.get, key="explain_pick")
    facts = explain(pick)
    st.markdown(f"**Rule:** {facts.rule}")
    cols = st.columns(4)
    f = facts.facts
    cols[0].metric("Combined score at the time", f"{f['combined_score']} {f['band']}" if f["combined_score"] is not None else "–")
    cols[1].metric("Open hardship case", f"due {f['open_hardship_case']['due'][:10]}" if f["open_hardship_case"] else "no")
    cols[2].metric("Overdue promises", len(f["overdue_promises"]))
    cols[3].metric("Calls booked", f["calls_booked"])
    if st.button("🤖 Explain in plain English (AI)", key="explain_ai"):
        with st.spinner("Asking the AI to explain the facts..."):
            try:
                st.session_state.explanation = (pick, explain_in_words(pick))
            except Exception as exc:              # no key / no network: the facts are still shown below
                st.session_state.explanation = (pick, f"⚠️ The AI couldn't be reached ({type(exc).__name__}). "
                                                       f"The facts below are the full explanation.")
    if st.session_state.get("explanation", (None,))[0] == pick:
        st.info(st.session_state.explanation[1])
    with st.expander("All facts and the ledger entries it relied on (call codes hidden)"):
        st.json(facts.model_dump())
else:
    st.info("Nothing to explain yet: check an action or run the policy sweep.")

# ---- 6. Policy sweep ----
st.header("6. Policy sweep")
st.caption("Runs `runbooks/policy_sweep.md`: verify the ledger (stops if tampered) → deadlines → Quiet Help "
           "list → create recommendations. With the AI, it follows the checklist and writes a summary; "
           "without it, the same steps run directly. Both leave the ledger identical.")
b1, b2 = st.columns(2)
use_ai = None
if b1.button("🤖 Run sweep with the AI", width="stretch", key="sweep_ai"):
    use_ai = True
if b2.button("⚙️ Run sweep without the AI", width="stretch", key="sweep_no_ai"):
    use_ai = False
if use_ai is not None:
    with st.spinner("Running the policy sweep..."):
        st.session_state.last_run = agent.run(SWEEP, ai=use_ai).run_id
    st.rerun()

# Only policy sweeps: other runbooks (e.g. A's and B's, run by reset_demo.py) log here too.
runs = sorted(agent.RUNS_DIR.glob("*-policy_sweep-*.jsonl"), reverse=True) if agent.RUNS_DIR.exists() else []
if runs:
    names = [p.stem for p in runs]
    default = names.index(st.session_state["last_run"]) if st.session_state.get("last_run") in names else 0
    chosen = st.selectbox("Run log", names, index=default, key="run_pick")
    events = run_events(agent.RUNS_DIR / f"{chosen}.jsonl")
    finish = next((e for e in events if e["event"] == "finish"), {})
    status = finish.get("status", "RUNNING")
    box = st.success if status == "COMPLETED" else st.error
    box(f"**{status}** · {chosen}")
    for e in events:
        if e["event"] == "step":
            with st.expander(f"{'✔' if e['ok'] else '✘'} Step {e['n']}: {e['tool']}"):
                st.json(e["output"])
        elif e["event"] == "off_script":
            st.error(f"OFF SCRIPT at step {e['step']}: the AI called {e['called']}, the runbook says {e['expected']}")
        elif e["event"] == "stopped":
            st.error(f"Stopped at step {e['step']} ({e['rule']})")
    if finish.get("summary"):
        st.markdown("**Summary**")
        st.info(finish["summary"])
    if finish.get("error") and status != "STOPPED":
        st.caption(finish["error"])
else:
    st.info("No sweeps have run yet.")
