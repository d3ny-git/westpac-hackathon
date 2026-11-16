"""Run a runbook: the AI follows a markdown checklist and calls MCP tools, one step at a time.

    python agent.py runbooks/ledger_check.md
    python agent.py runbooks/b_interaction.md --var token=cust_af4200
    python agent.py runbooks/policy_sweep.md --no-ai      # same steps, no AI (demo fallback)

How it stays deterministic:
  1. The runbook lists the exact steps (tool names, in order, with any fixed arguments).
  2. The AI is only given THOSE tools, nothing else from the server.
  3. Every tool call the AI makes must be the NEXT step in the list. Anything else (wrong tool,
     wrong order, different arguments, an extra call) stops the run as OFF_SCRIPT.
  4. The tool is run with the RUNBOOK's arguments, never ones the AI made up.
  5. When all steps are done, the AI writes a short summary using only what the tools returned.
  6. A step can have a stop rule (e.g. stop if the ledger was tampered with). The run stops
     there, whatever the AI would have done next.

--no-ai runs exactly the same steps without the AI. It's the demo fallback (no key or no Wi-Fi
needed) and the proof that the AI changes nothing: both modes leave the ledger identical.
The AI decides nothing: the tools (plain Python) do the work. Everything is logged to
data/runs/<run_id>.jsonl, and every AI call goes through shared/llm.py (PII check, temperature 0).

Runbook format: see runbooks/README.md.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml
from mcp import Client, StdioServerParameters
from pydantic import BaseModel

from shared import llm
from shared.pii_guard import PIIError

REPO = Path(__file__).resolve().parent
RUNS_DIR = REPO / "data" / "runs"           # gitignored


# ---------------------------------------------------------------------------
# Runbooks
# ---------------------------------------------------------------------------
class Step(BaseModel):
    tool: str
    args: dict[str, Any] = {}
    stop_if: Optional[str] = None             # e.g. "valid == false" (see check_stop)
    stop_message: Optional[str] = None        # what to report when it stops, e.g. "LEDGER TAMPERED"


_CONDITION = re.compile(r"^\s*([A-Za-z_][\w.]*)\s*(==|!=)\s*(.+?)\s*$")


def parse_condition(text: str) -> tuple[str, str, Any]:
    """A stop rule is deliberately simple: `field == value` or `field != value`.

    field can reach inside the tool's output with dots (e.g. report.valid); value is
    true / false / a number / text. Anything else is refused, so a runbook can't run code."""
    match = _CONDITION.match(text or "")
    if not match:
        raise ValueError(f"stop_if must look like 'field == value' or 'field != value', got {text!r}")
    field, op, raw = match.groups()
    return field, op, yaml.safe_load(raw)


def check_stop(step: Step, output: Any) -> bool:
    """True if this step's stop rule matches the tool's output."""
    if not step.stop_if:
        return False
    field, op, value = parse_condition(step.stop_if)
    current: Any = output
    for part in field.split("."):
        if not isinstance(current, dict) or part not in current:
            return False                      # field not in the output: the rule doesn't apply
        current = current[part]
    return (current == value) if op == "==" else (current != value)


class Runbook(BaseModel):
    name: str
    description: str = ""
    steps: list[Step]
    instructions: str                         # the markdown body: what the summary should say, etc.


def load_runbook(path: Path | str, variables: Optional[dict[str, str]] = None) -> Runbook:
    """Read a runbook file and fill in variables like {token} from --var token=...

    The file starts with a YAML block between two '---' lines (name, description, steps),
    followed by plain-English instructions.
    """
    text = Path(path).read_text()
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not match:
        raise ValueError(f"{path} must start with a '---' settings block (see runbooks/README.md)")
    settings, body = yaml.safe_load(match.group(1)) or {}, match.group(2).strip()
    variables = variables or {}

    def fill(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        missing = [v for v in re.findall(r"{(\w+)}", value) if v not in variables]
        if missing:
            raise ValueError(f"runbook needs --var {missing[0]}=...")
        return value.format(**variables)

    steps = []
    for raw in settings.get("steps") or []:
        step: dict[str, Any] = {"tool": raw} if isinstance(raw, str) else dict(raw)
        step["args"] = {k: fill(v) for k, v in (step.get("args") or {}).items()}
        if step.get("stop_if"):
            parse_condition(step["stop_if"])  # refuse a bad rule now, not halfway through a run
        steps.append(Step(**step))
    if not steps:
        raise ValueError(f"{path} has no steps")
    return Runbook(name=settings.get("name") or Path(path).stem, description=settings.get("description", ""),
                   steps=steps, instructions=fill(body))


# ---------------------------------------------------------------------------
# Results and logging
# ---------------------------------------------------------------------------
class StepResult(BaseModel):
    n: int                                    # 1, 2, 3 ...
    tool: str
    args: dict[str, Any]
    ok: bool
    output: Any = None                        # what the tool returned (or its error message)


class RunResult(BaseModel):
    run_id: str
    runbook: str
    mode: str                                 # "ai" or "no-ai"
    status: str                               # COMPLETED / STOPPED / OFF_SCRIPT / TOOL_ERROR / INCOMPLETE /
                                              # BLOCKED_PII / LLM_ERROR / SETUP_ERROR
    steps: list[StepResult] = []
    summary: str = ""
    error: Optional[str] = None
    log_file: str = ""


class RunLog:
    """One JSON line per event in data/runs/<run_id>.jsonl, so the D page can replay a run."""

    def __init__(self, run_id: str):
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        self.path = RUNS_DIR / f"{run_id}.jsonl"

    def write(self, event: str, **data: Any) -> None:
        line = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event, **data}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, default=str, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Talking to the MCP server
