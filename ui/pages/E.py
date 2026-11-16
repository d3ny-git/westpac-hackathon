
"""Customer Guardian – Node E Streamlit dashboard.

Human decisions persist in Node C's append-only ledger.
Approved actions are carried out via actions_execute_approved() (re-checked by Node D first).
The caller check uses Node D's policy P3.
"""

from pathlib import Path
import sys
import streamlit as st

# Works when launched as: streamlit run ui/pages/E.py
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nodes.actions import (approve, reject, actions_pending, actions_status,
                           actions_execute_approved, actions_inbox, ExecutionError)
from nodes.ledger import store
from nodes.policy import check_action
from shared.schemas import Recommendation

st.set_page_config(
    page_title="Customer Guardian",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============================================================
# DESIGN
# ============================================================

st.markdown("""
<style>
.stApp {
    background: #f4f6fa;
}

.block-container {
    max-width: 1150px;
    padding-top: 1rem;
    padding-bottom: 1.5rem;
}

h1, h2, h3 {
    color: #172640;
    letter-spacing: -0.03em;
}

h2 {
    font-size: 1.2rem !important;
}

h3 {
    font-size: 1rem !important;
}

.hero {
    background: #172640;
    border-radius: 14px;
    padding: 20px 24px;
    margin-bottom: 16px;
}

.hero-title {
    color: white;
    font-size: 24px;
    font-weight: 700;
}

.hero-subtitle {
    color: #b7c5d9;
    font-size: 12px;
    margin-top: 5px;
}

div[data-testid="stMetric"] {
    background: white;
    border: 1px solid #e6eaf0;
    border-radius: 12px;
    padding: 12px 16px;
}

div[data-testid="stMetricValue"] {
    font-size: 1.7rem;
    font-weight: 700;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 12px;
}

div.stButton > button {
    border-radius: 8px;
    font-weight: 600;
}

/* GREEN APPROVE BUTTONS */
[class*="st-key-approve_"] button {
    background: #16835d !important;
    border-color: #16835d !important;
    color: white !important;
}

[class*="st-key-approve_"] button:hover {
    background: #106747 !important;
    border-color: #106747 !important;
    color: white !important;
}

/* RED REJECT BUTTONS */
[class*="st-key-reject_"] button {
    background: #c03945 !important;
    border-color: #c03945 !important;
    color: white !important;
}

[class*="st-key-reject_"] button:hover {
    background: #a52d38 !important;
    border-color: #a52d38 !important;
    color: white !important;
}

/* DARK BLUE EXECUTION BUTTONS */
[class*="st-key-execute_"] button {
    background: #172640 !important;
    border-color: #172640 !important;
    color: white !important;
}

[class*="st-key-execute_"] button:hover {
    background: #304565 !important;
    border-color: #304565 !important;
    color: white !important;
}

.phone {
    background: #172640;
    border-radius: 20px;
    padding: 25px;
    text-align: center;
    margin-bottom: 12px;
}

.phone-title {
    color: white;
    font-size: 18px;
    font-weight: 700;
}

.phone-subtitle {
    color: #c2d0e1;
    font-size: 12px;
}

.footer {
    color: #718096;
    font-size: 12px;
    margin-top: 20px;
}

#MainMenu, footer {
    visibility: hidden;
}
</style>
""", unsafe_allow_html=True)


# ============================================================
# LEDGER FUNCTIONS
# ============================================================

def load_recommendations():
    """Load recommendations and their current ledger-backed status."""

    result = []

    for entry in store.read(entry_type="RECOMMENDATION"):
        rec = Recommendation.model_validate(entry.data)

        item = rec.model_dump(mode="json")
        item["status"] = actions_status(rec.rec_id)["status"]

        result.append(item)

    return result


def decide(rec_id, staff, accept):
    """Send a human decision to Node E and persist it in Node C."""

    try:
        if accept:
            result = approve(rec_id, staff)
        else:
            result = reject(rec_id, staff)

    except Exception as exc:
        st.error(f"Ledger write failed: {exc}")
        return

    if "error" in result:
        st.error(result["error"])

    elif "warning" in result:
        st.warning(result["warning"])

    else:
        st.success(
            f"{rec_id}: {result['status']} — saved in ledger"
        )
        st.rerun()


# ============================================================
# HEADER
# ============================================================

st.markdown("""
<div class="hero">
    <div class="hero-title">🛡 Customer Guardian</div>
    <div class="hero-subtitle">
        Node E · Human Approval &amp; Customer Actions ·
        Ledger-connected demo
    </div>
</div>
""", unsafe_allow_html=True)


# ============================================================
# LOAD REAL DATA
# ============================================================

try:
    items = load_recommendations()
    ledger_entries = store.read()

except Exception as exc:
    st.error(f"Unable to read Promise Ledger: {exc}")
    st.stop()


pending = [
    item for item in items
    if item["status"] == "AWAITING_APPROVAL"
]

approved = [
    item for item in items
    if item["status"] == "APPROVED"
]

completed = [
    item for item in items
    if item["status"] == "DONE"
]


# ============================================================
# METRICS
# ============================================================

m1, m2, m3, m4 = st.columns(4)

m1.metric("Pending", len(pending))
m2.metric("Approved", len(approved))
m3.metric("Completed", len(completed))
m4.metric("Total", len(items))


# ============================================================
# NAVIGATION
# ============================================================

tab1, tab2, tab3 = st.tabs([
    "Approval Queue",
    "Customer Experience",
    "Activity & Status",
])


# ============================================================
# TAB 1 – APPROVAL QUEUE
# ============================================================

with tab1:

    left, right = st.columns([1.5, 1], gap="medium")

    with left:

        st.subheader("Approval Queue")

        staff = st.selectbox(
            "Acting staff member",
            ["staff_19c", "staff_44a"],
        )

        if not pending:
            st.success("No recommendations awaiting approval.")

        for item in pending:

            with st.container(border=True):

                action_name = item["recommendation"].replace(
                    "_", " "
                ).title()

                st.markdown(f"**{action_name}**")

                st.caption(
                    f"{item['rec_id']} · {item['customer_token']}"
                )

                st.caption(
                    "Reasons: " + ", ".join(item["why"])
                )

                col_a, col_b = st.columns(2)

                with col_a:

                    if st.button(
                        "✓ Approve",
                        key=f"approve_{item['rec_id']}",
                        width="stretch",
                    ):

                        decide(
                            item["rec_id"],
                            staff,
                            True,
                        )

                with col_b:

                    if st.button(
                        "✕ Reject",
                        key=f"reject_{item['rec_id']}",
                        width="stretch",
                    ):

                        decide(
                            item["rec_id"],
                            staff,
                            False,
                        )

    with right:

        st.subheader("Approved — Awaiting Execution")

        st.caption(
            "Each action is re-checked by Node D's policies "
            "before it is carried out."
        )

        if not approved:
            st.info("No approved actions available.")

        for item in approved:

            with st.container(border=True):

                action_name = item["recommendation"].replace(
                    "_", " "
                ).title()

                st.markdown(f"**{action_name}**")

                st.caption(
                    f"{item['rec_id']} · {item['customer_token']}"
                )

                if st.button(
                    "▶ Execute",
                    key=f"execute_{item['rec_id']}",
                    width="stretch",
                ):

                    try:
                        outcome = actions_execute_approved(item["rec_id"])[0]
                    except ExecutionError as exc:
                        st.error(str(exc))
                    else:
                        if "blocked" in outcome:
                            st.error(
                                f"Blocked by Node D ({outcome['blocked']['policy']}): "
                                f"{outcome['blocked']['reason']}"
                            )
                        else:
                            st.rerun()

        st.caption(
            "Execute writes the action to the ledger and marks it DONE. "
            "The customer sees it in the Customer Experience tab."
        )


# ============================================================
# TAB 2 – CUSTOMER EXPERIENCE
# ============================================================

with tab2:

    st.subheader("Customer Experience")

    customers = sorted({
        item["customer_token"]
        for item in items
    })

    if not customers:

        st.info(
            "No customer recommendations in the ledger yet."
        )

    else:

        customer = st.selectbox(
            "Select customer",
            customers,
        )

        phone_col, verify_col = st.columns(
            2,
            gap="medium",
        )

        with phone_col:

            st.markdown("""
            <div class="phone">
                <div style="color:#b7c5d9;font-size:12px">
                    9:41 · Westpac Mobile
                </div>
                <div style="font-size:36px;margin:14px 0">
                    📱
                </div>
                <div class="phone-title">
                    Customer Notifications
                </div>
                <div class="phone-subtitle">
                    Secure message preview
                </div>
            </div>
            """, unsafe_allow_html=True)

            inbox = actions_inbox(customer)

            if inbox:

                # The lock screen never shows details.
                st.info(inbox[-1]["lock_screen"])

                for n, message in enumerate(inbox):

                    with st.expander(
                        message["in_app_title"],
                        expanded=(n == len(inbox) - 1),
                    ):

                        st.write(message["in_app_body"])

                        if message["kind"] == "QUIET_HELP":

                            for option in message["options"]:

                                st.button(
                                    option.replace("_", " ").title(),
                                    key=f"option_{customer}_{n}_{option}",
                                    disabled=True,
                                    width="stretch",
                                )

                        else:

                            st.write(
                                f"Call booked for "
                                f"{message['meeting_time'][:16].replace('T', ' ')}"
                            )
                            st.code(message["call_code"])

            else:

                st.caption(
                    "No messages have been sent "
                    "to this customer yet."
                )

        with verify_col:

            st.subheader("Caller Verification")

            st.caption(
                "Someone calls the customer saying they're from Westpac. "
                "Type the code the CALLER quotes; Node D's policy P3 checks it "
                "against the calls Westpac really booked."
            )

            # The real code is never shown here: it's only on the customer's phone.
            quoted = st.text_input(
                "Code provided by caller",
                max_chars=12,
                placeholder="e.g. U5PXLW",
                key="verify_code",
            )

            clicked = st.button(
                "Verify Caller",
                key="verify_caller",
                width="stretch",
            )

            if clicked and not quoted.strip():

                st.warning("Type the code the caller quoted first.")

            elif clicked:

                verdict = check_action({
                    "customer_token": customer,
                    "action": "VERIFY_CALLER",
                    "requested_by": staff,
                    "call_code": quoted,
                })

                if verdict.decision == "ALLOW":
                    st.success(f"✅ Genuine Westpac caller. {verdict.reason}")
                else:
                    st.error(f"⛔ Possible scam ({verdict.policy}). {verdict.reason}")

                st.caption("The check is recorded in the ledger.")


# ============================================================
# TAB 3 – ACTIVITY & STATUS
# ============================================================

with tab3:

    st.subheader("Recommendation Status")

    status_rows = [
        {
            "ID": item["rec_id"],
            "Customer": item["customer_token"],
            "Action": item["recommendation"],
            "Status": item["status"],
        }
        for item in items
    ]

    if status_rows:

        st.dataframe(
            status_rows,
            hide_index=True,
            width="stretch",
        )

    else:

        st.caption(
            "No recommendations recorded yet."
        )

    st.subheader("Promise Ledger Activity")

    event_rows = [
        {
            "Entry": entry.entry_id,
            "Type": entry.entry_type,
            "Customer": entry.customer_token,
            "Reference": entry.data.get(
                "rec_id",
                entry.data.get(
                    "ref_id",
                    entry.data.get("promise_id", ""),
                ),
            ),
            "Created": str(entry.created_at),
        }
        for entry in reversed(ledger_entries)
    ]

    if event_rows:

        st.dataframe(
            event_rows,
            hide_index=True,
            width="stretch",
        )

    else:

        st.caption(
            "No ledger activity yet."
        )

    st.caption(
        "The ledger is append-only. "
        "Demo reset is intentionally not available here."
    )


# ============================================================
# FOOTER
# ============================================================

st.markdown("""
<div class="footer">
    Customer Guardian · Node E · Westpac Hackathon Prototype
</div>
""", unsafe_allow_html=True)
