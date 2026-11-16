
# Node E – Actions
# E1: Human approval and rejection

# Temporary demo data until Node C and D are connected
recommendations = {
    "REC-001": {
        "action": "BOOK_MEETING",
        "status": "AWAITING"
    },
    "REC-002": {
        "action": "QUIET_HELP_PUSH",
        "status": "AWAITING"
    }
}


def approve(rec_id, staff):
    """Approve a recommendation by a staff member."""
    if rec_id not in recommendations:
        return {"error": "Recommendation not found"}

    recommendation = recommendations[rec_id]

    if recommendation["status"] != "AWAITING":
        return {"error": "Recommendation already processed"}

    recommendation["status"] = "APPROVED"

    return {
        "rec_id": rec_id,
        "status": "APPROVED",
        "staff": staff
    }


def reject(rec_id, staff):
    """Reject a recommendation by a staff member."""
    if rec_id not in recommendations:
        return {"error": "Recommendation not found"}

    recommendation = recommendations[rec_id]

    if recommendation["status"] != "AWAITING":
        return {"error": "Recommendation already processed"}

    recommendation["status"] = "REJECTED"

    return {
        "rec_id": rec_id,
        "status": "REJECTED",
        "staff": staff
    }


def actions_pending():
    """Return recommendations awaiting approval."""
    return [
        {"rec_id": rec_id, **data}
        for rec_id, data in recommendations.items()
        if data["status"] == "AWAITING"
    ]


def actions_status(rec_id):
    """Return the current recommendation status."""
    if rec_id not in recommendations:
        return {"error": "Recommendation not found"}

    return {
        "rec_id": rec_id,
        "status": recommendations[rec_id]["status"]
    }
