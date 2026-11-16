# Demo: the 10-step story in the GEL React UI

The SPEC's "one customer, start to finish" story for hero (`cust_af4200`), clicked through in **one
browser tab**. The Home page's guide ticks each step by itself as it shows up in the ledger, and its
"Next" box says where to go. You still click Approve and Execute yourself: the AI never decides.

Setup and start (see `web/README.md`):

```bash
pip install -r requirements.txt -r requirements-web.txt
cd web && npm ci && npm run build && cd ..
python app.py                     # http://127.0.0.1:8600
```

Want to keep the demo ledger untouched? Start it with `GUARDIAN_DB=/tmp/guardian-demo.db python app.py`.

| # | SPEC step | Where | What you click | What you see |
|---|---|---|---|---|
| 0 | Reset | **Home** → Demo controls | Story stage `start` → **Load demo data** | Home ticks steps 1 and 2 straight away |
| 1 | A → C: score 63 HIGH, SALARY_STOPPED | **Ledger (C)** → Customer lookup | (hero is picked by default) | Combined score **63 HIGH**, no open case |
| 2 | C → D: hero is a Quiet Help candidate | **Ledger (C)** → Quiet Help list | – | `cust_bb4b75` and `cust_af4200` are on the list |
| 3 | D → E: recommend QUIET_HELP_PUSH | **Policy (D)** → 6. Policy sweep | **Run sweep without the AI** (or with it) | Run log COMPLETED; 3. Recommendations shows hero's `QUIET_HELP_PUSH` (R-0004) awaiting approval |
| 4 | Human → E: approved | **Actions (E)** → Approval Queue | Acting staff `staff_19c` → **Approve** on hero's *Quiet Help Push* | "R-0004: APPROVED — saved in ledger" |
| 5 | E → Customer: push notification | **Actions (E)** → Approved — Awaiting Execution | **Execute** | Customer Experience tab: lock screen says only "You have a new message from Westpac"; inside the app, the three options |
| 6 | Customer → B: hardship form | **Home** → Demo controls | **Simulate: hero submits hardship form** (stand-in for Node B's form B5) | Steps 6 and 7 tick |
| 7 | B → C: score 50 + HARDSHIP_RESPONSE due in 21 days | **Ledger (C)** → Customer lookup | – | Combined **75 HIGH**, open hardship case **due 01 Dec** |
| 8 | D → E: BOOK_MEETING → approved → call code | **Policy (D)** sweep again, then **Actions (E)** | **Run sweep without the AI** → **Approve** hero's *Book Meeting* (R-0005) → **Execute** | Customer Experience: "Your call with a hardship specialist", 18 Nov 14:00, the 6-character **call code** (only shown here) |
| 9 | Collections → D: SEND_DEFAULT_NOTICE → BLOCKED (P2) | **Policy (D)** → 1. Check an action | Customer `cust_af4200`, Action `SEND_DEFAULT_NOTICE` → **Check with D** | Red **BLOCK (P2)**: "Hardship request received 6 days ago, response due in 15 days" |
| 10 | Scam caller → D: wrong code → BLOCKED (P3) | **Actions (E)** → Caller verification | Type `K7P4QX` → **Verify Caller**; then type the real code from the phone | `K7P4QX`: **Possible scam (P3)**. The real code: **Genuine Westpac caller** |

Back on **Home**, all 10 steps are ticked and the guide says "All 10 steps done".

## Extras worth showing

- **Tamper-proof ledger:** Home → Demo controls → **Record checkpoint**, then **Simulate insider edit**.
  Ledger (C) shows **LEDGER TAMPERED** at E-0004 with that row highlighted; Home's pipeline says
  *tampered*; a policy sweep **stops** at step 1. Load demo data to undo.
- **Explain:** Policy (D) → 5. Explain shows the rule and the facts at the time for any decision or
  recommendation; **Explain in plain English (AI)** needs the OpenRouter key in `.env` (without it, a
  message says the facts are the full explanation).
- **The AI follows the runbook:** run the sweep **with the AI**; the run log replays each step, and
  the ledger ends up identical to a run without it.
- **Stage `full`** loads the end state of E's mock data (steps 1 to 8 done, R-0005 still awaiting
  approval, hero's call code `U5PXLW`).

The scripted version of this table is `web/e2e/story.spec.ts` (`npx playwright test`).
