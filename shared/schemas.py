"""The contract between nodes: the exact shape of every message in Customer Guardian.

Every message A, B, C, D and E pass around is defined here as a Pydantic model. If your
data doesn't fit the model, Pydantic raises a clear error, so mistakes show up in your own
code instead of breaking someone else's node later.

How to use:
    from shared.schemas import ScoreMessage
    msg = ScoreMessage(customer_token="cust_af4200", source="ACCOUNT", score=63,
                       band="HIGH", reasons=["SALARY_STOPPED"], timestamp="2026-11-16T10:00:00")
    msg.model_dump(mode="json")    # -> plain dict, ready for the ledger or JSON

Two safety features built in:
  - extra="forbid": a model rejects any field it doesn't know. A stray "full_name" or
    "email" can never sneak into a message.
  - Tokens and IDs are pattern-checked (cust_xxxxxx, staff_xxx, P-0001, ...).

Anyone can change this file. Other nodes use these models too, so give the team a heads-up
when you do (see shared/README.md).

Contents:
  1. Building blocks (token/ID types, base class)
  2. Sanitized input rows        CleanTransaction, CleanInteraction
  3. Node A / B output           ScoreMessage, Promise
  4. Node C                      LedgerEntry
  5. Node D                      ActionRequest, Decision, DeadlineAlert, Recommendation
  6. Human + Node E              Approval, QuietHelpPush, MeetingBooking, Escalation,
                                 ContactScheduled, StatusUpdate
  7. Which model goes in each ledger entry type   validate_entry_data()
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import (BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter,
                      field_validator, model_validator)

from shared.config import (CALL_CODE_PATTERN, CUSTOMER_TOKEN_PATTERN, ENTRY_ID_PATTERN,
                           HASH_PATTERN, MESSAGE_ID_PATTERN, PROMISE_ID_PATTERN,
                           REASON_CODE_PATTERN, REC_ID_PATTERN, STAFF_TOKEN_PATTERN,
                           SYSTEM_ACTOR, AccountType, ActionType, Band, Category, Channel,
                           DeadlineLevel, DecisionResult, EntryType, FormStatus,
                           InteractionType, PolicyId, PromiseStatus, PromiseType,
                           QuietHelpOption, RecommendationStatus, RecommendationType,
                           Source, band)

# ===========================================================================
# 1. Building blocks
# ===========================================================================
# Reusable string types. Writing `customer_token: CustomerToken` means Pydantic checks
# the value matches the pattern, e.g. "cust_af4200" passes, "Jane Citizen" fails.
CustomerToken = Annotated[str, StringConstraints(pattern=CUSTOMER_TOKEN_PATTERN)]
StaffToken = Annotated[str, StringConstraints(pattern=STAFF_TOKEN_PATTERN)]
# A staff token, or "SYSTEM" when no person was involved (e.g. a self-service form).
Actor = Annotated[str, StringConstraints(pattern=f"{STAFF_TOKEN_PATTERN}|^{SYSTEM_ACTOR}$")]
EntryId = Annotated[str, StringConstraints(pattern=ENTRY_ID_PATTERN)]
PromiseId = Annotated[str, StringConstraints(pattern=PROMISE_ID_PATTERN)]
RecId = Annotated[str, StringConstraints(pattern=REC_ID_PATTERN)]
MessageId = Annotated[str, StringConstraints(pattern=MESSAGE_ID_PATTERN)]
CallCode = Annotated[str, StringConstraints(pattern=CALL_CODE_PATTERN)]
Hash = Annotated[str, StringConstraints(pattern=HASH_PATTERN)]
ReasonCode = Annotated[str, StringConstraints(pattern=REASON_CODE_PATTERN)]
Score = Annotated[int, Field(ge=0, le=100)]


class Contract(BaseModel):
    """Base class for every message.

    extra="forbid"      unknown fields are an error (stops PII fields sneaking in)
    frozen=True         a message can't be changed after it's created (like the ledger)
    use_enum_values     enums are stored as plain strings, e.g. "HIGH" not Band.HIGH
    validate_default    default values are checked too
    """
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True, validate_default=True)


def _empty_to_none(value: Any) -> Any:
    """CSV files store 'nothing' as an empty string. Turn that into None."""
    return None if value == "" else value


# ===========================================================================
# 2. Sanitized input rows (output of sanitize.py, input to Nodes A and B)
# ===========================================================================
class CleanTransaction(Contract):
    """One row of data/clean/transactions.csv. No PII: the customer is a token."""
    customer_token: CustomerToken
    date: date
    account_type: AccountType
    amount: float                      # negative = money out, positive = money in
    category: Category
    merchant: Optional[str] = None     # e.g. AFTERPAY, WOOLWORTHS (businesses, not people)
    balance_after: float

    blank_to_none = field_validator("merchant", mode="before")(_empty_to_none)


class CleanInteraction(Contract):
    """One row of data/clean/interactions.csv. The free text has already been DELETED;
    only keyword flags (e.g. JOB_LOSS) are kept."""
    customer_token: CustomerToken
    staff_token: Optional[StaffToken] = None   # None for self-service forms
    date: date
    channel: Channel
    type: InteractionType
    form_status: Optional[FormStatus] = None   # only for HARDSHIP_FORM
    callback_due: Optional[datetime] = None    # only for CALLBACK_REQUEST
    flags: list[ReasonCode] = []

    blank_to_none = field_validator("staff_token", "form_status", "callback_due", mode="before")(_empty_to_none)

    @field_validator("flags", mode="before")
    @classmethod
    def _split_flags(cls, value: Any) -> Any:
        """In the CSV, flags are stored as "JOB_LOSS|CANT_AFFORD". Turn that into a list."""
        if isinstance(value, str):
            return [f for f in value.split("|") if f]
        return value


# ===========================================================================
# 3. Node A / B output  ->  Ledger
# ===========================================================================
class ScoreMessage(Contract):
    """A hardship score from Node A (source=ACCOUNT) or Node B (source=INTERACTION).

    SPEC example:
        {"customer_token": "cust_8f2a91", "source": "ACCOUNT", "score": 63, "band": "HIGH",
         "reasons": ["SALARY_STOPPED", "DISHONOUR", "BNPL_STACKING"],
         "timestamp": "2026-11-16T10:00:00"}
    """
    customer_token: CustomerToken
    source: Source
    score: Score
    band: Band
    reasons: list[ReasonCode]          # rule codes that added points, e.g. SALARY_STOPPED
    timestamp: datetime

    @model_validator(mode="after")
    def _band_matches_score(self) -> "ScoreMessage":
        # Stops mistakes like score=63 with band="LOW".
        expected = band(self.score).value
        if self.band != expected:
            raise ValueError(f"band {self.band!r} doesn't match score {self.score} (should be {expected!r})")
        return self


class Promise(Contract):
    """Something the bank promised to do (from Node B, or a meeting booked by Node E).

    SPEC example:
        {"customer_token": "cust_8f2a91", "promise_id": "P-0042", "promise_type": "CALLBACK",
         "description": "Hardship team to call back", "made_by": "staff_19c",
         "made_via": "CALL", "due": "2026-11-18T14:00:00", "status": "OPEN"}
    """
    customer_token: CustomerToken
    promise_id: PromiseId
    promise_type: PromiseType
    description: str = Field(max_length=200)   # from a fixed template, NEVER customer text
    made_by: Actor
    made_via: Channel
    due: datetime
    status: PromiseStatus = PromiseStatus.OPEN


# ===========================================================================
# 4. Node C: the ledger
# ===========================================================================
class LedgerEntry(Contract):
    """One line in the Promise Ledger. Entries are only ever added, never changed.

    `data` holds the message itself (a ScoreMessage, Promise, Decision, ...). Use
    validate_entry_data() below to check it matches the entry_type.
    `hash` = sha256(this entry + prev_hash), which chains every entry to the one before it.
    """
    entry_id: EntryId
    customer_token: CustomerToken
    entry_type: EntryType
    data: dict[str, Any]
    created_at: datetime
    prev_hash: Hash
    hash: Hash


# ===========================================================================
# 5. Node D: Policy Agent
# ===========================================================================
class ActionRequest(Contract):
    """An action someone wants to take, sent to Node D for checking.

    SPEC example:
        {"customer_token": "cust_8f2a91", "action": "SEND_DEFAULT_NOTICE", "requested_by": "staff_44a"}
    For VERIFY_CALLER, include the call_code the caller quoted.
    """
    customer_token: CustomerToken
    action: ActionType
    requested_by: Actor
    call_code: Optional[str] = Field(default=None, max_length=12)  # what the caller said; may be wrong

    @model_validator(mode="after")
    def _caller_needs_code(self) -> "ActionRequest":
        if self.action == ActionType.VERIFY_CALLER.value and not self.call_code:
            raise ValueError("VERIFY_CALLER needs the call_code the caller quoted")
        return self


class Decision(Contract):
    """Node D's answer to an ActionRequest.

    SPEC example:
        {"customer_token": "cust_8f2a91", "action": "SEND_DEFAULT_NOTICE", "decision": "BLOCK",
         "policy": "P2", "reason": "Hardship request received 6 days ago, response due in 15 days"}
    """
    customer_token: CustomerToken
    action: ActionType
    decision: DecisionResult
    policy: Optional[PolicyId] = None   # which policy blocked it (None when ALLOWED)
    reason: str = Field(max_length=300) # built from a template by code, not written by the AI
    flags: list[ReasonCode] = []        # e.g. ["POSSIBLE_SCAM"] for P3

    @model_validator(mode="after")
    def _block_needs_policy(self) -> "Decision":
        if self.decision == DecisionResult.BLOCK.value and self.policy is None:
            raise ValueError("a BLOCK decision must name the policy that blocked it")
        return self


class DeadlineAlert(Contract):
    """P1 result for one promise that is near its deadline or already overdue."""
    customer_token: CustomerToken
    promise_id: PromiseId
    promise_type: PromiseType
    due: datetime
    level: DeadlineLevel               # ALERT (due soon) or ESCALATE (overdue)
    hours_to_due: float                # negative when overdue
    policy: Literal["P1"] = "P1"
    reason: str = Field(default="", max_length=300)   # plain English, e.g. "Callback was due 2 days ago (14 Nov 10:00)"


class Recommendation(Contract):
    """A suggestion from Node D. Nothing happens until a human approves it.

    SPEC example:
        {"rec_id": "R-0031", "customer_token": "cust_8f2a91", "recommendation": "QUIET_HELP_PUSH",
         "why": ["SALARY_STOPPED", "SCORE_HIGH"], "status": "AWAITING_APPROVAL"}
    """
    rec_id: RecId
    customer_token: CustomerToken
    recommendation: RecommendationType
    why: list[ReasonCode]
    status: RecommendationStatus = RecommendationStatus.AWAITING_APPROVAL


# ===========================================================================
# 6. Human approval + Node E: Actions
# ===========================================================================
class Approval(Contract):
    """A human's decision on a recommendation, made by clicking in the UI (never by the AI).

    SPEC example: {"rec_id": "R-0031", "approved_by": "staff_19c", "approved": true}
    """
    rec_id: RecId
    approved_by: StaffToken            # must be a person, never SYSTEM
    approved: bool


class QuietHelpPush(Contract):
    """Node E sent a Quiet Help push. The lock screen only says
    "You have a new message from Westpac"; the options show inside the app."""
    customer_token: CustomerToken
    action: Literal["QUIET_HELP_PUSH"] = "QUIET_HELP_PUSH"
    message_id: MessageId
    options: list[QuietHelpOption]


class MeetingBooking(Contract):
    """Node E booked a meeting. The customer sees the call_code in their app; a real
    Westpac caller will quote it, and policy P3 checks it."""
    customer_token: CustomerToken
    action: Literal["BOOK_MEETING"] = "BOOK_MEETING"
    meeting_time: datetime
    staff: StaffToken
    call_code: CallCode


class Escalation(Contract):
    """Node E escalated a case (e.g. a missed promise) to a team lead."""
    customer_token: CustomerToken
    action: Literal["ESCALATE"] = "ESCALATE"
    why: list[ReasonCode]


class ContactScheduled(Contract):
    """A contact the bank has scheduled with its call code. P3 looks these up to tell a
    real Westpac caller from a scammer."""
    customer_token: CustomerToken
    call_code: CallCode
    contact_time: datetime
    staff: StaffToken


class StatusUpdate(Contract):
    """A promise or recommendation changed status, e.g. a callback was made (P-0042 -> KEPT)
    or a recommendation was carried out (R-0031 -> DONE)."""
    customer_token: CustomerToken
    ref_id: Annotated[str, StringConstraints(pattern=f"{PROMISE_ID_PATTERN}|{REC_ID_PATTERN}")]
    status: str
    updated_by: Actor

    @model_validator(mode="after")
    def _status_fits_ref(self) -> "StatusUpdate":
        # P-xxxx must use a PromiseStatus, R-xxxx must use a RecommendationStatus.
        allowed = PromiseStatus if self.ref_id.startswith("P-") else RecommendationStatus
        if self.status not in {s.value for s in allowed}:
            raise ValueError(f"status {self.status!r} isn't valid for {self.ref_id}; "
                             f"use one of {[s.value for s in allowed]}")
        return self


# Anything Node E can report after carrying out an approved recommendation.
ActionResult = Union[QuietHelpPush, MeetingBooking, Escalation]


# ===========================================================================
# 7. Which model belongs in each ledger entry type
# ===========================================================================
# The ledger (C-2) calls validate_entry_data() before appending, so a malformed message
# is rejected before it can ever be written.
#   ACTION can be either D allowing a request (Decision) or E carrying one out (ActionResult).
_ENTRY_DATA_MODELS: dict[str, Any] = {
    EntryType.SCORE.value: ScoreMessage,
    EntryType.PROMISE.value: Promise,
    EntryType.CONTACT_SCHEDULED.value: ContactScheduled,
    EntryType.ACTION.value: Union[Decision, QuietHelpPush, MeetingBooking, Escalation],
    EntryType.BLOCKED.value: Decision,
    EntryType.STATUS_UPDATE.value: StatusUpdate,
    EntryType.RECOMMENDATION.value: Recommendation,
    EntryType.APPROVAL.value: Approval,
}
_ADAPTERS = {name: TypeAdapter(model) for name, model in _ENTRY_DATA_MODELS.items()}


def validate_entry_data(entry_type: EntryType | str, data: dict[str, Any]) -> Contract:
    """Check `data` is the right message for `entry_type` and return it as a model.

    Example:
        validate_entry_data("SCORE", {"customer_token": "cust_af4200", "source": "ACCOUNT", ...})
    Raises pydantic.ValidationError if it doesn't fit.
    """
    key = getattr(entry_type, "value", entry_type)   # accept EntryType.SCORE or "SCORE"
    if key not in _ADAPTERS:
        raise ValueError(f"unknown entry_type {key!r}; use one of {list(_ADAPTERS)}")
    model = _ADAPTERS[key].validate_python(data)
    if key == EntryType.BLOCKED.value and model.decision != DecisionResult.BLOCK.value:
        raise ValueError("a BLOCKED entry must hold a Decision with decision='BLOCK'")
    if key == EntryType.ACTION.value and isinstance(model, Decision) and model.decision != DecisionResult.ALLOW.value:
        raise ValueError("an ACTION entry holding a Decision must have decision='ALLOW' (use BLOCKED otherwise)")
    return model
