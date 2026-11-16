"""Customer Guardian with the GEL React UI: one command, one port.

    python app.py                     # http://127.0.0.1:8600 (API at /api, UI at /)
    python app.py --port 8650         # another port
    python app.py --live              # + automatic sweeps and AI intake reviews (api/live.py)

The live apps (branch ui/live-apps) are on the same port: /customer/ (the customer app) and
/westpac/ (the Westpac dashboard). The walkthrough stays at /.

It builds nothing: build the UI once with `cd web && npm ci && npm run build` (needs Node 22+).
It always binds to 127.0.0.1, so it's only reachable from this machine.

Uses the same ledger as everything else: GUARDIAN_DB (from the environment or .env), or
data/guardian.db by default. GUARDIAN_RUNS_DIR optionally moves the policy-sweep run logs
(default data/runs/, the same folder the Streamlit pages read). Tests and demos that must not touch
the real demo ledger set GUARDIAN_DB to a temporary file.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parent
HOST = "127.0.0.1"
DEFAULT_PORT = 8600


def main() -> None:
    load_dotenv(REPO / ".env")
    parser = argparse.ArgumentParser(description="Serve the Customer Guardian API and the GEL React UI.")
    parser.add_argument("--port", type=int, default=int(os.getenv("GUARDIAN_PORT", DEFAULT_PORT)),
                        help=f"port on {HOST} (default {DEFAULT_PORT})")
    parser.add_argument("--live", action="store_true",
                        help="run the automatic sweeps and AI intake reviews in the background (api/live.py)")
    args = parser.parse_args()

    import uvicorn

    from api.main import WEB_DIST, app      # imported after .env is loaded: agent.py reads GUARDIAN_RUNS_DIR
    from nodes.ledger import store

    if not (WEB_DIST / "index.html").is_file():
        print("Note: web/dist isn't built yet, so only the API works. Run: cd web && npm ci && npm run build")
    missing = [k for k in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL") if not os.getenv(k)]
    if missing:
        print(f"Note: the AI buttons won't work: {', '.join(missing)} not set. Put them in {REPO / '.env'} "
              "(copy .env.example) and restart. Everything else works without the AI.")
    else:
        print(f"AI: ready ({os.getenv('OPENROUTER_MODEL')} via OpenRouter)")
    print(f"Customer Guardian on http://{HOST}:{args.port}  (ledger: {store.db_file()})", flush=True)
    print(f"  customer app: http://{HOST}:{args.port}/customer/   Westpac dashboard: http://{HOST}:{args.port}/westpac/")
    if args.live:
        from api import live
        worker = live.start()
        print(f"Live: automatic sweeps every {worker.interval:g}s when something changed "
              f"(AI {'on' if live.ai_wanted() else 'off'})", flush=True)
    uvicorn.run(app, host=HOST, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
