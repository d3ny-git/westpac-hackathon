# `nodes/`: one file (or folder) per pipeline node

| Node | File | Owner |
|---|---|---|
| A Account | `nodes/account.py` | Owner-A |
| B Interactions | `nodes/interaction.py` | Owner-B |
| C Ledger | `nodes/ledger/` (done: `store.py`, `chain.py`, `quiet_help.py`, `dashboard.py`, `tools.py`) | Owner-CD |
| D Policy | `nodes/policy.py` (done: P1–P4, recommendations, explain, 4 tools) | Owner-CD |
| E Actions | `nodes/actions.py` | Owner-E |

Your node file holds two kinds of code:
1. **Plain Python functions** that do the work (sanitize, score, execute, …). These don't know anything about MCP or AI.
2. **A `register(mcp)` function** that turns some of them into **tools** the AI can call.

You never edit `server.py`. It finds your `register(mcp)` automatically.

---

## Writing to the ledger

```python
from nodes.ledger import store
from shared.schemas import ScoreMessage

msg = ScoreMessage(customer_token="cust_af4200", source="ACCOUNT", score=63, band="HIGH",
                   reasons=["SALARY_STOPPED"], timestamp="2026-11-16T10:00:00")
entry_id = store.append("SCORE", msg.customer_token, msg.model_dump(mode="json"))   # -> "E-0001"
```

- **Need a new ID** for a promise, recommendation or message? Use `store.next_id("P")`, `store.next_id("R")` or `store.next_id("M")`. Never number them yourself, or IDs will clash.
- **Reading:** `store.read(customer_token="cust_af4200")`, `store.read(entry_type="PROMISE")`, `store.get("E-0001")`.
- **Refusals:** the ledger refuses bad data (wrong message shape, PII, a reused ID) and writes nothing. The error message tells you why.

---

## Adding your tools: copy this

```python
# nodes/account.py   (Owner-A: same idea for interaction.py and actions.py)
from shared.pii_guard import safe_tool


def score_all_customers():
    """Plain Python: does the real work. Test this on its own first."""
    ...


def register(mcp):
    """server.py calls this once to add this node's tools."""

    @mcp.tool()
    @safe_tool
    def account_score_all() -> list[dict]:
        """Score every customer from their transactions.

        Returns one score message per customer: customer_token, score, band, reasons.
        """
        return score_all_customers()
```

**The rules:**

| Rule | Why |
|---|---|
| `@mcp.tool()` on top, `@safe_tool` directly under it | `@safe_tool` blocks any output containing PII and turns errors into readable messages |
| Name tools `<node>_<what>`, e.g. `account_score_all`, `actions_pending` | Easy to tell which node a tool belongs to |
| **The docstring is what the AI reads.** Say what it does and what it returns, in plain words. | The AI picks tools by their description |
| **Type hints become the tool's inputs.** Use the shared types where you can, e.g. `customer_token: CustomerToken` (from `shared.schemas`), `entry_type: EntryType` (from `shared.config`) | The AI is told the exact format, and bad inputs are rejected before your code runs |
| Return a dict, a list of dicts, or Pydantic models (they're converted for you) | Tools always reply with JSON |
| Keep tools thin: call your plain Python function and return its result | Logic stays testable without MCP |
| **Never make a tool for something only a human may do** (e.g. approve or reject) | The AI must never be able to approve anything |

**Example with inputs** (from `nodes/ledger/tools.py`):
```python
from typing import Optional
from shared.config import EntryType
from shared.schemas import CustomerToken

@mcp.tool()
@safe_tool
def ledger_get_history(customer_token: CustomerToken, entry_type: Optional[EntryType] = None) -> list[dict]:
    """Everything the ledger holds about one customer, oldest first."""
    return store.read(customer_token=customer_token, entry_type=entry_type)
```

---

## Checking your tools work (no AI needed)

```bash
python server.py --list
# A  Account       2 tool(s): account_check_data, account_score_all   <- yours should appear here

python scripts/try_tool.py                     # every tool and its inputs
python scripts/try_tool.py account_score_all   # call one, exactly as the AI would
python scripts/try_tool.py ledger_get_history '{"customer_token": "cust_af4200"}'
```

| If you see… | It means |
|---|---|
| `not built yet, skipped` | `server.py` can't find your file. Check the name matches the table at the top. |
| `has no register(mcp) function` | Add the `register(mcp)` function |
| `ERROR: … validation error … customer_token` | The inputs you passed don't match the type hints |
| `ERROR: Output blocked: PII detected (…)` | Your tool tried to return personal information. Find where it comes from and remove it. |
| `ERROR: Error executing tool <name>` and nothing else | Your code crashed. The real error is printed above it in the terminal (the `[server]` / traceback lines). |
