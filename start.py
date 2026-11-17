#!/usr/bin/env python3
"""Customer Guardian: one command to set up and run the demo.

    python start.py               # first time: sets everything up (2-3 minutes), then starts the app
    python start.py --reset       # start again from fresh demo data
    python start.py --no-ai       # run without the AI, even if .env has a key
    python start.py --port 8601   # another port (default 8600)
    python start.py --no-browser  # don't open the browser

What it does, each step only when needed:
  1. checks Python is 3.11 or newer
  2. creates a virtual environment in .venv/ and installs requirements*.txt into it
  3. creates .env from .env.example (the AI is optional: add an OpenRouter key there to switch it on)
  4. builds the demo data: fake raw bank data -> sanitizer -> Nodes A and B -> the ledger
  5. starts the app with the automatic sweeps on, and opens http://127.0.0.1:8600/

Only uses the Python standard library itself; everything else goes into .venv/. Stop with Ctrl+C.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import venv
import webbrowser
from pathlib import Path

REPO = Path(__file__).resolve().parent
VENV = REPO / ".venv"
REQUIREMENTS = [REPO / "requirements.txt", REPO / "requirements-web.txt"]
STAMP = VENV / ".customer-guardian-installed"


def say(msg: str) -> None:
    print(f"\033[1m▸ {msg}\033[0m" if sys.stdout.isatty() else f"> {msg}", flush=True)


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def requirements_hash() -> str:
    return hashlib.sha256(b"".join(p.read_bytes() for p in REQUIREMENTS)).hexdigest()


def ensure_venv() -> Path:
    py = venv_python()
    if not py.exists():
        say("Creating a virtual environment in .venv/ ...")
        venv.EnvBuilder(with_pip=True).create(VENV)
    if not STAMP.exists() or STAMP.read_text().strip() != requirements_hash():
        say("Installing the Python packages (first run takes a couple of minutes) ...")
        subprocess.run([str(py), "-m", "pip", "install", "--quiet", "--upgrade", "pip"], check=True)
        args = [str(py), "-m", "pip", "install", "--quiet"]
        for r in REQUIREMENTS:
            args += ["-r", str(r)]
        subprocess.run(args, check=True)
        STAMP.write_text(requirements_hash())
    return py


def ensure_env() -> None:
    env, example = REPO / ".env", REPO / ".env.example"
    if not env.exists() and example.exists():
        shutil.copy(example, env)
        say("Created .env from .env.example (the AI is off until you add an OpenRouter key there).")


def ensure_data(py: Path, reset: bool, env: dict) -> None:
    ledger = Path(env.get("GUARDIAN_DB") or REPO / "data" / "guardian.db")
    if reset or not ledger.exists():
        say("Building the demo data: raw bank data -> sanitizer -> Nodes A and B -> ledger ...")
        subprocess.run([str(py), str(REPO / "scripts" / "reset_demo.py")], check=True, cwd=REPO, env=env,
                       stdout=subprocess.DEVNULL)


def wait_for(url: str, proc: subprocess.Popen, seconds: float = 60) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Set up and run the Customer Guardian demo.")
    ap.add_argument("--reset", action="store_true", help="start from fresh demo data")
    ap.add_argument("--no-ai", action="store_true", help="run without the AI")
    ap.add_argument("--port", type=int, default=8600, help="port on 127.0.0.1 (default 8600)")
    ap.add_argument("--no-browser", action="store_true", help="don't open the browser")
    a = ap.parse_args()

    if sys.version_info < (3, 11):
        print(f"Customer Guardian needs Python 3.11 or newer (this is {sys.version.split()[0]}). "
              "Install it from https://www.python.org/downloads/ and run this again.")
        return 1
    if not (REPO / "web" / "dist" / "index.html").exists():
        print("The built web UI (web/dist) is missing. Build it with Node 22+: cd web && npm ci && npm run build")
        return 1

    py = ensure_venv()
    ensure_env()
    env = dict(os.environ)
    if a.no_ai:
        env["GUARDIAN_LIVE_AI"] = "0"
    ensure_data(py, a.reset, env)

    base = f"http://127.0.0.1:{a.port}"
    say("Starting Customer Guardian ...")
    proc = subprocess.Popen([str(py), str(REPO / "app.py"), "--live", "--port", str(a.port)], cwd=REPO, env=env)
    try:
        if not wait_for(f"{base}/api/demo/meta", proc):
            print(f"The app didn't start. Is port {a.port} already in use? Try: python start.py --port {a.port + 1}")
            proc.terminate()
            return 1
        print(f"""
  Customer Guardian is running. Open these side by side:

    Customer app (Jane's phone)   {base}/customer/     sign in as Jane Citizen
    Westpac dashboard (staff)     {base}/westpac/      sign in as staff_19c
    How it works (walkthrough)    {base}/              also has "Reset demo"

  The demo script is in docs/LIVE_DEMO.md. Stop with Ctrl+C.
""", flush=True)
        if not a.no_browser:
            webbrowser.open(f"{base}/")
        return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("\nStopped.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
