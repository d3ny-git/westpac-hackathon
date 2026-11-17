# Live demo: the customer app and the Westpac dashboard, side by side

Two windows, one app. On the left, **Jane** (hero, `cust_af4200` to the bank) in the Westpac app on her
phone. On the right, the **hardship team** in the Customer Guardian dashboard. The sweeps run by
themselves: nobody clicks "run". People only approve.

## Start

```bash
pip install -r requirements.txt -r requirements-web.txt
cd web && npm ci && npm run build && cd ..
python app.py --live              # http://127.0.0.1:8600
```

- `.env` holds the OpenRouter key and model (see `docs/DEMO.md`). With them, the startup lines say
  `AI: ready (...)` and `Live: ... (AI on)`. Without them, everything still works and the AI parts say
  "AI unavailable".
- `GUARDIAN_LIVE_AI=0 python app.py --live` runs the same thing with the AI switched off (repeatable).
- To keep your demo data untouched:
  `GUARDIAN_DB=/tmp/g.db GUARDIAN_CLEAN_DIR=/tmp/g-clean GUARDIAN_RUNS_DIR=/tmp/g-runs python app.py --live`

Open three tabs:

| Tab | URL | Size |
|---|---|---|
| Walkthrough (only for the reset) | http://127.0.0.1:8600/ | any |
| **Jane's phone** | http://127.0.0.1:8600/customer/ | narrow, e.g. DevTools device toolbar or a ~400 px window |
| **Westpac dashboard** | http://127.0.0.1:8600/westpac/ | wide |

**Reset** in the walkthrough: Home → Demo controls → **Reset demo (real pipeline)**. The live apps have
no demo buttons. Sign in on the phone as **Jane Citizen** and on the dashboard as **staff_19c**.

### On a real phone (filming only)
By default the app only answers this laptop. To open the customer app on a real phone:

1. Turn on **your own phone's hotspot** and connect the laptop to it (not venue or office Wi-Fi).
2. Start with `python app.py --live --host 0.0.0.0`. It prints a warning and the address for the
   phone, e.g. `http://192.168.43.20:8600/customer/`. Open that on the phone.
3. There's **no real login**: anyone on that network could open both apps and the API. All the data
   is fake, but stop the app (Ctrl+C) and switch the hotspot off when you're done.
4. If the phone can't connect, the laptop's firewall may be blocking the port: allow it while
   filming (e.g. `sudo ufw allow 8600/tcp`, then `sudo ufw delete allow 8600/tcp` afterwards).

**Android over USB, with no network at all:** keep the default (no `--host`), connect the phone by
USB with USB debugging on, run `adb reverse tcp:8600 tcp:8600`, and open
`http://localhost:8600/customer/` on the phone.

## What happens by itself

The dashboard's live bar shows "Automatic sweeps on". Every 30 seconds the worker checks whether
anything changed (the ledger or the clean data); a customer submission or an approval wakes it at once:

1. **Scoring:** Node A and Node B rescore from the clean data (no AI; unchanged scores aren't rewritten).
2. **Policy sweep:** `runbooks/policy_sweep.md` **with the AI**, which writes the summary on the Overview
   tab (it falls back to no AI on any AI failure).
3. **Carry out:** everything a person approved is carried out (Node D re-checks it first).

If nothing changed, nothing runs: no AI calls while idle.

## The script (about 5 minutes)

| # | Jane's phone | Westpac dashboard |
|---|---|---|
| 1 | **Home:** "Good morning, Jane", her Everyday account and home loan, recent transactions (Afterpay, Zip, Klarna, rent...). No scores, no tokens: just her banking. | **Overview:** ledger verified; the first automatic sweep's AI summary; P1 alert (a callback 2 days overdue); Risk Dashboard; **Quiet Help list: `cust_af4200` 63 HIGH**. |
| 2 | – | **Approvals (4):** the sweep recommended a **Quiet Help Push** for `cust_af4200`. Show the facts, click **Explain in plain English (AI)**, then **Approve**. |
| 3 | Within a few seconds, **Messages**: the lock screen says only "You have a new message from Westpac"; inside: "We're here if you need a hand", with what Westpac can do. | The live bar shows the sweep carrying it out; **Approvals → Decided:** DONE. |
| 4 | Tap **Apply for hardship help**, write what's happening (try including her name and phone number), **Submit my request**. "We'll respond by Mon 7 Dec, 5:00 pm". | **New contacts:** `cust_af4200`, Hardship Form, flags `JOB_LOSS` / `CANT_AFFORD`, interaction score 75, and the **AI hardship assessment** (signs, urgency, promises owed, suggested next step). No name, no phone: sanitized on arrival. |
| 5 | **Our promises:** "We'll respond to your hardship request by Mon 7 Dec, 5:00 pm", "We'll call you back on Wed 18 Nov, 2:00 pm". | The next sweep (woken by the form) recommends **Book Meeting** for `cust_af4200`. **Approve.** |
| 6 | **Messages:** "Your call with a hardship specialist", 18 Nov, 2:00 pm, and **her call code** in six boxes. | **Check an action:** customer `cust_af4200`, `SEND_DEFAULT_NOTICE` → **BLOCK (P2)**: hardship request received today. |
| 7 | **Is this Westpac?:** type a wrong code (e.g. `K7P4QX`) → "Hang up: this isn't Westpac". Then the code from Messages → "This matches your call code". | **Audit:** the P2 and P3 decisions, the actions carried out (call code hidden), the full ledger, chain verified. |

## What to point out

- The customer never sees scores, bands, flags, tokens or policy names; staff never see a name, a phone
  number or the call code. The customer's own name and transactions are shown only to her (two
  customer-only views on the PII allow-list; every other response is PII-checked).
- What Jane types is sanitized before it's stored: only tokens and keyword flags reach Node B, the
  ledger and the AI.
- The AI **assesses and explains** (the intake assessment, the sweep summary, "Explain in plain
  English"). The scores, the promises and every ALLOW / BLOCK come from fixed rules, and only a person
  approves.
- Idle means nothing runs: watch the "next check" counter tick over without a new sweep.

## Tests

```bash
python -m pytest                                  # incl. tests/test_live.py (local, not in git)
cd web
npm run build && npx tsc --noEmit
PYTHON=python npx playwright test                 # the walkthrough's 5 specs
PYTHON=python npx playwright test -c e2e/live.config.ts   # this two-window story (sweeps on, AI off, port 8661)
```
