"""The FastAPI app: the routers, error handling, the PII check on every response, and the built
React UI (web/dist) served at /.

    python app.py                       # http://127.0.0.1:8600 (see app.py)

Rules (docs/REACT_UI_PLAN.md):
  - bound to 127.0.0.1 by default (app.py; --host opens it to a network, for filming only);
    CORS only for the Vite dev server (npm run dev)
  - invalid input -> 422; LedgerError / PolicyError / ExecutionError -> 400 with their readable message
  - every JSON response is PII-checked with shared.pii_guard.find_pii (defence in depth); anything
    that looks like PII is blocked with a 500 that names only the KIND of PII. The only exceptions are
    the RAW_VIEWS below: local views of the demo's fake raw data on the A and B pages
  - error messages never echo what was typed (it might be PII)
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from api import account, actions, demo, interaction, ledger, policy
from api import customer, live, westpac          # the live apps: /customer and /westpac (ui/live-apps)
from api.common import REPO
from nodes.account import AccountError
from nodes.actions import ExecutionError
from nodes.ledger.store import LedgerError
from nodes.policy import PolicyError
from shared.config import HASH_PATTERN
from shared.pii_guard import PIIError, find_pii

WEB_DIST = REPO / "web" / "dist"
DEV_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]     # Vite dev server only
_HASH = re.compile(HASH_PATTERN)
# agent.py's run ids: "<YYYYmmdd-HHMMSS>-<runbook>-<mode>-<4 hex>", e.g. 20261116-104542-policy_sweep-no-ai-f431
_RUN_ID = re.compile(r"^\d{8}-\d{6}-[a-z0-9_]+-(ai|no-ai)-[0-9a-f]{4}$")


# ---------------------------------------------------------------------------
# PII check on every response
# ---------------------------------------------------------------------------
def _machine_made(key: str, value: Any) -> bool:
    """Values the system generates itself, in a fixed shape that can't hold personal information,
    but whose runs of digits can look like a phone or card number to the PII patterns:
    sha256 hashes (64 hex characters) and agent.py's timestamped run ids."""
    if not isinstance(value, str):
        return False
    return bool(_HASH.match(value)) or (key == "run_id" and bool(_RUN_ID.match(value)))


def _without_hashes(value: Any) -> Any:
    """The response with hashes and run ids left out, ready for the PII scan."""
    if isinstance(value, list):
        return [_without_hashes(v) for v in value]
    if isinstance(value, dict):
        return {k: _without_hashes(v) for k, v in value.items() if not _machine_made(k, v)}
    return value


def pii_in(body: bytes, exempt_field: Optional[str] = None) -> list[str]:
    """The kinds of PII found in a JSON response body (never the values). `exempt_field` leaves out
    one top-level field of the response (only for a RAW_VIEWS entry, below)."""
    try:
        data = json.loads(body)
    except ValueError:
        return find_pii(body.decode("utf-8", errors="replace"))
    if exempt_field and isinstance(data, dict):
        data = {k: v for k, v in data.items() if k != exempt_field}
    return find_pii(_without_hashes(data))


# THE allow-list: the only responses NOT fully PII-checked. They are LOCAL views of the demo's raw
# data (fake PII), shown so people can see what the sanitizer keeps and throws away
# (docs/MCP_PLAN.md §6). Raw data never goes through MCP or the AI, and none of it is stored.
#   value WHOLE_RESPONSE  the whole (successful) response is the raw view
#   value "<field>"       only that top-level field is the raw view; the rest is still checked
# Everything else, and every error response, is checked. tests/test_api.py pins this list.
WHOLE_RESPONSE = "*"
RAW_VIEWS: dict[tuple[str, str], str] = {
    ("GET", "/api/account/raw-sample"): WHOLE_RESPONSE,        # A: one customer's raw row (+ the people picker)
    ("GET", "/api/interaction/form-options"): WHOLE_RESPONSE,  # B: customer/staff pickers + the 2 examples
    ("POST", "/api/interaction/submit"): "thrown_away",        # B: what the sanitizer threw away
    # Customer-only views (the customer app): the customer's OWN name and transactions, shown only to them.
    ("GET", "/api/customer/sign-in-options"): WHOLE_RESPONSE,  # who you can sign in as (demo)
    ("GET", "/api/customer/overview"): WHOLE_RESPONSE,         # your accounts and recent transactions
}


class PIIGuard(BaseHTTPMiddleware):
    """Checks every JSON response from /api before it leaves the server (except the RAW_VIEWS)."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        if not request.url.path.startswith("/api") or "json" not in response.headers.get("content-type", ""):
            return response
        body = b"".join([chunk async for chunk in response.body_iterator])
        raw_view = RAW_VIEWS.get((request.method, request.url.path)) if response.status_code < 300 else None
        kinds = [] if raw_view == WHOLE_RESPONSE else pii_in(body, exempt_field=raw_view)
        if kinds:
            return JSONResponse({"detail": f"Response blocked: PII detected ({', '.join(kinds)}). Nothing was sent."},
                                status_code=500)
        headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        return Response(body, status_code=response.status_code, headers=headers, media_type=response.media_type)


# ---------------------------------------------------------------------------
# Errors -> readable JSON {"detail": "..."}
# ---------------------------------------------------------------------------
def _problems(errors: list[dict[str, Any]]) -> str:
    """Say WHERE and WHAT is wrong, never the value that was typed."""
    parts = []
    for e in errors:
        loc = ".".join(str(p) for p in e.get("loc", ()) if p not in ("body",))
        msg = str(e.get("msg", "invalid")).removeprefix("Value error, ")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts)


def _register_errors(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def request_invalid(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"detail": _problems(list(exc.errors()))}, status_code=422)

    @app.exception_handler(ValidationError)
    async def model_invalid(_request: Request, exc: ValidationError) -> JSONResponse:
        # e.g. check_action() / approve() validating ActionRequest / Approval
        return JSONResponse({"detail": _problems(exc.errors(include_input=False, include_url=False))},
                            status_code=422)

    async def refused(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    for kind in (LedgerError, PolicyError, ExecutionError, AccountError, PIIError):
        app.add_exception_handler(kind, refused)


# ---------------------------------------------------------------------------
# The app
# ---------------------------------------------------------------------------
_NO_BUILD = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Customer Guardian</title></head>
<body style="font-family: sans-serif; padding: 2rem"><h1>Customer Guardian API is running</h1>
<p>The React UI hasn't been built yet. Run <code>cd web &amp;&amp; npm ci &amp;&amp; npm run build</code>,
then reload. The API is at <a href="/api/docs">/api/docs</a>.</p></body></html>"""


def create_app(web_dist: Path = WEB_DIST) -> FastAPI:
    app = FastAPI(title="Customer Guardian API", docs_url="/api/docs", redoc_url=None,
                  openapi_url="/api/openapi.json")
    app.add_middleware(PIIGuard)
    app.add_middleware(CORSMiddleware, allow_origins=DEV_ORIGINS, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"])
    _register_errors(app)
    for module in (account, interaction, ledger, policy, actions, demo):
        app.include_router(module.router)
    for module in (customer, westpac, live):           # the live apps (ui/live-apps)
        app.include_router(module.router)

    if (web_dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")
    else:
        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        def not_built() -> str:
            return _NO_BUILD
    return app


app = create_app()
