

"""Node E – Actions: human approval and rejection.

Temporary in-memory implementation using the shared team schemas.
Ledger integration and action execution will be added later.
"""

from shared.schemas import Recommendation, Approval


# Temporary recommendations until Node D is connected.
recommendations = {
    "R-0001": Recommendation(
        rec_id="R-0001",
        customer_token="cust_af4200",
        recommendation="BOOK_MEETING",
        why=["SCORE_HIGH"],
        status="AWAITING_APPROVAL",
    ),
    "R-0002": Recommendation(
        rec_id="R-0002",
        customer_token="cust_bb4b75",
        recommendation="QUIET_HELP_PUSH",
        why=["SALARY_STOPPED"],
        status="AWAITING_APPROVAL",
    ),
}

# Temporary storage until Node C's ledger is connected.
approvals = {}
statuses = {
    rec_id: rec.status
    for rec_id, rec in recommendations.items()
}


def approve(rec_id: str, staff: str) -> dict:
    """Approve a recommendation by a human staff member."""

    if rec_id not in recommendations:
        return {"error": "Recommendation not found"}

    if statuses[rec_id] != "AWAITING_APPROVAL":
        return {"error": "Recommendation already processed"}

    # Validate the approval against the shared schema.
    approval = Approval(
        rec_id=rec_id,
        approved_by=staff,
        approved=True,
    )

    approvals[rec_id] = approval
    statuses[rec_id] = "APPROVED"

    return {
        "rec_id": rec_id,
        "status": "APPROVED",
        "approval": approval.model_dump(mode="json"),
    }


def reject(rec_id: str, staff: str) -> dict:
    """Reject a recommendation by a human staff member."""

    if rec_id not in recommendations:
        return {"error": "Recommendation not found"}

    if statuses[rec_id] != "AWAITING_APPROVAL":
        return {"error": "Recommendation already processed"}

    approval = Approval(
        rec_id=rec_id,
        approved_by=staff,
        approved=False,
    )

    approvals[rec_id] = approval
    statuses[rec_id] = "REJECTED"

    return {
        "rec_id": rec_id,
        "status": "REJECTED",
        "approval": approval.model_dump(mode="json"),
    }


def actions_pending() -> list[dict]:
    """Return recommendations awaiting human approval."""

    return [
        recommendation.model_dump(mode="json")
        for rec_id, recommendation in recommendations.items()
        if statuses[rec_id] == "AWAITING_APPROVAL"
    ]


def actions_status(rec_id: str) -> dict:
    """Return the current status of a recommendation."""

    if rec_id not in recommendations:
        return {"error": "Recommendation not found"}

    return {
        "rec_id": rec_id,
        "status": statuses[rec_id],
    }