# ---------------------------------------------------------------------------
def server_params() -> StdioServerParameters:
    """Start server.py as a separate process (the same way any MCP client would)."""
    return StdioServerParameters(command=sys.executable, args=[str(REPO / "server.py")],
                                 cwd=str(REPO), env=dict(os.environ))


def tool_output(result) -> Any:
    """Turn an MCP tool result into plain JSON data.

    Lists arrive as structured_content["result"]; single objects arrive as JSON text."""
    text = "\n".join(getattr(c, "text", "") for c in result.content)
    if result.is_error:
        return text
    sc = result.structured_content
    if sc is not None:
        return sc["result"] if set(sc) == {"result"} else sc
    try:
        return json.loads(text) if text else None
    except ValueError:
        return text


def openai_tool(tool) -> dict[str, Any]:
    """An MCP tool description in the format OpenRouter / OpenAI expects."""
    return {"type": "function", "function": {"name": tool.name, "description": tool.description or "",
                                             "parameters": tool.input_schema}}


def args_match(from_ai: dict[str, Any], expected: dict[str, Any]) -> bool:
    """The AI may leave arguments out (the runbook's are used anyway), but may not change or add any."""
    given = {k: v for k, v in (from_ai or {}).items() if v is not None}
    return all(k in expected and expected[k] == v for k, v in given.items())


def system_prompt(rb: Runbook) -> str:
    lines = [f"{i}. {s.tool}" + (f" with arguments {json.dumps(s.args)}" if s.args else "")
             for i, s in enumerate(rb.steps, 1)]
    return (
        "You are running a Customer Guardian runbook. Follow it exactly.\n"
        "Call these tools in this exact order, one at a time:\n" + "\n".join(lines) + "\n"
        "Do not call any other tool, skip a step or repeat one. Use only facts the tools return. "
        "Customers are tokens like cust_af4200: never invent names, numbers or reasons. "
        "When every step is done you will be asked for the summary described below.\n\n"
        f"--- RUNBOOK: {rb.name} ---\n{rb.instructions}"
    )


# ---------------------------------------------------------------------------
# Running the steps
# ---------------------------------------------------------------------------
async def _available_tools(rb: Runbook, client: Client, result: RunResult) -> Optional[dict]:
    available = {t.name: t for t in (await client.list_tools()).tools}
    missing = [s.tool for s in rb.steps if s.tool not in available]
    if missing:
        result.status, result.error = "SETUP_ERROR", f"tool not on the server (node not built yet?): {missing[0]}"
        return None
    return available


async def _do_step(client: Client, step: Step, n: int, result: RunResult, log: RunLog) -> Optional[Any]:
    """Run one step with the RUNBOOK's arguments. Returns the output, or None if the run must end
    here (tool error or stop rule), in which case result.status is already set."""
    mcp_result = await client.call_tool(step.tool, step.args)
    output = tool_output(mcp_result)
    record = StepResult(n=n, tool=step.tool, args=step.args, ok=not mcp_result.is_error, output=output)
    result.steps.append(record)
    log.write("step", **record.model_dump())
    if mcp_result.is_error:
        result.status, result.error = "TOOL_ERROR", f"{step.tool} failed: {output}"
        return None
    if check_stop(step, output):
        result.status = "STOPPED"
        result.error = f"stopped at step {n} ({step.tool}): {step.stop_if}"
        result.summary = step.stop_message or f"Stopped: {step.stop_if}"
        log.write("stopped", step=n, rule=step.stop_if, message=result.summary)
        return None
    return output


async def _run_no_ai(rb: Runbook, client: Client, result: RunResult, log: RunLog) -> None:
    """--no-ai: the same steps, in the same order, with the same arguments. No AI involved."""
    if await _available_tools(rb, client, result) is None:
        return
    for n, step in enumerate(rb.steps, 1):
        if await _do_step(client, step, n, result, log) is None:
            return
    result.status = "COMPLETED"
    result.summary = f"All {len(rb.steps)} steps completed without the AI. See each step's output."


