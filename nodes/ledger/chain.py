"""Hash chain: what makes the ledger tamper-proof.

Every ledger entry stores two hashes:
  prev_hash  the hash of the entry before it (the very first entry uses GENESIS_HASH, 64 zeros)
  hash       sha256 of THIS entry's content, including prev_hash

Because each hash includes the previous one, the entries form a chain. Change anything in an
old entry (even one character) and its hash no longer matches, which breaks every link after it.

    E-0001  prev=000…000  hash=7f3a…
    E-0002  prev=7f3a…    hash=c91e…    <- depends on E-0001
    E-0003  prev=c91e…    hash=04bd…    <- depends on E-0002, and so on

What's in this file:
    canonical_json(), compute_hash()   used by store.append() to seal each new entry
    verify_chain()                     re-checks the whole ledger and reports the first problem

What verify_chain() catches:
    EDITED          an entry's content was changed after it was written (its hash no longer matches)
    BROKEN_LINK     an entry no longer points at the one before it (entries inserted, swapped or
                    a hash was "fixed up" to hide an edit)
    MISSING_ENTRY   an entry was deleted from the middle (the numbering has a gap)
    UNREADABLE      an entry's data isn't valid JSON any more

One limit to know: if the NEWEST entries are deleted, what's left is still a valid chain.
That's why verify_chain() also returns `head_hash` (the hash of the latest entry): write it
down or show it in the UI, and if it ever goes backwards, history was cut off.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from pydantic import BaseModel

from shared.config import GENESIS_HASH


def canonical_json(obj: Any) -> str:
    """Turn data into ONE fixed JSON string, so the same data always gives the same hash.

    sort_keys=True        {"b":1,"a":2} and {"a":2,"b":1} become identical
    separators=(",",":")  no spaces, so formatting can't change the hash
    ensure_ascii=False    keep characters as they are
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(entry_id: str, customer_token: str, entry_type: str, data: dict[str, Any],
                 created_at: str, prev_hash: str) -> str:
    """sha256 of every field of an entry (except the hash itself), as 64 hex characters.

    prev_hash is one of the hashed fields, which is what links each entry to the one before.
    `created_at` must be the ISO string exactly as stored, e.g. "2026-11-16T10:00:00".
    """
    content = {
        "entry_id": entry_id,
        "customer_token": customer_token,
        "entry_type": entry_type,
        "data": data,
        "created_at": created_at,
        "prev_hash": prev_hash,
    }
    return hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Verifying the chain (C-3)
# ---------------------------------------------------------------------------
class ChainReport(BaseModel):
    """The result of verify_chain(). This is what the ledger_verify_chain tool returns."""
    valid: bool                         # True = nothing has been changed
    entries_checked: int                # how many entries were checked before stopping
    first_bad_entry: Optional[str]      # e.g. "E-0007", or None if valid
    problem: Optional[str]              # EDITED, BROKEN_LINK, MISSING_ENTRY or UNREADABLE (None if valid)
    detail: Optional[str]               # one plain-English sentence about the problem
    last_entry_id: Optional[str]        # the newest entry, e.g. "E-0038" (None if the ledger is empty)
    head_hash: str                      # hash of the newest entry (GENESIS_HASH if empty)


def check_entries(rows: Iterable[Mapping[str, Any]]) -> ChainReport:
    """Check a sequence of raw ledger rows, oldest first.

    Each row needs: seq, entry_id, customer_token, entry_type, data (the JSON TEXT as stored),
    created_at (the ISO string as stored), prev_hash, hash. Stops at the FIRST problem.
    """
    expected_prev = GENESIS_HASH       # what the next entry's prev_hash should be
    expected_seq = 1                   # what the next entry's number should be
    checked = 0
    last_id: Optional[str] = None

    def broken(row, problem: str, detail: str) -> ChainReport:
        return ChainReport(valid=False, entries_checked=checked, first_bad_entry=row["entry_id"],
                           problem=problem, detail=detail, last_entry_id=last_id, head_hash=expected_prev)

    for row in rows:
        checked += 1

        # 1. Numbering: E-0001, E-0002, ... with no gaps. A gap means an entry was deleted.
        if row["seq"] != expected_seq or row["entry_id"] != f"E-{row['seq']:04d}":
            missing = f"E-{expected_seq:04d}"
            return broken(row, "MISSING_ENTRY",
                          f"{missing} is missing: the entry before {row['entry_id']} was deleted or renumbered")

        # 2. Link: this entry must point at the hash of the entry before it.
        if row["prev_hash"] != expected_prev:
            return broken(row, "BROKEN_LINK",
                          f"{row['entry_id']} doesn't point at the entry before it, so an earlier "
                          f"entry was changed and its hash re-calculated, or entries were inserted")

        # 3. Content: re-calculate the hash from what's stored now and compare.
        try:
            data = json.loads(row["data"])
        except (TypeError, ValueError):
            return broken(row, "UNREADABLE", f"{row['entry_id']}'s data is no longer valid JSON")
        recalculated = compute_hash(row["entry_id"], row["customer_token"], row["entry_type"],
                                    data, row["created_at"], row["prev_hash"])
        if recalculated != row["hash"]:
            return broken(row, "EDITED", f"{row['entry_id']} was changed after it was written "
                                         f"(its content no longer matches its hash)")

        # All good: this entry becomes the one the next entry must point at.
        expected_prev = row["hash"]
        expected_seq += 1
        last_id = row["entry_id"]

    return ChainReport(valid=True, entries_checked=checked, first_bad_entry=None, problem=None,
                       detail=None, last_entry_id=last_id, head_hash=expected_prev)


def verify_chain(db_path: Optional[Path | str] = None) -> ChainReport:
    """Re-check every entry in the ledger database and report the first problem, if any.

        report = verify_chain()
        report.valid              # True / False
        report.first_bad_entry    # e.g. "E-0007"
        report.detail             # plain-English explanation
    """
    from nodes.ledger.store import connect   # imported here: store.py also imports this file
    from contextlib import closing

    with closing(connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT seq, entry_id, customer_token, entry_type, data, created_at, prev_hash, hash "
            "FROM ledger ORDER BY seq").fetchall()
    return check_entries(rows)
