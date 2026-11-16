"""The Promise Ledger database: one append-only list of everything the bank knows and promised.

The functions most people need:

    from nodes.ledger import store

    entry_id = store.append("SCORE", "cust_af4200", score_msg.model_dump(mode="json"))  # -> "E-0001"
    entries  = store.read(customer_token="cust_af4200")          # list of LedgerEntry, oldest first
    entry    = store.get("E-0001")                               # one entry, or None
    new_id   = store.next_id("P")                                # -> "P-0005" (next free promise ID)

What append() guarantees:
  1. The data is the right message for the entry type (checked against shared/schemas.py).
  2. No PII is stored (shared/pii_guard.py).
  3. IDs are never reused: a promise_id / rec_id / message_id that already exists is rejected.
  4. No back-dating: an entry can't be older than the entry before it.
  5. Every entry is hash-chained to the previous one (see chain.py).
If any check fails, NOTHING is written.

And the database itself refuses UPDATE and DELETE (SQLite triggers), so history can't be
changed even by someone running SQL by hand. The only way to start over is reset(), which
deletes the whole demo database file.

Where the data lives: data/guardian.db (gitignored). Set GUARDIAN_DB in .env to use another
file, or pass db_path=... to any function (tests do this).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from nodes.ledger.chain import canonical_json, compute_hash
from shared.config import GENESIS_HASH, EntryType, now
from shared.pii_guard import assert_no_pii
from shared.schemas import LedgerEntry, validate_entry_data

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "data" / "guardian.db"

# Prefixes next_id() can hand out. Ledger entry IDs (E-) are always created by append() itself.
ID_PREFIXES = {"P": "promise", "R": "recommendation", "M": "message"}


class LedgerError(ValueError):
    """The ledger refused an entry (duplicate ID, back-dating, mismatched customer, ...)."""


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------
_SCHEMA = """
-- One row per ledger entry. Columns match the SPEC; `seq` is just the row number.
CREATE TABLE IF NOT EXISTS ledger (
    seq            INTEGER PRIMARY KEY,
    entry_id       TEXT NOT NULL UNIQUE,
    customer_token TEXT NOT NULL,
    entry_type     TEXT NOT NULL,
    data           TEXT NOT NULL,          -- the message, as canonical JSON
    created_at     TEXT NOT NULL,          -- ISO time, e.g. 2026-11-16T10:00:00
    prev_hash      TEXT NOT NULL,
    hash           TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_ledger_customer ON ledger(customer_token);
CREATE INDEX IF NOT EXISTS idx_ledger_type ON ledger(entry_type);

-- Append-only: the database itself refuses to change or remove history.
CREATE TRIGGER IF NOT EXISTS ledger_no_update BEFORE UPDATE ON ledger
BEGIN SELECT RAISE(ABORT, 'ledger is append-only: UPDATE is not allowed'); END;
CREATE TRIGGER IF NOT EXISTS ledger_no_delete BEFORE DELETE ON ledger
BEGIN SELECT RAISE(ABORT, 'ledger is append-only: DELETE is not allowed'); END;

-- Highest number handed out or seen so far for each ID prefix (P, R, M). Used by next_id().
-- This is a helper table, not history, so it is allowed to change.
CREATE TABLE IF NOT EXISTS id_counters (
    prefix TEXT PRIMARY KEY,
    last   INTEGER NOT NULL
);
"""


def _db_path(db_path: Optional[Path | str]) -> Path:
    if db_path is not None:
        return Path(db_path)
    return Path(os.getenv("GUARDIAN_DB", DEFAULT_DB))


def connect(db_path: Optional[Path | str] = None) -> sqlite3.Connection:
    """Open the ledger database, creating the file and tables if they don't exist yet."""
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None: we start transactions ourselves (BEGIN IMMEDIATE below).
    # timeout=10: if another process (e.g. the UI) is writing, wait up to 10s instead of failing.
    conn = sqlite3.connect(path, isolation_level=None, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def reset(db_path: Optional[Path | str] = None) -> None:
    """Delete the whole demo database so you can start fresh (used by reset_demo.py and tests).

    This is the ONLY way to remove entries. It wipes everything, so it can't be used to
    quietly remove one inconvenient entry.
    """
    path = _db_path(db_path)
    for suffix in ("", "-wal", "-shm", "-journal"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# IDs
# ---------------------------------------------------------------------------
# Which field in each entry type holds a NEW id that must never be reused.
_NEW_ID_FIELDS = {
    EntryType.PROMISE.value: "promise_id",
    EntryType.RECOMMENDATION.value: "rec_id",
    EntryType.ACTION.value: "message_id",       # only Quiet Help pushes have one
}
_ID_RE = re.compile(r"^([A-Z])-(\d+)$")


def next_id(prefix: str, db_path: Optional[Path | str] = None) -> str:
    """Hand out the next free ID for a prefix: "P" (promise), "R" (recommendation), "M" (message).

    Example: if P-0001..P-0004 are already in the ledger, next_id("P") returns "P-0005".
    Each call returns a new number, even if the first one was never used, so two nodes
    can never be given the same ID.
    """
    if prefix not in ID_PREFIXES:
        raise LedgerError(f"unknown ID prefix {prefix!r}; use one of {sorted(ID_PREFIXES)}")
    with closing(connect(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")   # lock, so two callers can't get the same number
        conn.execute("INSERT OR IGNORE INTO id_counters(prefix, last) VALUES (?, 0)", (prefix,))
        conn.execute("UPDATE id_counters SET last = last + 1 WHERE prefix = ?", (prefix,))
        number = conn.execute("SELECT last FROM id_counters WHERE prefix = ?", (prefix,)).fetchone()[0]
        conn.execute("COMMIT")
    return f"{prefix}-{number:04d}"


def _id_already_used(conn: sqlite3.Connection, entry_type: str, field: str, value: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM ledger WHERE entry_type = ? AND json_extract(data, ?) = ? LIMIT 1",
        (entry_type, f"$.{field}", value),
    ).fetchone()
    return row is not None


def _remember_id(conn: sqlite3.Connection, value: str) -> None:
    """Make sure next_id() never hands out a number that's already been used."""
    match = _ID_RE.match(value)
    if match and match.group(1) in ID_PREFIXES:
        prefix, number = match.group(1), int(match.group(2))
        conn.execute("INSERT OR IGNORE INTO id_counters(prefix, last) VALUES (?, 0)", (prefix,))
        conn.execute("UPDATE id_counters SET last = MAX(last, ?) WHERE prefix = ?", (number, prefix))


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------
def append(entry_type: EntryType | str, customer_token: str, data: dict[str, Any], *,
           created_at: Optional[datetime] = None, db_path: Optional[Path | str] = None) -> str:
    """Add one entry to the ledger and return its entry_id (e.g. "E-0007").

    entry_type      one of shared.config.EntryType, e.g. "SCORE", "PROMISE", "ACTION"
    customer_token  who the entry is about, e.g. "cust_af4200"
    data            the message as a dict, e.g. ScoreMessage(...).model_dump(mode="json")
    created_at      leave empty to use the system clock (config.now()). Only the seed/fixture
                    loader should set this, to load past events in time order.
    """
    entry_type = getattr(entry_type, "value", entry_type)

    # 1. Right message for this entry type? (raises pydantic.ValidationError if not)
    model = validate_entry_data(entry_type, data)
    clean = model.model_dump(mode="json")       # normalised: enums -> strings, dates -> ISO

    # 2. Entry is about the customer the message says it's about.
    if "customer_token" in clean and clean["customer_token"] != customer_token:
        raise LedgerError(f"customer_token {customer_token!r} doesn't match the message "
                          f"({clean['customer_token']!r})")

    # 3. No PII, ever (raises PIIError).
    assert_no_pii(clean)

    when = (created_at or now()).isoformat(timespec="seconds")

    with closing(connect(db_path)) as conn:
        # BEGIN IMMEDIATE locks the database for writing, so two processes can't both
        # read the same "last entry" and create a fork in the chain.
        conn.execute("BEGIN IMMEDIATE")
        try:
            last = conn.execute(
                "SELECT seq, hash, created_at FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()

            # 4. No back-dating.
            if last is not None and when < last["created_at"]:
                raise LedgerError(f"created_at {when} is earlier than the previous entry "
                                  f"({last['created_at']}); the ledger only moves forward in time")

            # 5. IDs are never reused.
            id_field = _NEW_ID_FIELDS.get(entry_type)
            new_id = clean.get(id_field) if id_field else None
            if id_field and new_id:
                if _id_already_used(conn, entry_type, id_field, new_id):
                    raise LedgerError(f"{id_field} {new_id} is already in the ledger; "
                                      f"use store.next_id() to get a free one")
                _remember_id(conn, new_id)

            # 6. Build the entry and chain it to the previous one.
            seq = (last["seq"] + 1) if last else 1
            entry_id = f"E-{seq:04d}"
            prev_hash = last["hash"] if last else GENESIS_HASH
            entry_hash = compute_hash(entry_id, customer_token, entry_type, clean, when, prev_hash)

            # Final shape check (token format, hash format, ...) before writing.
            LedgerEntry(entry_id=entry_id, customer_token=customer_token, entry_type=entry_type,
                        data=clean, created_at=when, prev_hash=prev_hash, hash=entry_hash)

            conn.execute(
                "INSERT INTO ledger (seq, entry_id, customer_token, entry_type, data, created_at, prev_hash, hash)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (seq, entry_id, customer_token, entry_type, canonical_json(clean), when, prev_hash, entry_hash),
            )
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")    # nothing is written if anything above failed
            raise
    return entry_id


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def _to_entry(row: sqlite3.Row) -> LedgerEntry:
    return LedgerEntry(entry_id=row["entry_id"], customer_token=row["customer_token"],
                       entry_type=row["entry_type"], data=json.loads(row["data"]),
                       created_at=row["created_at"], prev_hash=row["prev_hash"], hash=row["hash"])


def read(customer_token: Optional[str] = None,
         entry_type: Optional[EntryType | str | Iterable[EntryType | str]] = None,
         *, db_path: Optional[Path | str] = None) -> list[LedgerEntry]:
    """Read entries, oldest first. Filter by customer and/or entry type(s).

    store.read()                                         # everything
    store.read(customer_token="cust_af4200")             # one customer's history
    store.read(entry_type="PROMISE")                     # all promises
    store.read("cust_af4200", ["SCORE", "PROMISE"])      # one customer's scores and promises
    """
    sql, params = "SELECT * FROM ledger WHERE 1=1", []
    if customer_token is not None:
        sql += " AND customer_token = ?"
        params.append(customer_token)
    if entry_type is not None:
        types = [entry_type] if isinstance(entry_type, (str, EntryType)) else list(entry_type)
        types = [getattr(t, "value", t) for t in types]
        sql += f" AND entry_type IN ({','.join('?' * len(types))})"
        params.extend(types)
    sql += " ORDER BY seq"
    with closing(connect(db_path)) as conn:
        return [_to_entry(r) for r in conn.execute(sql, params)]


def get(entry_id: str, *, db_path: Optional[Path | str] = None) -> Optional[LedgerEntry]:
    """One entry by its ID, e.g. store.get("E-0007"). Returns None if it doesn't exist."""
    with closing(connect(db_path)) as conn:
        row = conn.execute("SELECT * FROM ledger WHERE entry_id = ?", (entry_id,)).fetchone()
    return _to_entry(row) if row else None


def count(*, db_path: Optional[Path | str] = None) -> int:
    """How many entries are in the ledger."""
    with closing(connect(db_path)) as conn:
        return conn.execute("SELECT COUNT(*) FROM ledger").fetchone()[0]
