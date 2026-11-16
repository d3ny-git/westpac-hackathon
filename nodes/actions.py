
"""Node E – Actions.

Human approval and rejection backed by the Promise Ledger.
Customer actions are not executed until Node D is integrated.
"""

from nodes.ledger import store
from shared.schemas import Approval, Recommendation, StatusUpdate


def _recommendations():
    """Load actual Node D recommendations from the ledger."""
    result = {}

    for entry in store.read(entry_type="RECOMMENDATION"):
        rec = Recommendation.model_validate(entry.data)
        result[rec.rec_id] = rec

    return result


def _statuses():
    """Reconstruct recommendation statuses from ledger history."""
    recommendations = _recommendations()

    statuses = {
        rec_id: rec.status
        for rec_id, rec in recommendations.items()
    }

    # Ledger entries are ordered oldest first.
    for entry in store.read():
        if entry.entry_type == "APPROVAL":
            rec_id = entry.data["rec_id"]

            if rec_id in statuses:
                statuses[rec_id] = (
                    "APPROVED"
                    if entry.data["approved"]
                    else "REJECTED"
                )

        elif entry.entry_type == "STATUS_UPDATE":
            rec_id = entry.data["ref_id"]

            if rec_id in statuses:
                statuses[rec_id] = entry.data["status"]

    return statuses


def _decide(rec_id: str, staff: str, approved: bool) -> dict:
    """Record a human decision in the ledger."""

    recommendations = _recommendations()

    if rec_id not in recommendations:
        return {"error": "Recommendation not found in ledger"}

    statuses = _statuses()

    if statuses[rec_id] != "AWAITING_APPROVAL":
        return {
            "error": "Recommendation already processed",
            "status": statuses[rec_id],
        }

    rec = recommendations[rec_id]

    # Validate staff token and approval data first.
    approval = Approval(
        rec_id=rec_id,
        approved_by=staff,
        approved=approved,
    )

    new_status = "APPROVED" if approved else "REJECTED"

    status_update = StatusUpdate(
        customer_token=rec.customer_token,
        ref_id=rec_id,
        status=new_status,
        updated_by=staff,
    )

    # Persist the actual human decision.
    approval_entry_id = store.append(
        "APPROVAL",
        rec.customer_token,
        approval.model_dump(mode="json"),
    )

    # Record the resulting recommendation status.
    try:
        status_entry_id = store.append(
            "STATUS_UPDATE",
            rec.customer_token,
            status_update.model_dump(mode="json"),
        )
    except Exception as exc:
        # Approval was already written. Do not claim that
        # the whole operation failed or retry automatically.
        return {
            "rec_id": rec_id,
            "status": new_status,
            "approval_entry_id": approval_entry_id,
            "warning": (
                "Approval saved, but STATUS_UPDATE failed: "
                + str(exc)
            ),
        }

    return {
        "rec_id": rec_id,
        "status": new_status,
        "approval": approval.model_dump(mode="json"),
        "approval_entry_id": approval_entry_id,
        "status_entry_id": status_entry_id,
    }


def approve(rec_id: str, staff: str) -> dict:
    """Approve a recommendation after a human UI action."""
    return _decide(rec_id, staff, approved=True)


def reject(rec_id: str, staff: str) -> dict:
    """Reject a recommendation after a human UI action."""
    return _decide(rec_id, staff, approved=False)


def actions_pending() -> list[dict]:
    """Return recommendations still awaiting approval."""

    recommendations = _recommendations()
    statuses = _statuses()

    return [
        rec.model_dump(mode="json")
        for rec_id, rec in recommendations.items()
        if statuses[rec_id] == "AWAITING_APPROVAL"
    ]


def actions_status(rec_id: str) -> dict:
    """Return the current recommendation status."""

    recommendations = _recommendations()

    if rec_id not in recommendations:
        return {"error": "Recommendation not found"}

    statuses = _statuses()

    return {
        "rec_id": rec_id,
        "status": statuses[rec_id],
    }
