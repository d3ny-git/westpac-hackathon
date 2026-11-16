"""Answers worked out from the ledger: combined score, open hardship cases (C-5) and the
Quiet Help list (C-6).

These are plain Python rules (no AI), calculated from what's in the ledger, so the same
ledger always gives the same answer.

    from nodes.ledger.quiet_help import combined_score, has_open_hardship_case, open_hardship_case

    combined_score("cust_af4200")            # CombinedScore(score=75, band="HIGH", ...) or None
    has_open_hardship_case("cust_af4200")    # True / False
    open_hardship_case("cust_af4200")        # the open HARDSHIP_RESPONSE Promise, or None
    quiet_help_candidates()                  # who should get a Quiet Help push (C-6)

Used by:
    D (policy.py)  P2 needs has_open_hardship_case / open_hardship_case, P4 needs combined_score
    C-6            the Quiet Help list and Risk Dashboard build on these
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from nodes.ledger import store
from shared.config import (HIGH_OR_ABOVE, QUIET_HELP_COOLDOWN, ActionType, EntryType,
                           PromiseStatus, PromiseType, Source, band, now)
from shared.schemas import LedgerEntry, Promise, Recommendation

DbPath = Optional[Path | str]


# ---------------------------------------------------------------------------
# Combined score
# ---------------------------------------------------------------------------
class CombinedScore(BaseModel):
    """One customer's overall hardship score, combining Node A and Node B.

    SPEC: the higher of A and B, plus a quarter of the lower one, capped at 100.
    Example (hero): A=63, B=50  ->  63 + 50/4 = 75.5  ->  75 (HIGH)
    """
    customer_token: str
    account_score: Optional[int]       # latest score from Node A (None if A hasn't scored them)
    interaction_score: Optional[int]   # latest score from Node B (None if B hasn't scored them)
    score: int                         # the combined score, 0-100
    band: str                          # LOW / MODERATE / HIGH / CRITICAL
    reasons: list[str]                 # reason codes from both scores, e.g. SALARY_STOPPED, HARDSHIP_FORM
    based_on: list[str]                # the ledger entries used, e.g. ["E-0001", "E-0012"]


def combine(account: Optional[int], interaction: Optional[int]) -> int:
    """The SPEC formula on its own: max + min/4, rounded down, capped at 100. A missing score counts as 0."""
    a, b = account or 0, interaction or 0
    high, low = max(a, b), min(a, b)
    return min(100, high + low // 4)


def latest_scores(customer_token: str, *, db_path: DbPath = None) -> dict[str, LedgerEntry]:
    """The most recent SCORE entry from each source: {"ACCOUNT": entry, "INTERACTION": entry}.

    A newer score replaces an older one from the same source (the ledger keeps both;
    we just use the latest).
    """
    latest: dict[str, LedgerEntry] = {}
    for entry in store.read(customer_token=customer_token, entry_type=EntryType.SCORE, db_path=db_path):
        latest[entry.data["source"]] = entry          # entries come oldest first, so the last one wins
    return latest


def combined_score(customer_token: str, *, db_path: DbPath = None) -> Optional[CombinedScore]:
    """The customer's combined hardship score, or None if neither A nor B has scored them yet."""
    latest = latest_scores(customer_token, db_path=db_path)
    if not latest:
        return None
    account = latest.get(Source.ACCOUNT.value)
    interaction = latest.get(Source.INTERACTION.value)
    a = account.data["score"] if account else None
    b = interaction.data["score"] if interaction else None
    total = combine(a, b)

    reasons: list[str] = []
    for entry in (account, interaction):
        for reason in (entry.data["reasons"] if entry else []):
            if reason not in reasons:                    # keep order, drop duplicates
                reasons.append(reason)

    return CombinedScore(
        customer_token=customer_token, account_score=a, interaction_score=b,
        score=total, band=band(total).value, reasons=reasons,
        based_on=[e.entry_id for e in (account, interaction) if e],
    )


# ---------------------------------------------------------------------------
# Promises and their current status
# ---------------------------------------------------------------------------
class TrackedPromise(BaseModel):
    """A promise plus where it is now. The PROMISE entry is never edited; later STATUS_UPDATE
    entries (e.g. P-0002 -> KEPT) say what happened to it."""
    promise: Promise
    current_status: str                # OPEN / KEPT / MISSED / CANCELLED
    entry_id: str                      # the PROMISE entry, e.g. "E-0010"
    recorded_at: str                   # when the promise was written to the ledger (ISO)


def tracked_promises(customer_token: Optional[str] = None, *, db_path: DbPath = None) -> list[TrackedPromise]:
    """Every promise (for one customer, or everyone) with its current status, oldest first."""
    entries = store.read(customer_token=customer_token,
                         entry_type=[EntryType.PROMISE, EntryType.STATUS_UPDATE], db_path=db_path)
    tracked: dict[str, TrackedPromise] = {}
    for entry in entries:
        if entry.entry_type == EntryType.PROMISE.value:
            p = Promise(**entry.data)
            tracked[p.promise_id] = TrackedPromise(promise=p, current_status=p.status, entry_id=entry.entry_id,
                                                   recorded_at=entry.created_at.isoformat())
        elif entry.data["ref_id"] in tracked:          # a status update for a promise (R-xxxx ones are skipped)
            tracked[entry.data["ref_id"]].current_status = entry.data["status"]
    return list(tracked.values())


def open_promises(customer_token: Optional[str] = None, *, db_path: DbPath = None) -> list[TrackedPromise]:
    """Promises that haven't been kept, missed or cancelled yet."""
    return [t for t in tracked_promises(customer_token, db_path=db_path)
            if t.current_status == PromiseStatus.OPEN.value]


