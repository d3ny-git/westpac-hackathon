"""Risk Dashboard: every open promise, most at-risk customers and nearest deadlines first (C-6).

SPEC: "a list of open promises, sorted by hardship score and how close each one is to its
due date." This is the "No promise forgotten" view for bank staff.

    from nodes.ledger.dashboard import risk_dashboard
    for row in risk_dashboard():
        print(row.customer_token, row.promise_type, row.due, row.urgency)

Plain Python, no AI. Reads the ledger; never writes to it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from nodes.ledger.quiet_help import combined_score, open_promises
from shared.config import P1_ALERT_WINDOW, now

DbPath = Optional[Path | str]


class DashboardRow(BaseModel):
    """One open promise on the Risk Dashboard."""
    promise_id: str
    customer_token: str
    promise_type: str                  # CALLBACK, MEETING, HARDSHIP_RESPONSE, ...
    description: str
    made_by: str
    due: str                           # ISO time
    hours_to_due: float                # negative = already overdue
    urgency: str                       # OVERDUE / DUE_SOON (within 24h) / UPCOMING
    score: int                         # the customer's combined hardship score (0 if never scored)
    band: str


def _urgency(hours_to_due: float) -> str:
    if hours_to_due < 0:
        return "OVERDUE"
    if hours_to_due <= P1_ALERT_WINDOW.total_seconds() / 3600:
        return "DUE_SOON"
    return "UPCOMING"


def risk_dashboard(*, db_path: DbPath = None) -> list[DashboardRow]:
    """All open promises, sorted by the customer's combined score (highest first), then by
    how soon each promise is due (overdue and soonest first)."""
    at = now()
    scores: dict[str, tuple[int, str]] = {}     # combined score per customer, worked out once each
    rows: list[DashboardRow] = []

    for tracked in open_promises(db_path=db_path):
        p = tracked.promise
        if p.customer_token not in scores:
            c = combined_score(p.customer_token, db_path=db_path)
            scores[p.customer_token] = (c.score, c.band) if c else (0, "LOW")
        score, band = scores[p.customer_token]
        hours = round((p.due - at).total_seconds() / 3600, 1)
        rows.append(DashboardRow(
            promise_id=p.promise_id, customer_token=p.customer_token, promise_type=p.promise_type,
            description=p.description, made_by=p.made_by, due=p.due.isoformat(),
            hours_to_due=hours, urgency=_urgency(hours), score=score, band=band))

    rows.sort(key=lambda r: (-r.score, r.hours_to_due, r.promise_id))
    return rows
