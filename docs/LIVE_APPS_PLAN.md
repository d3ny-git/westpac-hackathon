# Live apps: Customer app + Westpac dashboard (branch `ui/live-apps`)

## Context
The current UIs (Streamlit on `main`, GEL React walkthrough on `ui/gel-react`) exist to **explain**
how Customer Guardian works: node pages A–E, raw→clean panels, a 10-step guide and demo controls.
To show it "in the wild" we need two **operational** front ends that look like real products:

- **Customer app:** what a Westpac customer sees. Their accounts and transactions, messages,
  the hardship form, a callback request, "is this call really Westpac?", and the bank's
  promises to them.
- **Westpac dashboard:** what staff need to operate it. Alerts, risk, Quiet Help, the approval
  queue, policy checks, customer lookup, the audit trail and the automatic sweeps. Nothing that
  only exists to explain the system.

**Nothing is replaced.** The walkthrough UIs stay exactly as they are for the group
presentation. User decisions:
- a **new branch `ui/live-apps` off `ui/gel-react`**, never merged to `main`
- reset the data from the existing walkthrough UI (same ledger), so the new apps have no demo buttons
- on a customer submission, **the AI reads the sanitized input and assesses it for financial hardship**
- **sweeps run automatically**, with no buttons

## Branch rules (same spirit as before)
- Work only on `ui/live-apps` (from `origin/ui/gel-react`). Push only there: no PR, nothing to `main`.
- Files on `main` are untouched. Files from `ui/gel-react` get **additive edits only**:
  - register the new routers and entry pages in `api/main.py`, `app.py` and `vite.config.ts`
  - add the customer views to the `RAW_VIEWS` allow-list
- The walkthrough at `/` keeps working, and all its tests pass unchanged.
- Tests stay local and uncommitted, as before. Built by a background agent so you can keep working.

## How it runs
`python app.py --live` → http://127.0.0.1:8600:
- `/` the walkthrough (unchanged)
- `/customer` the customer app
- `/westpac` the Westpac dashboard

They share the same API, ledger and `.env`. `--live` switches on the automatic sweeps.
Plain `python app.py` stays manual, so the step-by-step walkthrough isn't done for you.

## 1. Customer app (`/customer`, GEL, phone-first layout)
| Screen | What | Built from (existing, unchanged) |
|---|---|---|
| Sign in | Demo sign-in: pick one of the fake customers (no passwords; says "demo") | raw customer list (`api/interaction.fake_customers`) |
| Home | Greeting, accounts with balances, recent transactions | `data/raw/transactions_raw.csv` rows for **that customer only** (their own data) |
| Messages | Lock-screen notice + in-app messages. Quiet Help buttons work: "Apply for hardship help" → the form; "Talk to someone" → callback request. A booked call shows **your call code**. | `actions_inbox(token)` |
| Get help | Hardship form (self-service, `FORM`/`HARDSHIP_FORM`) and Request a callback (`CALLBACK_REQUEST`, date/time). Name and contact details come from the sign-in. | `sanitize.add_interaction` → intake (§3) |
| Our promises to you | Open promises in plain words, e.g. "We'll respond to your hardship request by 1 Dec, 5pm", "We'll call you 18 Nov, 2pm" | ledger PROMISE entries for the token |
| Is this call really Westpac? | Enter the code the caller says → "✅ matches your call code" or "❌ Hang up: this isn't Westpac" | `check_action(VERIFY_CALLER)` (P3), `requested_by: SYSTEM` |

- The customer never sees scores, bands, flags, tokens or policy names.
- The token is worked out on the server from the signed-in customer ID (`tokenise`).
- **Privacy:**
  - The customer's own name and transactions are personal data, shown only to that customer.
    They're added to `RAW_VIEWS` as customer-only views, with tests.
  - What the customer types is sanitized before it is stored. The AI only ever sees the clean row.

## 2. Westpac dashboard (`/westpac`, GEL, desktop-first; tokens only, every response PII-checked)
Staff demo sign-in (staff picker), used for approvals and policy checks.

| Tab | What | Built from |
|---|---|---|
| **Overview** | Ledger integrity badge, automatic sweep status (last run, AI summary, next run), P1 deadline alerts (ALERT/ESCALATE), Risk Dashboard, Quiet Help list | `verify_chain`, scheduler status, `check_deadlines`, `risk_dashboard`, `quiet_help_candidates` |
| **New contacts** | Each customer submission: token, type, flags, score, the promises created, and the **AI hardship assessment** | intake runs (§3) |
| **Approvals** | Recommendations awaiting approval: facts plus "Explain in plain English" (AI), then Approve / Reject. Approved items are carried out automatically by the next sweep, and their status updates live. | `tracked_recommendations`, `explain`, `explain_in_words`, `approve`, `reject` |
| **Check an action** | Before a default notice, credit offer or outbound call: ALLOW / BLOCK with the policy and reason | `check_action` (P2/P3/P4) |
| **Customers** | Look up a token: combined score, A/B scores, open case, promises, history | `combined_score`, `open_hardship_case`, `store.read` |
| **Audit** | Decisions (allowed/blocked), actions carried out, and the full ledger (read-only, chain verified) | existing ledger and decision endpoints |

