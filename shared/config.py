"""Shared settings and fixed values for Customer Guardian.

Everything here is a CONSTANT that more than one node relies on. If a value is only used
inside one node (e.g. Node A's +25 for salary stopped), it can live in that node instead.

Anyone can change a value here. Every node sees the change, so give the team a heads-up
(see shared/README.md).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------
# The whole system pretends "now" is this moment. Rules NEVER call datetime.now(),
# so the same data always gives the same answer (deterministic) and the demo is repeatable.
# All times are naive local times (no timezone), matching the SPEC examples.
AS_OF = datetime(2026, 11, 16, 10, 0, 0)


def now() -> datetime:
    """The one clock everyone uses. Always returns AS_OF so results are repeatable."""
    return AS_OF


# ---------------------------------------------------------------------------
# Token formats (what customers and staff look like after sanitizing)
# ---------------------------------------------------------------------------
# A customer is only ever "cust_" + 6 hex characters, e.g. cust_af4200.
CUSTOMER_TOKEN_PATTERN = r"^cust_[0-9a-f]{6}$"
# A staff member is only ever "staff_" + 3 hex characters, e.g. staff_19c.
STAFF_TOKEN_PATTERN = r"^staff_[0-9a-f]{3}$"
# Used as `made_by` / `requested_by` when no person was involved (e.g. a self-service form).
SYSTEM_ACTOR = "SYSTEM"

# ID formats. Numbers are zero-padded to at least 4 digits: E-0001, P-0042, R-0031, M-0007.
ENTRY_ID_PATTERN = r"^E-\d{4,}$"           # ledger entry
PROMISE_ID_PATTERN = r"^P-\d{4,}$"         # promise
REC_ID_PATTERN = r"^R-\d{4,}$"             # recommendation
MESSAGE_ID_PATTERN = r"^M-\d{4,}$"         # Quiet Help message
CALL_CODE_PATTERN = r"^[A-Z0-9]{6}$"       # e.g. K7P4QX, quoted by real Westpac callers
HASH_PATTERN = r"^[0-9a-f]{64}$"           # sha256 hex
REASON_CODE_PATTERN = r"^[A-Z][A-Z0-9_]*$"  # e.g. SALARY_STOPPED, HARDSHIP_FORM

# The prev_hash of the very first ledger entry (there is nothing before it).
GENESIS_HASH = "0" * 64


# ---------------------------------------------------------------------------
# Score bands (SPEC: Node C)
# ---------------------------------------------------------------------------
class Band(str, Enum):
    LOW = "LOW"              # under 30
    MODERATE = "MODERATE"    # 30–59
    HIGH = "HIGH"            # 60–79
    CRITICAL = "CRITICAL"    # 80 or more


# (lowest score for the band, band), checked from the top down.
BAND_CUTOFFS: list[tuple[int, Band]] = [
    (80, Band.CRITICAL),
    (60, Band.HIGH),
    (30, Band.MODERATE),
    (0, Band.LOW),
]

# Bands that count as "HIGH or above" (Quiet Help rule, policy P4).
HIGH_OR_ABOVE = {Band.HIGH, Band.CRITICAL}


def band(score: int) -> Band:
    """Turn a 0–100 score into its band. Example: band(63) -> Band.HIGH."""
    if not 0 <= score <= 100:
        raise ValueError(f"score must be between 0 and 100, got {score}")
    for lowest, name in BAND_CUTOFFS:
        if score >= lowest:
            return name
    raise AssertionError("unreachable")


# ---------------------------------------------------------------------------
# Business rules shared between nodes
# ---------------------------------------------------------------------------
HARDSHIP_RESPONSE_DAYS = 21                    # SPEC: a hardship form starts a 21-day response deadline
P1_ALERT_WINDOW = timedelta(hours=24)          # P1: a promise due within this window is "near"
QUIET_HELP_COOLDOWN = timedelta(days=30)       # Quiet Help: max one push per customer per 30 days
RECOMMENDATION_COOLDOWN = timedelta(days=30)   # D won't repeat the same recommendation to a customer
                                               # within 30 days (e.g. after a person rejected it)
REACHED_OUT_WINDOW_DAYS = 30                   # "reached out" = a money-related contact (hardship form,
                                               # callback request, hardship keywords) in the last 30 days.
                                               # Decides the Quiet Help message: support OFFER or gentle TIP


# ---------------------------------------------------------------------------
# Fixed vocabularies (enums). Using these instead of free strings catches typos early.
# ---------------------------------------------------------------------------
class Source(str, Enum):
    """Which node produced a score."""
    ACCOUNT = "ACCOUNT"          # Node A
    INTERACTION = "INTERACTION"  # Node B


class EntryType(str, Enum):
    """Every kind of ledger entry, and who writes it."""
    SCORE = "SCORE"                          # A, B
    PROMISE = "PROMISE"                      # B (from interactions), E (a booked meeting)
    CONTACT_SCHEDULED = "CONTACT_SCHEDULED"  # E: a booked call with its call code (used by P3)
    ACTION = "ACTION"                        # D: an allowed action. E: an action that was carried out
    BLOCKED = "BLOCKED"                      # D: an action that was blocked by a policy
    STATUS_UPDATE = "STATUS_UPDATE"          # E/D: a promise or recommendation changed status
    RECOMMENDATION = "RECOMMENDATION"        # D: a suggested action awaiting human approval
    APPROVAL = "APPROVAL"                    # UI: a human approved or rejected a recommendation


class PromiseType(str, Enum):
    CALLBACK = "CALLBACK"
    MEETING = "MEETING"
    EMAIL = "EMAIL"
    DECISION = "DECISION"
    HARDSHIP_RESPONSE = "HARDSHIP_RESPONSE"


class PromiseStatus(str, Enum):
    OPEN = "OPEN"            # still to be done
    KEPT = "KEPT"            # done on time
    MISSED = "MISSED"        # deadline passed without it being done
    CANCELLED = "CANCELLED"  # no longer needed (e.g. customer withdrew)


class Channel(str, Enum):
    CALL = "CALL"
    CHAT = "CHAT"
    FORM = "FORM"
    EMAIL = "EMAIL"


class InteractionType(str, Enum):
    HARDSHIP_FORM = "HARDSHIP_FORM"
    CALLBACK_REQUEST = "CALLBACK_REQUEST"
    GENERAL = "GENERAL"
    COMPLAINT = "COMPLAINT"


class FormStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    ABANDONED = "ABANDONED"


class AccountType(str, Enum):
    TRANSACTION = "TRANSACTION"
    CREDIT_CARD = "CREDIT_CARD"
    HOME_LOAN = "HOME_LOAN"


class Category(str, Enum):
    """Transaction categories. The first five come from the SPEC; the rest appear in the mock data."""
    SALARY = "SALARY"
    RENT = "RENT"
    BNPL = "BNPL"
    DISHONOUR = "DISHONOUR"
    LOAN_REPAYMENT = "LOAN_REPAYMENT"
    GROCERIES = "GROCERIES"
    BILLS = "BILLS"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"
    OTHER = "OTHER"


class ActionType(str, Enum):
    """Every action someone can ask Node D to check."""
    # Collections (blocked by P2 while a hardship case is open)
    SEND_DEFAULT_NOTICE = "SEND_DEFAULT_NOTICE"
    SEND_COLLECTIONS_NOTICE = "SEND_COLLECTIONS_NOTICE"
    # Credit offers (blocked by P4 for HIGH / CRITICAL customers)
    OFFER_CREDIT_CARD = "OFFER_CREDIT_CARD"
    OFFER_LOAN = "OFFER_LOAN"
    INCREASE_LIMIT = "INCREASE_LIMIT"
    # Someone claims to be calling from Westpac (checked by P3)
    VERIFY_CALLER = "VERIFY_CALLER"
    # Actions Node E carries out after human approval
    QUIET_HELP_PUSH = "QUIET_HELP_PUSH"
    BOOK_MEETING = "BOOK_MEETING"
    ESCALATE = "ESCALATE"


COLLECTIONS_ACTIONS = {ActionType.SEND_DEFAULT_NOTICE, ActionType.SEND_COLLECTIONS_NOTICE}
CREDIT_OFFER_ACTIONS = {ActionType.OFFER_CREDIT_CARD, ActionType.OFFER_LOAN, ActionType.INCREASE_LIMIT}


class DecisionResult(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"


class PolicyId(str, Enum):
    P1 = "P1"  # promise or deadline near / missed -> alert or escalate
    P2 = "P2"  # collections / default notice while a hardship case is open -> BLOCK
    P3 = "P3"  # "calling from Westpac" with no matching CONTACT_SCHEDULED -> BLOCK, possible scam
    P4 = "P4"  # credit card or loan offer to a HIGH or CRITICAL customer -> BLOCK


class DeadlineLevel(str, Enum):
    """P1 outcome for a promise."""
    ALERT = "ALERT"        # due within P1_ALERT_WINDOW
    ESCALATE = "ESCALATE"  # already past due


class RecommendationType(str, Enum):
    QUIET_HELP_PUSH = "QUIET_HELP_PUSH"
    BOOK_MEETING = "BOOK_MEETING"
    ESCALATE = "ESCALATE"


class RecommendationStatus(str, Enum):
    AWAITING_APPROVAL = "AWAITING_APPROVAL"  # waiting for a human
    APPROVED = "APPROVED"                    # human said yes, not carried out yet
    REJECTED = "REJECTED"                    # human said no
    DONE = "DONE"                            # Node E carried it out


class QuietHelpOption(str, Enum):
    """One-tap options shown inside the app after a Quiet Help push."""
    PAUSE_REPAYMENTS = "PAUSE_REPAYMENTS"    # support OFFER
    REDUCE_REPAYMENTS = "REDUCE_REPAYMENTS"  # support OFFER
    BOOK_CALL = "BOOK_CALL"                  # support OFFER
    SEE_MONEY_TIPS = "SEE_MONEY_TIPS"        # gentle TIP


class QuietHelpMessage(str, Enum):
    """Which Quiet Help message a customer gets.

    OFFER  they reached out first (money-related contact in the last 30 days): the support offer
           ("We're here if you need a hand", pause / reduce repayments, book a call)
    TIP    they haven't: a gentle money tip, with no hardship wording, so nobody is offended
    """
    OFFER = "OFFER"
    TIP = "TIP"


class ReachedOutVia(str, Enum):
    """The kind of money-related contact that counts as reaching out (Node B)."""
    HARDSHIP_FORM = "HARDSHIP_FORM"          # any status, including ABANDONED
    CALLBACK_REQUEST = "CALLBACK_REQUEST"
    HARDSHIP_KEYWORDS = "HARDSHIP_KEYWORDS"  # e.g. "lost my job", "can't afford" in a chat or call


# ---------------------------------------------------------------------------
# Clean data files (written by sanitize.py, read by Nodes A and B; never raw data)
# ---------------------------------------------------------------------------
# GUARDIAN_CLEAN_DIR overrides the folder (tests use a temporary one).
CLEAN_DIR_DEFAULT = Path(__file__).resolve().parents[1] / "data" / "clean"
CLEAN_TRANSACTIONS_FILE = "transactions.csv"
CLEAN_INTERACTIONS_FILE = "interactions.csv"


def clean_dir() -> Path:
    """Where the clean CSVs live: GUARDIAN_CLEAN_DIR, or data/clean by default."""
    return Path(os.getenv("GUARDIAN_CLEAN_DIR") or CLEAN_DIR_DEFAULT)


# ---------------------------------------------------------------------------
# Sanitized CSV columns (the ONLY columns allowed after sanitizing; everything else is dropped)
# ---------------------------------------------------------------------------
CLEAN_TRANSACTION_COLUMNS = [
    "customer_token", "date", "account_type", "amount", "category", "merchant", "balance_after",
]
CLEAN_INTERACTION_COLUMNS = [
    "customer_token", "staff_token", "date", "channel", "type", "form_status", "callback_due", "flags",
]