async def _run_ai(rb: Runbook, client: Client, result: RunResult, log: RunLog) -> None:
    available = await _available_tools(rb, client, result)
    if available is None:
        return
    offered = [openai_tool(available[name]) for name in dict.fromkeys(s.tool for s in rb.steps)]

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt(rb)},
                                      {"role": "user", "content": "Start the runbook now."}]
    done = 0
    for _turn in range(len(rb.steps) + 2):                 # a little slack, never an endless loop
        reply = llm.ask(messages, tools=offered, purpose=f"runbook:{rb.name}", run_id=result.run_id)
        if not reply.tool_calls:
            break                                          # the AI stopped calling tools
        messages.append(reply.message)
        for call in reply.tool_calls:
            expected = rb.steps[done] if done < len(rb.steps) else None
            if expected is None or call.name != expected.tool or not args_match(call.arguments, expected.args):
                result.status = "OFF_SCRIPT"
                result.error = (f"step {done + 1}: the AI called {call.name}({json.dumps(call.arguments)}) "
                                f"but the runbook says " + (f"{expected.tool}({json.dumps(expected.args)})"
                                                            if expected else "there are no more steps"))
                log.write("off_script", step=done + 1, called=call.name, arguments=call.arguments,
                          expected=expected.tool if expected else None)
                return
            output = await _do_step(client, expected, done + 1, result, log)   # the RUNBOOK's arguments
            if output is None:
                return                                     # tool error or stop rule: the run ends here
            messages.append({"role": "tool", "tool_call_id": call.id,
                             "content": json.dumps(output, default=str, ensure_ascii=False)})
            done += 1
        if done == len(rb.steps):
            break

    if done < len(rb.steps):
        result.status = "INCOMPLETE"
        result.error = f"the AI stopped after {done} of {len(rb.steps)} steps"
        return

    # Every step done: ask for the summary, with no tools available.
    messages.append({"role": "user", "content": "All steps are done. Now write the summary the runbook asks for, "
                                                "using only what the tools returned."})
    result.summary = llm.ask(messages, purpose=f"runbook:{rb.name}:summary", run_id=result.run_id).text.strip()
    result.status = "COMPLETED"


async def run_async(path: Path | str, variables: Optional[dict[str, str]] = None, *, ai: bool = True,
                    server=None) -> RunResult:
    """Run a runbook, with the AI (ai=True) or without it (ai=False, same steps).
    `server` is for tests (an in-process MCP server); normally server.py is started as a separate process."""
    rb = load_runbook(path, variables)
    mode = "ai" if ai else "no-ai"
    run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{rb.name}-{mode}-{uuid.uuid4().hex[:4]}"
    log = RunLog(run_id)
    result = RunResult(run_id=run_id, runbook=rb.name, mode=mode, status="RUNNING", log_file=str(log.path))
    log.write("start", runbook=rb.name, mode=mode, steps=[s.model_dump() for s in rb.steps], variables=variables or {})
    async with Client(server if server is not None else server_params()) as client:
        # Caught INSIDE the client block: errors that escape it come out wrapped in an ExceptionGroup.
        try:
            await (_run_ai if ai else _run_no_ai)(rb, client, result, log)
        except PIIError as exc:
            result.status, result.error = "BLOCKED_PII", str(exc)
        except llm.LLMError as exc:
            result.status, result.error = "LLM_ERROR", str(exc)
    log.write("finish", status=result.status, summary=result.summary, error=result.error)
    return result


def run(path: Path | str, variables: Optional[dict[str, str]] = None, *, ai: bool = True,
        server=None) -> RunResult:
    """Run a runbook (blocking). Returns a RunResult with the status, each step's output and the summary."""
    return asyncio.run(run_async(path, variables, ai=ai, server=server))


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Customer Guardian runbook (with the AI, or --no-ai).")
    parser.add_argument("runbook", help="e.g. runbooks/ledger_check.md")
    parser.add_argument("--var", action="append", default=[], metavar="NAME=VALUE",
                        help="fill a {NAME} in the runbook, e.g. --var token=cust_af4200")
    parser.add_argument("--no-ai", action="store_true", help="run the same steps without the AI")
    args = parser.parse_args()
    variables = dict(v.split("=", 1) for v in args.var)

    result = run(args.runbook, variables, ai=not args.no_ai)
    print(f"Runbook {result.runbook} ({result.mode}): {result.status}")
    for s in result.steps:
        print(f"  {'✔' if s.ok else '✘'} {s.n}. {s.tool}")
    if result.error:
        print(f"  {result.error}")
    if result.summary:
        print(f"\n{result.summary}")
    print(f"\nLog: {result.log_file}")
    return 0 if result.status == "COMPLETED" else 1     # STOPPED is a non-zero exit too


if __name__ == "__main__":
    sys.exit(main())
