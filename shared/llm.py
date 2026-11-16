"""The ONLY door to the AI (OpenRouter). Every AI call in Customer Guardian goes through here.

What this file guarantees, whoever calls it:
  1. Nothing is sent if it looks like PII (shared/pii_guard.py).
  2. temperature=0, so answers are as repeatable as possible.
  3. Every call is logged to data/runs/llm_calls.jsonl (gitignored) for the audit trail.
  4. The AI's reply is PII-checked too before anyone uses it.

Team rules:
  - Use `explain()` to turn results that are ALREADY tokens and codes into plain English
    (e.g. an "Explain this score" button).
  - `ask()` with tools is for agent.py's runbook loop.
  - NEVER call this from scoring, policy, sanitizing or approval code. Those stay plain Python.

Settings come from .env: OPENROUTER_API_KEY and OPENROUTER_MODEL.
Quick check that your key works:  python -m shared.llm
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

from shared.pii_guard import PIIError, assert_no_pii

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
LOG_FILE = REPO_ROOT / "data" / "runs" / "llm_calls.jsonl"


class LLMError(RuntimeError):
    """Anything that went wrong talking to the AI (missing key, network, bad reply)."""


@dataclass
class ToolCall:
    """One tool the AI asked to run, e.g. ToolCall(id="call_1", name="account_score_all", arguments={})."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMReply:
    text: str                      # the AI's written answer ("" if it only asked for tools)
    tool_calls: list[ToolCall]     # tools it wants to run next (empty if none)
    message: dict[str, Any]        # the assistant message, ready to append to `messages`
    model: str
    usage: dict[str, Any] = field(default_factory=dict)


_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        key = os.getenv("OPENROUTER_API_KEY")
        if not key:
            raise LLMError("OPENROUTER_API_KEY is not set. Add it to .env (ask Owner-CD for the value).")
        _client = OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=key,
            timeout=60,
            max_retries=2,
            default_headers={"X-Title": "Customer Guardian"},
        )
    return _client


def _model() -> str:
    model = os.getenv("OPENROUTER_MODEL")
    if not model:
        raise LLMError("OPENROUTER_MODEL is not set. Add it to .env, e.g. OPENROUTER_MODEL=z-ai/glm-5.3-flashx-legal")
    return model


def _log(entry: dict[str, Any]) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")


def _check_pii(obj: Any, base_log: dict[str, Any], event: str) -> None:
    try:
        assert_no_pii(obj)
    except PIIError as e:
        _log({**base_log, "event": event, "error": str(e)})  # logs the kind of PII, never the content
        raise


def ask(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    *,
    purpose: str = "explain",
    run_id: str | None = None,
) -> LLMReply:
    """Send a conversation to the AI and return its reply.

    messages: OpenAI-style chat messages, e.g. [{"role": "user", "content": "..."}]
    tools:    OpenAI-style tool definitions (agent.py builds these from the MCP server)
    purpose:  short label for the log, e.g. "explain", "runbook:a_account"
    run_id:   groups calls from one agent.py run in the log
    """
    model = _model()
    base_log = {"run_id": run_id or uuid.uuid4().hex[:8], "purpose": purpose, "model": model}

    # 1. Nothing leaves this machine if it looks like PII.
    _check_pii(messages, base_log, "BLOCKED_REQUEST")
    if tools:
        _check_pii(tools, base_log, "BLOCKED_REQUEST")

    request: dict[str, Any] = {"model": model, "messages": messages, "temperature": 0}
    if tools:
        request["tools"] = tools
        request["tool_choice"] = "auto"

    # 2. Call OpenRouter.
    started = time.monotonic()
    try:
        response = _get_client().chat.completions.create(**request)
    except OpenAIError as e:
        _log({**base_log, "event": "ERROR", "error": str(e)})
        raise LLMError(f"OpenRouter call failed: {e}") from e
    duration_ms = round((time.monotonic() - started) * 1000)

    if not response.choices:
        _log({**base_log, "event": "ERROR", "error": "empty response"})
        raise LLMError("OpenRouter returned no answer.")
    msg = response.choices[0].message

    # 3. Turn the reply into simple Python objects.
    tool_calls: list[ToolCall] = []
    for tc in msg.tool_calls or []:
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError as e:
            _log({**base_log, "event": "ERROR", "error": f"invalid tool arguments for {tc.function.name}"})
            raise LLMError(f"The AI sent invalid arguments for tool {tc.function.name!r}.") from e
        tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

    text = msg.content or ""
    message: dict[str, Any] = {"role": "assistant", "content": text or None}
    if tool_calls:
        message["tool_calls"] = [
            {"id": c.id, "type": "function",
             "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
            for c in tool_calls
        ]

    # 4. The reply must be PII-free too (the AI never has any, so this catches made-up details).
    _check_pii(message, base_log, "BLOCKED_REPLY")

    usage = response.usage.model_dump() if response.usage else {}
    reply = LLMReply(text=text, tool_calls=tool_calls, message=message,
                     model=response.model or model, usage=usage)

    # 5. Audit log (everything here has passed the PII check).
    _log({**base_log, "event": "OK", "duration_ms": duration_ms,
          "request": messages, "tools": [t["function"]["name"] for t in tools or []],
          "reply": message, "usage": usage})
    return reply


EXPLAIN_SYSTEM_PROMPT = (
    "You explain results from Customer Guardian, a bank hardship tool, to bank staff. "
    "Use ONLY the facts provided. Never invent numbers, customers, reasons or names. "
    "Customers are tokens like cust_xxxxxx; refer to them only by token. "
    "You do not make decisions; describe what the rules found. "
    "Write plain English in at most {max_sentences} sentences."
)


def explain(
    facts: dict[str, Any],
    question: str = "Explain this result.",
    *,
    max_sentences: int = 3,
    run_id: str | None = None,
) -> str:
    """Turn tool/rule output into a short plain-English explanation.

    Example (UI page A):
        text = explain({"score": score_msg, "rules": account_rules()},
                       "Why does this customer have this score?")
    """
    messages = [
        {"role": "system", "content": EXPLAIN_SYSTEM_PROMPT.format(max_sentences=max_sentences)},
        {"role": "user", "content": f"{question}\n\nFacts (JSON):\n"
                                    f"{json.dumps(facts, indent=2, sort_keys=True, default=str)}"},
    ]
    return ask(messages, purpose="explain", run_id=run_id).text.strip()


if __name__ == "__main__":
    print(f"Model: {_model()}")
    r = ask([{"role": "user", "content": "Reply with exactly: OK"}], purpose="selftest")
    print(f"Reply: {r.text!r}")
    print(f"Usage: {r.usage}")
    print(f"Logged to: {LOG_FILE}")
