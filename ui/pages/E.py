
"""Node E – Streamlit Actions Dashboard (E3).

Standalone UI prototype with mock data.
Real Node E and ledger integration will follow.
"""

import streamlit as st

st.set_page_config(page_title="Customer Guardian | Actions", layout="wide")

st.title("Customer Guardian")
st.subheader("Node E – Human Approval & Customer Actions")

st.info("Demo mode: actions are simulated, not sent to customers.")

# Temporary demo data until Node E is integrated.
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

st.divider()

st.header("1. Staff Approval Queue")

staff = st.selectbox(
    "Select staff member",
    ["staff_19c", "staff_44a"],
)

pending = [
    item for item in st.session_state.recommendations
    if item["status"] == "AWAITING_APPROVAL"
]

if not pending:
    st.success("No recommendations awaiting approval.")

for item in pending:
    with st.container(border=True):
        st.write(f"**Recommendation:** {item['rec_id']}")
        st.write(f"Customer: {item['customer_token']}")
        st.write(f"Action: {item['recommendation']}")
        st.write(f"Reason: {', '.join(item['why'])}")

        approve_col, reject_col = st.columns(2)

        with approve_col:
            if st.button("Approve", key=f"approve_{item['rec_id']}"):
                item["status"] = "APPROVED"
                st.success(f"{item['rec_id']} approved by {staff}")
                st.rerun()

        with reject_col:
            if st.button("Reject", key=f"reject_{item['rec_id']}"):
                item["status"] = "REJECTED"
                st.warning(f"{item['rec_id']} rejected by {staff}")
                st.rerun()

st.divider()

st.header("2. Execute Approved Actions")

approved = [
    item for item in st.session_state.recommendations
    if item["status"] == "APPROVED"
]

if not approved:
    st.write("No approved actions ready for execution.")

for item in approved:
    if st.button(
        f"Simulate {item['recommendation']} – {item['rec_id']}",
        key=f"execute_{item['rec_id']}",
    ):
        # Demo only. Real execution must re-check Node D policy
        # and confirm approval in Node C's ledger.
        if item["recommendation"] == "QUIET_HELP_PUSH":
            st.session_state.messages.append({
                "customer_token": item["customer_token"],
                "message": "You have a new message from Westpac",
                "options": [
                    "Pause repayments",
                    "Reduce repayments",
                    "Book a call",
                ],
            })

        elif item["recommendation"] == "BOOK_MEETING":
            # Fixed demo code, NOT a real verification code.
            st.session_state.call_codes[item["customer_token"]] = "K7P4QX"

        item["status"] = "DONE"
        st.rerun()

st.divider()

st.header("3. Customer Phone Simulation")

customer = st.selectbox(
    "Select demo customer",
    [item["customer_token"] for item in st.session_state.recommendations],
)

with st.container(border=True):
    st.subheader("Westpac Mobile")

    customer_messages = [
        message for message in st.session_state.messages
        if message["customer_token"] == customer
    ]

    if customer_messages:
        st.info("You have a new message from Westpac")

        with st.expander("Open message"):
            st.write("We are here to help.")
            for option in customer_messages[-1]["options"]:
                st.button(
                    option,
                    key=f"{customer}_{option}",
                    disabled=True,
                    help="Demo display only",
                )
    else:
        st.write("No new messages.")

    if customer in st.session_state.call_codes:
        st.write("Your Westpac caller verification code:")
        st.code(st.session_state.call_codes[customer])

st.divider()

st.header("4. Verify Caller Code")

entered_code = st.text_input(
    "Enter the code provided by the caller",
    max_chars=6,
).strip().upper()

if st.button("Verify Code"):
    expected_code = st.session_state.call_codes.get(customer)

    if not expected_code:
        st.error("No scheduled contact found for this customer.")
    elif entered_code == expected_code:
        st.success("Demo verification: code matches.")
    else:
        st.error("Code does not match.")

st.divider()

st.header("5. Recommendation Status")

st.dataframe(
    st.session_state.recommendations,
    use_container_width=True,
    hide_index=True,
)