**Removed (walkthrough only):** raw→clean panels, node-by-node pages, the run-workflow and sweep
buttons, rules tables, the 10-step guide, demo controls, the tamper/insider-edit simulation,
mock fixtures and checkpoints.

## 3. Automatic sweeps + AI intake (new `api/live.py`, started by `app.py --live`)
A background worker in the app process (one at a time, using the existing `RUN_LOCK`):

1. **Intake, on each customer submission (immediate):**
   - The submission is sanitized and stored, and the customer gets "Received" straight away.
   - The worker then runs the **new runbook `runbooks/b_intake_review.md` with the AI**. It has the
     same tools and steps as `b_interaction.md` (score → promises → publish → verify). Its
     instructions ask the AI to read the sanitized interaction's results and write a
     **hardship assessment** for staff:
     - the signs of financial hardship it found
     - how urgent it is
     - the promises now owed
     - a suggested next step
   - The **score and promises still come from the fixed rules**. The AI assesses and explains;
     it doesn't decide, as in the original plan.
   - If the AI fails (no key, timeout), it falls back to the same runbook without the AI. The
     ledger is identical and the assessment says "AI unavailable".
2. **Cycle, every 30 s, but only when something changed** (ledger head or clean data moved since the last cycle):
   1. **Scoring run (A + B):** `reset_demo.run_node_a` + `run_node_b_for_everyone`, without the AI.
      These are deterministic and skip unchanged scores, so they're cheap.
   2. **Policy sweep (D):** `runbooks/policy_sweep.md` **with the AI**, falling back to no AI.
      Its summary appears on the Overview tab.
   3. **Execute approved (E):** `actions_execute_approved()` carries out every APPROVED item.
      Node D re-checks each one first. **People still approve; the sweep only carries out what a
      person approved.**
3. **Triggers:** a customer submission or a staff approval/rejection triggers a cycle straight
   away, so the demo feels live.
4. **Idle means no AI calls:** if nothing changed, nothing runs, so there's no token spend while idle.
5. **Status** (last run, step results, AI summary, errors) is shown on the Westpac Overview tab.
   Run logs go to `data/runs/` as now.

## Files (new unless marked)
- `api/customer.py`: sign-in options, overview (accounts and transactions), inbox, promises, submit, verify caller
- `api/westpac.py`: thin presenters for the dashboard tabs (most data reuses existing `api/*` endpoints)
- `api/live.py`: the scheduler and intake worker, plus status and intake-feed endpoints
- `runbooks/b_intake_review.md`: the AI hardship-assessment runbook
- `web/customer.html` + `web/src/customer/*`, `web/westpac.html` + `web/src/westpac/*`
  - These reuse `web/src/api.ts` and `components.tsx`, with GEL Header/Footer and Westpac branding.
- Additive edits:
  - `api/main.py`: routers, plus `RAW_VIEWS` for the customer views
  - `app.py`: the `--live` flag and the `/customer` and `/westpac` routes
  - `web/vite.config.ts`: multi-page inputs
- Docs: `docs/LIVE_APPS_PLAN.md` (this plan) and `docs/LIVE_DEMO.md` (the customer ↔ Westpac
  demo script for two browser windows side by side)

## Tickets (agent, on `ui/live-apps`)
| Ticket | What |
|---|---|
| L-1 | Branch, multi-page Vite, the `/customer` and `/westpac` shells with GEL branding and demo sign-in |
| L-2 | `api/customer.py` and the customer screens |
| L-3 | `api/live.py` scheduler, intake with the AI assessment, and the `b_intake_review.md` runbook |
| L-4 | Westpac dashboard tabs |
| L-5 | Tests, Playwright two-window story, docs, push |

## Verification
- **pytest:**
  - all existing tests still pass
  - new tests for the customer API: own data only, no scores or tokens leak to the customer, PII rules
  - the scheduler: idle → no runs; change → one cycle; approval → executed; AI failure → falls
    back with an identical ledger
  - every Westpac response is PII-free
- **Playwright, the two-window story** (sweeps on, AI forced off for repeatability):
  1. Jane signs in and sees her accounts.
  2. The sweep puts hero on Quiet Help, and it appears in Westpac Approvals.
  3. Staff approve. It's carried out automatically, and Jane's Messages shows "Westpac can help".
  4. Jane taps "Apply for hardship help" and submits the form. Westpac's New contacts shows it
     with an assessment.
  5. The sweep recommends BOOK_MEETING. Staff approve, and Jane sees her call code.
  6. On Westpac's Check an action, a default notice is BLOCKED (P2).
  7. Jane checks a wrong code ("Hang up") and then the right code ("matches").
  - Plus: no PII on any Westpac view.
- **Manual with the AI on:** `python app.py --live`, with `/customer` and `/westpac` side by side.
  Submit the form and watch the AI assessment and the sweep summary appear without clicking anything.
- The walkthrough at `/` and the Streamlit pages are unchanged and their tests pass.
- `npm run build`, `tsc`, the fresh-setup check, and the diff check that nothing on `main` changed.
