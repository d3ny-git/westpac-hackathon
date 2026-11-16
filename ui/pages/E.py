
"""Customer Guardian – Node E Dashboard.

Compact Streamlit prototype for the Westpac hackathon.
All actions are simulated until Nodes C, D and E are connected.
"""

import streamlit as st

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
# DEMO DATA
# ============================================================

DEMO_RECOMMENDATIONS = [
    {
        "rec_id": "R-0001",
        "customer_token": "cust_af4200",
        "recommendation": "BOOK_MEETING",
        "why": ["SCORE_HIGH"],
        "status": "AWAITING_APPROVAL",
    },
    {
        "rec_id": "R-0002",
        "customer_token": "cust_bb4b75",
        "recommendation": "QUIET_HELP_PUSH",
        "why": ["SALARY_STOPPED"],
        "status": "AWAITING_APPROVAL",
    },
]

if "recommendations" not in st.session_state:
    st.session_state.recommendations = [
        item.copy() for item in DEMO_RECOMMENDATIONS
    ]

if "messages" not in st.session_state:
    st.session_state.messages = []

if "call_codes" not in st.session_state:
    st.session_state.call_codes = {}

if "audit_events" not in st.session_state:
    st.session_state.audit_events = []


# ============================================================
# FUNCTIONS
# ============================================================

def record_event(rec_id, event, staff):
    st.session_state.audit_events.append({
        "recommendation": rec_id,
        "event": event,
        "staff": staff,
    })


def approve_item(rec_id, staff):
    for item in st.session_state.recommendations:
        if item["rec_id"] == rec_id:
            if item["status"] != "AWAITING_APPROVAL":
                return False

            item["status"] = "APPROVED"
            record_event(rec_id, "APPROVED", staff)
            return True

    return False


def reject_item(rec_id, staff):
    for item in st.session_state.recommendations:
        if item["rec_id"] == rec_id:
            if item["status"] != "AWAITING_APPROVAL":
                return False

            item["status"] = "REJECTED"
            record_event(rec_id, "REJECTED", staff)
            return True

    return False


def execute_item(rec_id):
    """Simulate an action after human approval.

    Real execution requires a ledger approval and policy recheck.
    """

    for item in st.session_state.recommendations:
        if item["rec_id"] != rec_id:
            continue

        if item["status"] != "APPROVED":
            return False

        token = item["customer_token"]
        action = item["recommendation"]

        if action == "QUIET_HELP_PUSH":
            st.session_state.messages.append({
                "customer_token": token,
                "message": "You have a new message from Westpac",
                "options": [
                    "Pause repayments",
                    "Reduce repayments",
                    "Book a call",
                ],
            })

        elif action == "BOOK_MEETING":
            # Demo-only code. Not secure for production.
            st.session_state.call_codes[token] = "K7P4QX"

        else:
            return False

        item["status"] = "DONE"
        record_event(rec_id, "DONE", "DEMO_SYSTEM")
        return True

    return False


# ============================================================
# HEADER
# ============================================================

st.markdown("""
<div class="hero">
    <div class="hero-title">🛡 Customer Guardian</div>
    <div class="hero-subtitle">
        Node E · Human Approval & Customer Actions · Demo
    </div>
</div>
""", unsafe_allow_html=True)

items = st.session_state.recommendations

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
            st.success("All recommendations reviewed.")

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
                        approve_item(item["rec_id"], staff)
                        st.rerun()

                with col_b:
                    if st.button(
                        "✕ Reject",
                        key=f"reject_{item['rec_id']}",
                        use_container_width=True,
                    ):
                        reject_item(item["rec_id"], staff)
                        st.rerun()

    with right:

        st.subheader("Ready to Execute")

        st.caption(
            "Only approved actions can be simulated."
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
                    "Simulate Action",
                    key=f"execute_{item['rec_id']}",
                    use_container_width=True,
                ):
                    if execute_item(item["rec_id"]):
                        st.rerun()
                    else:
                        st.error("Action could not be executed.")

        st.caption(
            "Demo only. No real customer actions are performed."
        )


# ============================================================
# TAB 2 – CUSTOMER EXPERIENCE
# ============================================================

with tab2:

    st.subheader("Customer Experience")

    customer = st.selectbox(
        "Select customer",
        sorted(set(
            item["customer_token"]
            for item in items
        )),
    )

    phone_col, verify_col = st.columns(2, gap="medium")

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

        customer_messages = [
            msg for msg in st.session_state.messages
            if msg["customer_token"] == customer
        ]

        if customer_messages:

            st.info(
                "You have a new message from Westpac"
            )

            with st.expander(
                "Open message",
                expanded=True,
            ):

                st.write("We are here to help.")

                for option in customer_messages[-1]["options"]:
                    st.button(
                        option,
                        key=f"{customer}_{option}",
                        disabled=True,
                        use_container_width=True,
                    )

        else:
            st.caption(
                "No new messages for this customer."
            )

    with verify_col:

        st.subheader("Caller Verification")

        st.caption(
            "Verify a scheduled Westpac contact."
        )

        expected = st.session_state.call_codes.get(
            customer
        )

        if expected:

            with st.container(border=True):
                st.caption("Customer's in-app call code")
                st.code(expected)

        else:
            st.info(
                "No scheduled contact for this customer."
            )

        entered_code = st.text_input(
            "Code provided by caller",
            max_chars=6,
            placeholder="Enter 6-character code",
        ).strip().upper()

        if st.button(
            "Verify Caller",
            use_container_width=True,
        ):

            if not expected:
                st.error(
                    "No scheduled contact found."
                )

            elif entered_code == expected:
                st.success(
                    "Demo verification: code matches."
                )

            else:
                st.error(
                    "Code does not match."
                )

        st.caption(
            "Demo only. Real verification uses Node D policy P3."
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

    st.dataframe(
        status_rows,
        hide_index=True,
        use_container_width=True,
    )

    st.subheader("Demo Activity")

    if st.session_state.audit_events:

        st.dataframe(
            st.session_state.audit_events,
            hide_index=True,
            use_container_width=True,
        )

    else:
        st.caption("No activity recorded yet.")

    if st.button("Reset Demo"):

        for key in [
            "recommendations",
            "messages",
            "call_codes",
            "audit_events",
        ]:
            st.session_state.pop(key, None)

        st.rerun()


# ============================================================
# FOOTER
# ============================================================

st.markdown("""
<div class="footer">
    Customer Guardian · Node E · Westpac Hackathon Prototype
</div>
""", unsafe_allow_html=True)