# ---------------------------------------------------------------------------
# Open hardship case
# ---------------------------------------------------------------------------
def open_hardship_case(customer_token: str, *, db_path: DbPath = None) -> Optional[Promise]:
    """The customer's open hardship case: their most recent HARDSHIP_RESPONSE promise that is
    still OPEN. None if they have no open case.

    A case opens when B records a submitted hardship form (a HARDSHIP_RESPONSE promise, due in
    21 days) and closes when a STATUS_UPDATE marks that promise KEPT, MISSED or CANCELLED.
    """
    cases = [t.promise for t in open_promises(customer_token, db_path=db_path)
             if t.promise.promise_type == PromiseType.HARDSHIP_RESPONSE.value]
    return cases[-1] if cases else None


def has_open_hardship_case(customer_token: str, *, db_path: DbPath = None) -> bool:
    """True if the customer has an open hardship case (see open_hardship_case)."""
    return open_hardship_case(customer_token, db_path=db_path) is not None


# ---------------------------------------------------------------------------
# Quiet Help list (C-6)
# ---------------------------------------------------------------------------
class QuietHelpCandidate(BaseModel):
    """A customer the Quiet Help rule says should get a private push notification."""
    customer_token: str
    score: int                          # combined score
    band: str                           # HIGH or CRITICAL
    reasons: list[str]                  # reason codes behind the score, e.g. SALARY_STOPPED
    last_quiet_help: Optional[str]      # when they last got a Quiet Help push (older than 30 days), or None


def last_quiet_help_push(customer_token: str, *, db_path: DbPath = None) -> Optional[datetime]:
    """When this customer was last sent a Quiet Help push (an ACTION entry from Node E), or None."""
    pushes = [e for e in store.read(customer_token=customer_token, entry_type=EntryType.ACTION, db_path=db_path)
              if e.data.get("action") == ActionType.QUIET_HELP_PUSH.value and "message_id" in e.data]
    return pushes[-1].created_at if pushes else None


def quiet_help_candidates(*, db_path: DbPath = None) -> list[QuietHelpCandidate]:
    """Everyone the Quiet Help rule says to recommend a push for, most at-risk first.

    SPEC rule (all three must be true):
      1. combined score is HIGH or CRITICAL
      2. no open hardship case (they've already asked for help, so a nudge isn't needed)
      3. no Quiet Help push in the last 30 days (don't nag)
    This only produces the list. Node D turns it into recommendations, and a human approves each one.
    """
    cutoff = now() - QUIET_HELP_COOLDOWN
    customers = sorted({e.customer_token for e in store.read(entry_type=EntryType.SCORE, db_path=db_path)})
    candidates: list[QuietHelpCandidate] = []

    for token in customers:
        score = combined_score(token, db_path=db_path)
        if score is None or score.band not in {b.value for b in HIGH_OR_ABOVE}:
            continue                                            # rule 1
        if has_open_hardship_case(token, db_path=db_path):
            continue                                            # rule 2
        last_push = last_quiet_help_push(token, db_path=db_path)
        if last_push is not None and last_push > cutoff:
            continue                                            # rule 3
        candidates.append(QuietHelpCandidate(
            customer_token=token, score=score.score, band=score.band, reasons=score.reasons,
            last_quiet_help=last_push.isoformat() if last_push else None))

    candidates.sort(key=lambda c: (-c.score, c.customer_token))   # highest score first; ties in token order
    return candidates


# ---------------------------------------------------------------------------
# Recommendations and their current status (used by D-4 and Node E)
# ---------------------------------------------------------------------------
class TrackedRecommendation(BaseModel):
    """A recommendation plus where it is now. Like promises, the RECOMMENDATION entry is never
    edited: later APPROVAL and STATUS_UPDATE entries say what happened to it."""
    recommendation: Recommendation
    current_status: str                # AWAITING_APPROVAL / APPROVED / REJECTED / DONE
    entry_id: str                      # the RECOMMENDATION entry, e.g. "E-0021"
    recorded_at: datetime              # when D made the recommendation
    decided_by: Optional[str] = None   # the staff token who approved or rejected it


def tracked_recommendations(customer_token: Optional[str] = None, *,
                            db_path: DbPath = None) -> list[TrackedRecommendation]:
    """Every recommendation (for one customer, or everyone) with its current status, oldest first.

    Status: starts AWAITING_APPROVAL -> an APPROVAL entry makes it APPROVED (or REJECTED) ->
    a STATUS_UPDATE for the R-xxxx id (e.g. from Node E) sets it directly, e.g. DONE.
    """
    entries = store.read(customer_token=customer_token,
                         entry_type=[EntryType.RECOMMENDATION, EntryType.APPROVAL, EntryType.STATUS_UPDATE],
                         db_path=db_path)
    tracked: dict[str, TrackedRecommendation] = {}
    for entry in entries:
        d = entry.data
        if entry.entry_type == EntryType.RECOMMENDATION.value:
            rec = Recommendation(**d)
            tracked[rec.rec_id] = TrackedRecommendation(recommendation=rec, current_status=rec.status,
                                                        entry_id=entry.entry_id, recorded_at=entry.created_at)
        elif entry.entry_type == EntryType.APPROVAL.value and d["rec_id"] in tracked:
            t = tracked[d["rec_id"]]
            t.current_status = "APPROVED" if d["approved"] else "REJECTED"
            t.decided_by = d["approved_by"]
        elif entry.entry_type == EntryType.STATUS_UPDATE.value and d["ref_id"] in tracked:
            tracked[d["ref_id"]].current_status = d["status"]      # P-xxxx updates are skipped
    return list(tracked.values())
