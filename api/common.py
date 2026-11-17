"""Small shared pieces for the API routers: paths, fixed lists for the UI and the call-code rule."""
from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
for _p in (REPO, REPO / "scripts"):           # load_fixtures lives in scripts/ (not a package)
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.config import COLLECTIONS_ACTIONS, CREDIT_OFFER_ACTIONS, ActionType  # noqa: E402

HERO = "cust_af4200"                          # the SPEC story's customer
# The staff tokens the Streamlit pages offer (D.py's list; E.py offers the first two of these).
STAFF = ["staff_44a", "staff_19c", "staff_b38", "staff_9bb"]
# The actions D's "Check an action" form offers (same list as ui/pages/D.py; each group sorted,
# because set order changes between Python runs).
CHECKABLE = (sorted(a.value for a in COLLECTIONS_ACTIONS) + sorted(a.value for a in CREDIT_OFFER_ACTIONS)
             + [ActionType.VERIFY_CALLER.value])

HIDDEN = "(hidden)"

# One workflow at a time (sweeps, A's and B's runbooks, resets): a double click waits its turn.
RUN_LOCK = threading.RLock()
_server = None


def mcp_server():
    """One in-process MCP server for the A and B runbook runs (as ui/pages/A.py and B.py cache one)."""
    global _server
    if _server is None:
        from server import build_server
        _server = build_server()[0]
    return _server


def present_run(result) -> dict[str, Any]:
    """An agent.RunResult for the screen: status, each step's output, summary (call codes hidden)."""
    return hide_call_codes({"run_id": result.run_id, "runbook": result.runbook, "mode": result.mode,
                            "status": result.status, "summary": result.summary, "error": result.error,
                            "steps": [s.model_dump() for s in result.steps]})


def hide_call_codes(value: Any) -> Any:
    """Call codes are secrets between the bank and the customer. They are only ever shown in the
    customer's phone view (GET /api/actions/inbox/{token}); everywhere else they are replaced.
    Same rule as nodes/actions.py _hide_call_codes and nodes/policy.py _hide_codes."""
    if isinstance(value, list):
        return [hide_call_codes(v) for v in value]
    if isinstance(value, dict):
        return {k: (HIDDEN if k == "call_code" else hide_call_codes(v)) for k, v in value.items()}
    return value
