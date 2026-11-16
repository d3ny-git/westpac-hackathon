"""Hash chain: what makes the ledger tamper-proof.

Every ledger entry stores two hashes:
  prev_hash  the hash of the entry before it (the very first entry uses GENESIS_HASH, 64 zeros)
  hash       sha256 of THIS entry's content, including prev_hash

Because each hash includes the previous one, the entries form a chain. Change anything in an
old entry (even one character) and its hash no longer matches, which breaks every link after it.

    E-0001  prev=000…000  hash=7f3a…
    E-0002  prev=7f3a…    hash=c91e…    <- depends on E-0001
    E-0003  prev=c91e…    hash=04bd…    <- depends on E-0002, and so on

C-2 (this file, now):  canonical_json() and compute_hash(), used by store.append().
C-3 (next):            verify_chain(), which re-computes every hash to detect tampering.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


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
