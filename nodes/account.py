"""Node A: Account. Scores each customer's financial stress (0-100) from their transactions (AB-2).

    data/clean/transactions.csv (tokens only, written by the sanitizer)  ->  rules  ->  SCORE entries in the ledger

The rules are plain Python, not AI, using the fixed demo clock (shared.config.now()):

    Salary stopped     salary 36-90 days ago, but none in the last 35 days          +25  SALARY_STOPPED
    Dishonour          a dishonoured payment in the last 30 days                     +10  DISHONOUR
    Overdrawn          +2 for each of the last 30 days the account ended overdrawn  +2/day OVERDRAWN
    BNPL stacking      3 or more different buy-now-pay-later providers, last 30 days +8  BNPL_STACKING
    Loan arrears       loan repayments 36-90 days ago, but none in the last 35 days  +15  LOAN_ARREARS
    Capped at 100. Bands: LOW <30, MODERATE 30-59, HIGH 60-79, CRITICAL 80+.

Node A only ever reads CLEAN data. It never sees raw data or personal information.

MCP tools (register() at the bottom): account_check_data, account_score_all, account_publish, account_rules.
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from nodes.ledger import store
from shared.config import CLEAN_TRANSACTION_COLUMNS, CLEAN_TRANSACTIONS_FILE, EntryType, band, clean_dir, now
from shared.pii_guard import safe_tool
from shared.schemas import CleanTransaction, ScoreMessage

# The rule table: one place for the points, so account_rules() and the scoring always agree.
RULES = [
    {"reason": "SALARY_STOPPED", "points": 25, "rule": "Salary paid 36-90 days ago, but none in the last 35 days"},
    {"reason": "DISHONOUR", "points": 10, "rule": "A dishonoured payment in the last 30 days"},
    {"reason": "OVERDRAWN", "points": 2, "rule": "Per day in the last 30 days the transaction account ended overdrawn"},
    {"reason": "BNPL_STACKING", "points": 8, "rule": "3 or more different buy-now-pay-later providers in the last 30 days"},
    {"reason": "LOAN_ARREARS", "points": 15, "rule": "Loan repayments 36-90 days ago, but none in the last 35 days"},
]
POINTS = {r["reason"]: r["points"] for r in RULES}
RECENT_DAYS, OLDER_FROM, OLDER_TO, ARREARS_RECENT_DAYS = 30, 36, 90, 35
BNPL_STACKING_PROVIDERS = 3


class AccountError(ValueError):
    """Node A can't do what was asked (e.g. no clean data yet). Messages are safe to show the AI."""


class AccountSignals(BaseModel):
    """What the rules found for one customer (same fields as mock_input_output/personas.json)."""
    salary_stopped: bool
    dishonour: bool
    overdrawn_days: int
    bnpl_providers: int
    loan_arrears: bool


# ---------------------------------------------------------------------------
# Reading the clean data
# ---------------------------------------------------------------------------
def clean_file() -> Path:
    return clean_dir() / CLEAN_TRANSACTIONS_FILE


def load_transactions() -> list[CleanTransaction]:
    """Every row of data/clean/transactions.csv, checked against the shared schema."""
    path = clean_file()
    if not path.exists():
        raise AccountError("There's no clean transaction data yet. Run `python sanitize.py` first.")
    with open(path, newline="", encoding="utf-8") as f:
        return [CleanTransaction(**row) for row in csv.DictReader(f)]


def _by_customer(rows: list[CleanTransaction]) -> dict[str, list[CleanTransaction]]:
    grouped: dict[str, list[CleanTransaction]] = {}
    for row in rows:
        grouped.setdefault(row.customer_token, []).append(row)
    return dict(sorted(grouped.items()))           # a fixed order: by token


# ---------------------------------------------------------------------------
# The rules (pure functions: rows in, answer out)
# ---------------------------------------------------------------------------
def account_signals(rows: list[CleanTransaction], as_of: Optional[date] = None) -> AccountSignals:
    """Work out the five signals from one customer's transactions (oldest first)."""
    as_of = as_of or now().date()
    rows = sorted(rows, key=lambda r: r.date)          # stable: same-day rows keep their order

    def days_ago(r: CleanTransaction) -> int:
        return (as_of - r.date).days

    def paid(category: str, low: int, high: int) -> bool:
        return any(r.category == category and low <= days_ago(r) <= high for r in rows)

    salary_stopped = paid("SALARY", OLDER_FROM, OLDER_TO) and not paid("SALARY", 0, ARREARS_RECENT_DAYS)
    loan_arrears = paid("LOAN_REPAYMENT", OLDER_FROM, OLDER_TO) and not paid("LOAN_REPAYMENT", 0, ARREARS_RECENT_DAYS)
    dishonour = paid("DISHONOUR", 0, RECENT_DAYS)
    bnpl = {r.merchant.strip().upper() for r in rows
            if r.category == "BNPL" and 0 <= days_ago(r) <= RECENT_DAYS and (r.merchant or "").strip()}

    # Overdrawn days: the end-of-day TRANSACTION balance, carried forward over days with no rows.
    window_start = as_of - timedelta(days=RECENT_DAYS)
    end_of_day: dict[date, float] = {}
    balance: Optional[float] = None
    for r in rows:
        if r.account_type != "TRANSACTION":
            continue
        if r.date < window_start:
            balance = r.balance_after                   # the last balance before the window starts
        end_of_day[r.date] = r.balance_after            # same day: the last row wins
    overdrawn_days = 0
    for offset in range(RECENT_DAYS):
        day = window_start + timedelta(days=offset)
        balance = end_of_day.get(day, balance)
        if balance is not None and balance < 0:
            overdrawn_days += 1

    return AccountSignals(salary_stopped=salary_stopped, dishonour=dishonour, overdrawn_days=overdrawn_days,
                          bnpl_providers=len(bnpl), loan_arrears=loan_arrears)


