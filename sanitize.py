"""Sanitize raw bank data (with PII) into clean data (tokens only). Plain code, no AI.

    python sanitize.py                         # data/raw/*.csv -> data/clean/*.csv
    python sanitize.py --raw DIR --clean DIR   # other folders

    data/raw/transactions_raw.csv   (A's input, HAS PII)  ->  data/clean/transactions.csv
    data/raw/interactions_raw.csv   (B's history, HAS PII) ->  data/clean/interactions.csv

What happens to every row:
  1. tokenise IDs           customer_id -> cust_xxxxxx, staff_id -> staff_xxx (one-way, shared/pii_guard.py)
  2. drop PII columns       only the allow-listed columns in shared/config.py are kept
  3. free text -> flags     B's text becomes keyword flags (JOB_LOSS, CANT_AFFORD), then is DELETED
  4. double-check           every clean row must fit the shared schema and contain no PII, or nothing is written

This is NOT an MCP tool: the AI can never trigger a read of raw data. Nodes A and B only ever
read data/clean/. B's mock input form (B5) calls sanitize_interaction() on each submission.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

from dotenv import load_dotenv

from shared.config import (CLEAN_INTERACTION_COLUMNS, CLEAN_INTERACTIONS_FILE, CLEAN_TRANSACTION_COLUMNS,
                           CLEAN_TRANSACTIONS_FILE, clean_dir)
from shared.pii_guard import assert_no_pii, keep_columns, scrub_text, tokenise
from shared.schemas import CleanInteraction, CleanTransaction

REPO = Path(__file__).resolve().parent
load_dotenv(REPO / ".env")                      # TOKEN_SECRET lives in .env

RAW_DIR = REPO / "data" / "raw"                 # fake PII, inputs only
RAW_TRANSACTIONS, CLEAN_TRANSACTIONS = "transactions_raw.csv", CLEAN_TRANSACTIONS_FILE
RAW_INTERACTIONS, CLEAN_INTERACTIONS = "interactions_raw.csv", CLEAN_INTERACTIONS_FILE


# ---------------------------------------------------------------------------
# A: transactions
# ---------------------------------------------------------------------------
def sanitize_transactions(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Raw transaction rows -> clean rows, in the same order.

    customer_id becomes customer_token; only CLEAN_TRANSACTION_COLUMNS are kept, so name, email,
    phone, dob, address, bsb, account_number and description (which can contain names, e.g.
    "TRANSFER TO J CITIZEN") are all dropped.
    """
    tokened = [{**row, "customer_token": tokenise(row["customer_id"])} for row in rows]
    clean = keep_columns(tokened, CLEAN_TRANSACTION_COLUMNS)
    for row in clean:
        _check(row, CleanTransaction)
    return clean


# ---------------------------------------------------------------------------
# B: interactions (history CSV and the mock input form)
# ---------------------------------------------------------------------------
def sanitize_interaction(row: Mapping[str, Any]) -> dict[str, str]:
    """One raw interaction (a history row or a form submission) -> one clean row.

    customer_id -> customer_token, staff_id -> staff_token (empty for self-service forms), the
    free text becomes keyword flags ("JOB_LOSS|CANT_AFFORD") and the text itself is thrown away.
    """
    staff_id = (row.get("staff_id") or "").strip()
    flags = scrub_text(row.get("text") or "", names=[row.get("full_name") or "", row.get("staff_name") or ""])
    tokened = {
        **row,
        "customer_token": tokenise(row["customer_id"]),
        "staff_token": tokenise(staff_id, prefix="staff_") if staff_id else "",
        "form_status": row.get("form_status") or "",
        "callback_due": row.get("callback_due") or "",
        "flags": "|".join(flags),
    }
    clean = keep_columns([tokened], CLEAN_INTERACTION_COLUMNS)[0]    # "text" is not on the list: gone
    _check(clean, CleanInteraction)
    return clean


def sanitize_interactions(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Many raw interactions -> clean rows, sorted by date then customer (a fixed, repeatable order)."""
    return sort_interactions([sanitize_interaction(r) for r in rows])


def sort_interactions(clean_rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(clean_rows, key=lambda r: (r["date"], r["customer_token"]))


def add_interaction(raw_row: Mapping[str, Any], out_dir: Path | str | None = None) -> dict[str, str]:
    """B's mock input form (B5): sanitize ONE new raw interaction and add it to the clean data.

    The raw row (with its PII and free text) is never stored: only the clean row is written to
    data/clean/interactions.csv (kept in date order). Returns the clean row.
    """
    path = Path(out_dir or clean_dir()) / CLEAN_INTERACTIONS
    if not path.exists():
        raise FileNotFoundError("There's no clean interaction data yet. Run `python scripts/reset_demo.py` first.")
    clean = sanitize_interaction(raw_row)
    write_csv(path, sort_interactions(read_csv(path) + [clean]), CLEAN_INTERACTION_COLUMNS)
    return clean


# ---------------------------------------------------------------------------
# Checks and files
# ---------------------------------------------------------------------------
def _check(clean_row: dict[str, str], model) -> None:
    """A clean row must fit the shared schema (tokens, enums, dates) and contain no PII."""
    model(**clean_row)
    assert_no_pii(clean_row)


def read_csv(path: Path | str) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path | str, rows: list[dict[str, str]], columns: list[str]) -> None:
    """Write a clean CSV (Python's csv defaults, the same format as mock_input_output)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, columns)
        writer.writeheader()
        writer.writerows(rows)


def sanitize_all(raw_dir: Path | str = RAW_DIR, out_dir: Path | str | None = None) -> dict[str, int]:
    """Sanitize both raw files into `out_dir` (default: shared.config.clean_dir(), i.e. data/clean).
    Every row is checked before anything is written, so a bad file writes nothing.
    Returns how many rows went into each clean file."""
    raw_dir, out_dir = Path(raw_dir), Path(out_dir or clean_dir())
    transactions = sanitize_transactions(read_csv(raw_dir / RAW_TRANSACTIONS))
    interactions = sanitize_interactions(read_csv(raw_dir / RAW_INTERACTIONS))
    write_csv(out_dir / CLEAN_TRANSACTIONS, transactions, CLEAN_TRANSACTION_COLUMNS)
    write_csv(out_dir / CLEAN_INTERACTIONS, interactions, CLEAN_INTERACTION_COLUMNS)
    return {CLEAN_TRANSACTIONS: len(transactions), CLEAN_INTERACTIONS: len(interactions)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Sanitize raw bank data into clean data (no PII).")
    parser.add_argument("--raw", default=str(RAW_DIR), help="folder with the raw CSVs (default: data/raw)")
    parser.add_argument("--clean", default=str(clean_dir()), help="folder for the clean CSVs (default: data/clean)")
    args = parser.parse_args()
    counts = sanitize_all(args.raw, args.clean)
    for name, n in counts.items():
        print(f"{Path(args.clean) / name}: {n} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
