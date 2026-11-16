"""PII guard: detects personal information so it never reaches the AI or leaves the machine.

Used by shared/llm.py (every request and reply) and by any code that needs to check
data is clean. It reports the KIND of PII found, never the value itself.
"""
from __future__ import annotations

import json
import re
from typing import Any


class PIIError(ValueError):
    """Raised when something that looks like PII is found. The message never contains the PII itself."""


PATTERNS: dict[str, re.Pattern[str]] = {
    "EMAIL": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "AU_MOBILE": re.compile(r"(?<!\d)(?:\+?61[ -]?|0)4\d{2}[ -]?\d{3}[ -]?\d{3}(?!\d)"),
    "AU_LANDLINE": re.compile(r"(?<!\d)(?:\+?61[ -]?|0)[2378][ -]?\d{4}[ -]?\d{4}(?!\d)"),
    "BSB": re.compile(r"(?<!\d)\d{3}-\d{3}(?!\d)"),
    "DATE_OF_BIRTH": re.compile(r"(?<!\d)\d{1,2}/\d{1,2}/(?:19|20)\d{2}(?!\d)"),
}
_CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")


def _luhn_ok(digits: str) -> bool:
    """Card numbers pass the Luhn checksum; random long numbers usually don't."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def find_pii(obj: Any) -> list[str]:
    """Return the KINDS of PII found (e.g. ["EMAIL", "AU_MOBILE"]), never the values."""
    text = obj if isinstance(obj, str) else json.dumps(obj, default=str, ensure_ascii=False)
    kinds = [kind for kind, pattern in PATTERNS.items() if pattern.search(text)]
    for match in _CARD_CANDIDATE.finditer(text):
        if _luhn_ok(re.sub(r"\D", "", match.group())):
            kinds.append("CARD_NUMBER")
            break
    return kinds


def assert_no_pii(obj: Any) -> None:
    """Raise PIIError if `obj` (str, dict, list, ...) contains anything that looks like PII."""
    kinds = find_pii(obj)
    if kinds:
        raise PIIError(f"PII detected ({', '.join(kinds)}). Nothing was sent.")
