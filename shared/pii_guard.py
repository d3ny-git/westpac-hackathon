"""PII guard: detects personal information so it never reaches the AI or leaves the machine.

Used by shared/llm.py (every request and reply), by @safe_tool (every MCP tool's output),
and by any code that needs to check data is clean. It reports the KIND of PII found,
never the value itself.
"""
from __future__ import annotations

import functools
import inspect
import json
import re
from typing import Any, Callable

from pydantic import ValidationError
from pydantic_core import to_jsonable_python


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


# ---------------------------------------------------------------------------
# @safe_tool: wrap every MCP tool with this (see nodes/README.md)
# ---------------------------------------------------------------------------
def _tool_error(message: str) -> Exception:
    """Build the MCP error the AI is allowed to read. Imported here so pii_guard
    doesn't need the mcp package unless a tool is actually used."""
    from mcp.server.mcpserver.exceptions import ToolError
    if find_pii(message):                      # never let PII escape through an error message
        message = "the tool failed (details withheld: they contained personal information)"
    return ToolError(message)


def _check_output(result: Any) -> Any:
    # 1. Turn Pydantic models, dates, enums etc. into plain JSON-friendly values.
    clean = to_jsonable_python(result)
    # 2. Block the whole result if anything looks like PII.
    kinds = find_pii(clean)
    if kinds:
        raise _tool_error(f"Output blocked: PII detected ({', '.join(kinds)}).")
    return clean


def _explain_failure(exc: Exception) -> Exception | None:
    """Turn failures we expect into a readable error for the AI. Return None for real crashes."""
    if isinstance(exc, PIIError):
        return _tool_error(str(exc))
    if isinstance(exc, ValidationError):
        # Pydantic messages can include the bad input value, so only say WHERE and WHAT.
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'input'}: {e['msg']}"
                             for e in exc.errors(include_input=False, include_url=False))
        return _tool_error(f"Invalid data: {problems}")
    if type(exc).__name__ in {"LedgerError", "ToolError"}:   # expected refusals from our own code
        return _tool_error(str(exc))
    return None


def safe_tool(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator for every MCP tool. Put it directly UNDER @mcp.tool():

        @mcp.tool()
        @safe_tool
        def ledger_get_history(customer_token: str) -> list[dict]:
            ...

    What it does:
      - converts the result to plain JSON (you can return Pydantic models, lists of them, dicts)
      - blocks the result if it contains anything that looks like PII
      - turns expected failures (PII, invalid data, ledger refusals) into a clear message
        the AI can read; any other crash shows only "Error executing tool <name>"
    """
    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return _check_output(await fn(*args, **kwargs))
            except Exception as exc:
                friendly = _explain_failure(exc)
                if friendly is None:
                    raise
                raise friendly from exc
        return async_wrapper

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return _check_output(fn(*args, **kwargs))
        except Exception as exc:
            friendly = _explain_failure(exc)
            if friendly is None:
                raise
            raise friendly from exc
    return wrapper
