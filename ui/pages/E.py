
"""Customer Guardian – Node E Streamlit dashboard.

Human decisions persist in Node C's append-only ledger.
Execution and caller verification remain disabled until Node D is integrated.
"""

from pathlib import Path
import sys
import streamlit as st

# Works when launched as: streamlit run ui/pages/E.py
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nodes.actions import approve, reject, actions_pending, actions_status
from nodes.ledger import store
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
                        use_container_width=True,
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
                        use_container_width=True,
                    ):

                        decide(
                            item["rec_id"],
                            staff,
                            False,
                        )

    with right:

        st.subheader("Approved — Awaiting Execution")

        st.caption(
            "Approved actions require a fresh Node D "
            "policy check before execution."
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

                st.button(
                    "Execute (Node D required)",
                    key=f"execute_{item['rec_id']}",
                    disabled=True,
                    use_container_width=True,
                )

        st.caption(
            "No customer action is sent from this dashboard yet."
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

            pushes = [
                entry
                for entry in ledger_entries
                if (
                    entry.customer_token == customer
                    and entry.entry_type == "ACTION"
                    and entry.data.get("action") == "QUIET_HELP_PUSH"
                )
            ]

            if pushes:

                st.info(
                    "You have a new message from Westpac"
                )

                with st.expander(
                    "Open message",
                    expanded=True,
                ):

                    st.write("We are here to help.")

                    options = pushes[-1].data.get(
                        "options", []
                    )

                    for option in options:

                        st.button(
                            option.replace("_", " ").title(),
                            key=f"option_{customer}_{option}",
                            disabled=True,
                            use_container_width=True,
                        )

            else:

                st.caption(
                    "No Quiet Help message has been "
                    "executed for this customer."
                )

        with verify_col:

            st.subheader("Caller Verification")

            contacts = [
                entry
                for entry in ledger_entries
                if (
                    entry.customer_token == customer
                    and entry.entry_type == "CONTACT_SCHEDULED"
                )
            ]

            if contacts:

                st.caption(
                    "Customer's in-app call code"
                )

                st.code(
                    contacts[-1].data["call_code"]
                )

            else:

                st.info(
                    "No scheduled contact for this customer."
                )

            st.text_input(
                "Code provided by caller",
                max_chars=6,
                placeholder="Enter 6-character code",
                disabled=True,
            )

            st.button(
                "Verify Caller (Node D required)",
                disabled=True,
                use_container_width=True,
            )

            st.caption(
                "Verification requires Node D policy P3. "
                "Matching text alone is not verification."
            )


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
            use_container_width=True,
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
            use_container_width=True,
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