def score_from_signals(token: str, signals: AccountSignals) -> ScoreMessage:
    """Turn the signals into Node A's ScoreMessage (reasons in the rule-table order)."""
    reasons: list[str] = []
    score = 0
    if signals.salary_stopped:
        score += POINTS["SALARY_STOPPED"]; reasons.append("SALARY_STOPPED")
    if signals.dishonour:
        score += POINTS["DISHONOUR"]; reasons.append("DISHONOUR")
    if signals.overdrawn_days:
        score += POINTS["OVERDRAWN"] * signals.overdrawn_days; reasons.append("OVERDRAWN")
    if signals.bnpl_providers >= BNPL_STACKING_PROVIDERS:
        score += POINTS["BNPL_STACKING"]; reasons.append("BNPL_STACKING")
    if signals.loan_arrears:
        score += POINTS["LOAN_ARREARS"]; reasons.append("LOAN_ARREARS")
    score = min(100, score)
    return ScoreMessage(customer_token=token, source="ACCOUNT", score=score, band=band(score).value,
                        reasons=reasons, timestamp=now())


def score_all_customers() -> list[ScoreMessage]:
    """A ScoreMessage for every customer in the clean data, ordered by token."""
    return [score_from_signals(token, account_signals(rows)) for token, rows in _by_customer(load_transactions()).items()]


def score_customer(customer_token: str) -> ScoreMessage:
    """One customer's ScoreMessage."""
    rows = [r for r in load_transactions() if r.customer_token == customer_token]
    if not rows:
        raise AccountError(f"{customer_token} has no transactions in the clean data")
    return score_from_signals(customer_token, account_signals(rows))


# ---------------------------------------------------------------------------
# Checking the data and publishing to the ledger
# ---------------------------------------------------------------------------
def check_data() -> dict:
    """How much clean data there is, and confirmation it has ONLY the allow-listed columns."""
    path = clean_file()
    if not path.exists():
        raise AccountError("There's no clean transaction data yet. Run `python sanitize.py` first.")
    with open(path, newline="", encoding="utf-8") as f:
        columns = next(csv.reader(f), [])
    if columns != CLEAN_TRANSACTION_COLUMNS:
        # Report the problem instead of reading the rows: an unexpected column might hold PII.
        unexpected = [c for c in columns if c not in CLEAN_TRANSACTION_COLUMNS]
        missing = [c for c in CLEAN_TRANSACTION_COLUMNS if c not in columns]
        return {"rows": None, "customers": None, "columns_ok": False,
                "unexpected_columns": len(unexpected), "missing_columns": missing}
    rows = load_transactions()
    return {"rows": len(rows), "customers": len({r.customer_token for r in rows}),
            "columns": columns, "columns_ok": True,
            "first_date": min(r.date for r in rows).isoformat() if rows else None,
            "last_date": max(r.date for r in rows).isoformat() if rows else None}


def _latest_account_score(customer_token: str) -> Optional[dict]:
    scores = [e.data for e in store.read(customer_token=customer_token, entry_type=EntryType.SCORE)
              if e.data["source"] == "ACCOUNT"]
    return scores[-1] if scores else None


def publish() -> dict:
    """Write a SCORE entry to the ledger for every customer whose account score changed.

    A customer whose latest ACCOUNT score in the ledger already has the same score, band and
    reasons is skipped, so running it twice writes nothing the second time.
    """
    if check_data()["columns_ok"] is not True:
        raise AccountError("The clean transaction file has unexpected columns, so nothing was published.")
    written, skipped = [], []
    for msg in score_all_customers():
        latest = _latest_account_score(msg.customer_token)
        if latest and (latest["score"], latest["band"], latest["reasons"]) == (msg.score, msg.band, msg.reasons):
            skipped.append(msg.customer_token)
            continue
        written.append(store.append(EntryType.SCORE, msg.customer_token, msg.model_dump(mode="json")))
    return {"written": len(written), "skipped": len(skipped), "entry_ids": written}


def rules() -> dict:
    """The rule table, so the AI can explain reasons without guessing."""
    return {"source": "ACCOUNT", "rules": RULES, "cap": 100,
            "bands": {"LOW": "under 30", "MODERATE": "30-59", "HIGH": "60-79", "CRITICAL": "80 or more"},
            "as_of": now().isoformat()}


# ---------------------------------------------------------------------------
# MCP tools: what the AI is allowed to ask Node A
# ---------------------------------------------------------------------------
def register(mcp) -> None:
    """Called once by server.py to add Node A's tools to the MCP server."""

    @mcp.tool(name="account_check_data")
    @safe_tool
    def tool_check_data() -> dict:
        """Check Node A's clean transaction data before scoring: how many rows and customers,
        the date range, and columns_ok (true only if the file has exactly the allowed columns, no PII)."""
        return check_data()

    @mcp.tool(name="account_score_all")
    @safe_tool
    def tool_score_all() -> list[dict]:
        """Score every customer from their transactions. Returns one score per customer:
        customer_token, source ACCOUNT, score (0-100), band, and reasons (rule codes)."""
        return score_all_customers()

    @mcp.tool(name="account_publish")
    @safe_tool
    def tool_publish() -> dict:
        """Write each customer's account score to the ledger as a SCORE entry (unchanged scores are
        skipped). Returns how many were written and skipped, and the new entry IDs."""
        return publish()

    @mcp.tool(name="account_rules")
    @safe_tool
    def tool_rules() -> dict:
        """The account scoring rules: each reason code, its points and what it means, plus the bands."""
        return rules()
