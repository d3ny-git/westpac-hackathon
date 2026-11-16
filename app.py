"""Customer Guardian with the GEL React UI: one command, one port.

    python app.py                     # http://127.0.0.1:8600 (API at /api, UI at /)
    python app.py --port 8650         # another port
    python app.py --live              # + automatic sweeps and AI intake reviews (api/live.py)
    python app.py --live --host 0.0.0.0   # FILMING ONLY: phones on the same network can open it

The live apps (branch ui/live-apps) are on the same port: /customer/ (the customer app) and
/westpac/ (the Westpac dashboard). The walkthrough stays at /.

It builds nothing: build the UI once with `cd web && npm ci && npm run build` (needs Node 22+).
By default it binds to 127.0.0.1, so it's only reachable from this machine. --host opens it to a
network (0.0.0.0 = every network this machine is on, or one address such as a phone hotspot's), so a
real phone can open the customer app, e.g. for filming. There is NO real login (the sign-in pages are
demo pickers), so anyone on that network could open both apps and the API: use it only on your own
private hotspot, with the demo's fake data, and stop it when you're done.

Uses the same ledger as everything else: GUARDIAN_DB (from the environment or .env), or
data/guardian.db by default. GUARDIAN_RUNS_DIR optionally moves the policy-sweep run logs
(default data/runs/, the same folder the Streamlit pages read). Tests and demos that must not touch
the real demo ledger set GUARDIAN_DB to a temporary file.
"""
from __future__ import annotations

import argparse
import ipaddress
import os
import socket
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parent
HOST = "127.0.0.1"
DEFAULT_PORT = 8600


def is_local_only(host: str) -> bool:
    """True if binding to this host keeps the app on this machine (loopback)."""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def network_addresses() -> list[str]:
    """This machine's IPv4 addresses on its networks (what a phone would type), best guess first."""
    found: list[str] = []
    try:                                     # the address used for the default route; no packet is sent
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    return [a for a in dict.fromkeys(found) if not ipaddress.ip_address(a).is_loopback]


def main() -> None:
    load_dotenv(REPO / ".env")
    parser = argparse.ArgumentParser(description="Serve the Customer Guardian API and the GEL React UI.")
    parser.add_argument("--port", type=int, default=int(os.getenv("GUARDIAN_PORT", DEFAULT_PORT)),
                        help=f"port (default {DEFAULT_PORT})")
    parser.add_argument("--host", default=HOST,
                        help=f"address to listen on (default {HOST}: this machine only). FILMING ONLY: 0.0.0.0 or "
                             "a hotspot address lets phones on that network open it. There's no real login.")
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
    print(f"Customer Guardian on http://127.0.0.1:{args.port}  (ledger: {store.db_file()})", flush=True)
    print(f"  customer app: http://127.0.0.1:{args.port}/customer/   Westpac dashboard: http://127.0.0.1:{args.port}/westpac/")
    if not is_local_only(args.host):
        shown = network_addresses() if args.host in ("0.0.0.0", "") else [args.host]
        print("\n*** NETWORK ACCESS ON (--host " + args.host + ") ***")
        print("Anyone on this network can open both apps and the API: there is no real login.")
        print("Use your own private phone hotspot only, with the demo's fake data. Stop it (Ctrl+C) when done.")
        if shown:
            for address in shown:
                print(f"  on the phone: http://{address}:{args.port}/customer/")
        else:
            print("  (couldn't find this machine's network address: check it with `ip addr`)")
        print(f"If the phone can't connect, the firewall may be blocking port {args.port}.\n", flush=True)
    if args.live:
        from api import live
        worker = live.start()
        print(f"Live: automatic sweeps every {worker.interval:g}s when something changed "
              f"(AI {'on' if live.ai_wanted() else 'off'})", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
