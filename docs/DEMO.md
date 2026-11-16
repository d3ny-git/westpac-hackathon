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

Want to keep the demo data untouched? Start it with
`GUARDIAN_DB=/tmp/g.db GUARDIAN_CLEAN_DIR=/tmp/g-clean GUARDIAN_RUNS_DIR=/tmp/g-runs python app.py`.

## Start: the real pipeline (one click) or start empty (A and B live)

- **One click:** Home → Demo controls → **Reset demo (real pipeline)**. Raw data (fake PII) is sanitized,
  Node A and Node B score everyone, and a fresh ledger is written (19 entries), with a PII self-check.
  Home ticks steps 1 and 2.
- **Live, step by step:** Home → Demo controls → **Start empty (A and B not run yet)** (1 entry). Then:
  1. **Account (A)**: look at *Raw data → clean data* (which columns are dropped; Jane Citizen's raw
     row next to the clean row Node A sees), then **Run without the AI** (or with it). 9 entries.
  2. **Interactions (B)**: **Run for all customers without the AI**. 19 entries: the same ledger, hash
     for hash, as the one-click reset.

## The 10 steps

| # | SPEC step | Where | What you click | What you see |
|---|---|---|---|---|
| 1 | A → C: score 63 HIGH, SALARY_STOPPED | **Account (A)** → 3. Account scores, or **Ledger (C)** → Customer lookup | (after the reset) | hero `cust_af4200` **63 HIGH**, in the ledger |
| 2 | C → D: hero is a Quiet Help candidate | **Ledger (C)** → Quiet Help list | – | `cust_bb4b75` and `cust_af4200` are on the list |
| 3 | D → E: recommend QUIET_HELP_PUSH | **Policy (D)** → 6. Policy sweep | **Run sweep without the AI** (or with it) | Run log COMPLETED; 3. Recommendations shows hero's `QUIET_HELP_PUSH` awaiting approval |
| 4 | Human → E: approved | **Actions (E)** → Approval Queue | Acting staff `staff_19c` → **Approve** on hero's *Quiet Help Push* | "R-000x: APPROVED — saved in ledger" |
| 5 | E → Customer: push notification | **Actions (E)** → Approved — Awaiting Execution | **Execute** | Customer Experience tab: the lock screen says only "You have a new message from Westpac"; inside the app, the three options |
| 6 | Customer → B: hardship form | **Interactions (B)** → 2. Mock input form | **Fill in: hero's hardship form (SPEC step 6)** → **Submit to Node B** | *Kept* (tokens, `HARDSHIP_FORM`, `SUBMITTED`) vs *Thrown away* (name, email, phone, the text with her DOB); Node B's workflow COMPLETED |
| 7 | B → C: score 50 + HARDSHIP_RESPONSE due in 21 days | same page → 4. cust_af4200 now (or **Ledger (C)** → Customer lookup) | – | Combined **75 HIGH**, open hardship case **yes**, a `HARDSHIP_RESPONSE` promise due 01 Dec 17:00 |
| 8 | D → E: BOOK_MEETING → approved → call code | **Policy (D)** sweep again, then **Actions (E)** | **Run sweep without the AI** → **Approve** hero's *Book Meeting* → **Execute** | Customer Experience: "Your call with a hardship specialist", 18 Nov 14:00, the 6-character **call code** (only shown here) |
| 9 | Collections → D: SEND_DEFAULT_NOTICE → BLOCKED (P2) | **Policy (D)** → 1. Check an action | Customer `cust_af4200`, Action `SEND_DEFAULT_NOTICE` → **Check with D** | Red **BLOCK (P2)**: "Hardship request received 6 days ago, response due in 15 days" |
| 10 | Scam caller → D: wrong code → BLOCKED (P3) | **Actions (E)** → Caller verification | Type `K7P4QX` → **Verify Caller**; then type the real code from the phone | `K7P4QX`: **Possible scam (P3)**. The real code: **Genuine Westpac caller** |

Back on **Home**, all 10 steps are ticked and the guide says "All 10 steps done".

## Extras worth showing

- **Privacy on the form:** on Interactions (B), type a message with a name and a phone number (e.g.
  *"Michael Tran here, 0491 570 006: I lost my job and can't afford rent"*) for Michael Tran, channel
  CHAT, type GENERAL. *Kept* shows only tokens and the flags `CANT_AFFORD|JOB_LOSS`; the name and number
  are only in *Thrown away* (a local view) and never reach the clean data, the ledger, the run logs or
  the Ledger page.
- **Tamper-proof ledger:** Home → Demo controls → **Record checkpoint**, then **Simulate insider edit**.
  Ledger (C) shows **LEDGER TAMPERED** with that row highlighted; Home's pipeline says *tampered*; a
  policy sweep (and Node B's workflow) **stops** at the ledger check. Reset the demo to undo.
- **Explain:** Policy (D) → 5. Explain shows the rule and the facts at the time for any decision or
  recommendation; **Explain in plain English (AI)** needs the OpenRouter key in `.env` (without it, a
  message says the facts are the full explanation).
- **The AI follows the runbook:** run A's workflow or the sweep **with the AI**; the step log shows
  each tool call, and the ledger ends up identical to a run without it.
- **Mock fixtures:** Demo controls → *Or load mock fixtures* loads `mock_input_output` straight into the
  ledger without running A or B (`start`, or `full` = steps 1 to 8 done, R-0005 still awaiting approval,
  hero's call code `U5PXLW`).

The scripted version of this page is `web/e2e/story.spec.ts` (`npx playwright test`).
