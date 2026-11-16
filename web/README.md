# Customer Guardian: GEL React UI

A second UI for Customer Guardian, built with Westpac's design system **GEL** (`@westpac/ui` 1.21 +
`@westpac/style-config`, WBC brand, Tailwind CSS v4), on branch `ui/gel-react`. It has the same
features as the Streamlit pages (`ui/pages/C.py`, `D.py`, `E.py`), which stay unchanged, plus a
Home page whose 10-step story guide ticks itself as the demo is played.

- `api/` (Python, FastAPI) wraps the existing node functions as JSON. No business logic lives there.
- `web/` (this folder) is React 18 + Vite + TypeScript + TanStack Query.
- `app.py` serves both on **one port**: http://127.0.0.1:8600 (API at `/api`, UI at `/`).

GEL is set up as GEL's own `installing-westpac-ui` guide says, with **no brand font files** (GEL's
fallback system fonts; the brand fonts are commercial) and light mode only.

## Setup (fresh clone)

Needs **Node 22+** (GEL's requirement; `node --version`) and Python 3.11+.

```bash
# Python: the project's requirements + the web extras (fastapi, uvicorn, httpx)
pip install -r requirements.txt -r requirements-web.txt

# The UI: install exactly what package-lock.json says, then build web/dist
cd web
npm ci
npm run build
cd ..
```

If your system Node is older than 22, install Node 22 LTS (e.g. `nvm install 22`, or the official
tarball from nodejs.org) and put its `bin` first on your `PATH` for these commands.

## Run

```bash
python app.py                    # http://127.0.0.1:8600
python app.py --port 8650        # another port
```

It uses the same ledger as everything else: `GUARDIAN_DB` (environment or `.env`), else
`data/guardian.db`. To try it without touching the demo ledger, point it at a temporary file:

```bash
GUARDIAN_DB=/tmp/guardian-try.db GUARDIAN_RUNS_DIR=/tmp/guardian-try-runs python app.py
```

Then open http://127.0.0.1:8600, use **Demo controls → Load demo data** (stage `start`) and follow the
Home page's guide, or `docs/DEMO.md`. Policy sweeps "with the AI" and "Explain in plain English"
need the OpenRouter settings in `.env`; everything else works without them.

### Developing the UI

```bash
python app.py                    # the API on 8600
cd web && npm run dev            # http://127.0.0.1:5173, hot reload, /api forwarded to 8600
```

The API allows CORS only from this Vite dev server.

## Checks

```bash
python -m pytest                 # all Python tests (incl. tests/test_api.py when present)
cd web
npm run build                    # production build into web/dist
npx tsc --noEmit                 # type-check
npx playwright install chromium  # once
PYTHON=python npx playwright test   # e2e: the 10-step story in a real browser
```

The Playwright run builds the UI and starts `app.py --port 8650` itself, against a temporary
`GUARDIAN_DB` and run-log folder (under the system temp folder, or `GUARDIAN_E2E_DIR`), so the demo
ledger is never touched. It never calls the AI. Set `PYTHON` to the interpreter that has the
requirements installed.

## Rules the UI keeps

- Approve / Reject are buttons a person clicks (API endpoints for the UI only); they are never MCP
  tools, and they need a staff token.
- A call code is shown only in the customer's phone view (`GET /api/actions/inbox/{token}`); the
  ledger view, explanations and run logs show `(hidden)`.
- Every JSON response is checked for PII (`shared.pii_guard.find_pii`) before it leaves the server.
- The server binds to 127.0.0.1 only. All times come from `shared.config.now()` (16 Nov 2026 10:00).
- One tab, always fresh: every view refetches every 3 seconds and on focus, and after every button.
