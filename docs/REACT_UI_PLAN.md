# REACT UI PLAN: GEL React UI (branch `ui/gel-react`)

> A copy of the addendum "FLOW-4R: GEL React UI on a separate branch" from the approved project plan, followed by
> the branch status: the feature-parity checklist and any deviations. `docs/MCP_PLAN.md` is not changed on this branch.

# ADDENDUM (Nov 16): FLOW-4R: GEL React UI on a separate branch

> The plan above is the original MCP build plan. It is **kept as-is**: `docs/MCP_PLAN.md` and the Streamlit UI on `main` are **not changed** by this work. This addendum is a second, parallel version of the UI.

## Context
The Streamlit demo on `main` works end to end (C → D → E, all 10 SPEC steps). For the pitch, the UI should use **Westpac's real design system, GEL-next** (`@westpac/ui` v1.21, MIT; `@westpac/style-config` for WBC tokens). GEL is React + Tailwind v4, so it can't run inside Streamlit.

The decision is to build a **React UI with real GEL components on a separate branch**, alongside the untouched Streamlit version. It is **merged to `main` only when it is fully functional** (see the merge criteria below). If it fails, nothing on `main` is lost: the Streamlit demo stays the fallback.

User decisions:
- real GEL React components
- GEL's fallback fonts (the brand fonts are commercial and not covered by MIT)
- all pages in GEL, including E's (tell E)
- a home page with a 10-step guide that **ticks itself** as steps happen; staff still click Approve/Execute themselves

## Branch rules
- Branch: **`ui/gel-react`**, from `main`. All work is committed there, and pushes go only to that branch.
- **Only new files are added.** The branch does not modify `nodes/`, `shared/`, `agent.py`, `server.py`, `runbooks/`, `ui/pages/*.py` or `docs/MCP_PLAN.md`, so `main`'s Streamlit demo is unchanged even on the branch.
  - Helpers that currently live in `ui/pages/C.py` (`describe`, the checkpoint read/save, `simulate_insider_edit`) are **copied** into the API rather than moved.
- Its plan doc lives on the branch as `docs/REACT_UI_PLAN.md`, a copy of this addendum.
- Periodically merge `main` into the branch, so E's and others' work flows in.

## What gets built (all new files)
```
api/                      FastAPI over the EXISTING Python functions, with no logic changes
  main.py                 app + routers, serves the built UI (web/dist) at /
  ledger.py policy.py actions.py demo.py story.py   (routes + small presenters)
web/                      React + Vite + TypeScript + Tailwind v4 + @westpac/ui + @westpac/style-config
  index.html              <html data-brand="wbc">
  src/styles.css          @import 'tailwindcss'; @import '@westpac/style-config/tailwind';
                          @import '@westpac/style-config/themes/wbc'; @source "../node_modules/@westpac/ui/src";
  postcss.config.mjs      from @westpac/style-config/postcss (per GEL's installing-westpac-ui guide)
  src/api.ts              typed fetch client;  src/App.tsx  GEL Header + navigation + Footer
  src/pages/Home.tsx Ledger.tsx Policy.tsx Actions.tsx
  e2e/story.spec.ts       Playwright: the 10-step SPEC story in a real browser
app.py                    one command, one port: builds nothing, serves api + web/dist (127.0.0.1:8600)
tests/test_api.py         API tests (FastAPI TestClient)
docs/REACT_UI_PLAN.md  docs/DEMO.md
```
New dependencies:
- **Python:** `fastapi`, `uvicorn`, `httpx` (for tests)
- **Web:** `react`/`react-dom` 18+, `@westpac/ui`, `@westpac/style-config`, `tailwindcss` ~4.1, `@tailwindcss/postcss`, `@tanstack/react-query`, `vite`, `typescript`, `@playwright/test`

**Node 22+ is required.** This machine has Node 20, and GEL's repo uses v24, so install Node 22 LTS or 24 via nvm first.

## API: every endpoint wraps a function that already exists and is tested
| Area | Endpoint | Existing function |
|---|---|---|
| Ledger | `GET /api/ledger/integrity` | `chain.verify_chain` + checkpoint (`chain.checkpoint_holds`, same `<db>_checkpoint.json` file as C.py) |
| | `POST /api/ledger/checkpoint` | save checkpoint |
| | `GET /api/ledger/entries?customer=&type=` | `store.read` + `describe` (copied from C.py) |
| | `GET /api/ledger/dashboard` · `/quiet-help` · `/customers/{token}` | `risk_dashboard`, `quiet_help_candidates`, `combined_score` + `open_hardship_case` + history |
| Policy | `POST /api/policy/check` | `policy.check_action` |
| | `GET /api/policy/deadlines` · `/recommendations` · `/decisions` | `check_deadlines`, `tracked_recommendations`, BLOCKED/ACTION decision entries |
| | `GET /api/policy/explain/{entry_id}` · `POST …/words` | `explain`, `explain_in_words` (AI) |
| | `POST /api/policy/sweep?ai=true\|false` · `GET /api/policy/runs[/{id}]` | `agent.run(runbooks/policy_sweep.md)`, run logs in `data/runs/` |
| Actions | `GET /api/actions` · `POST /api/actions/{rec}/approve\|reject {staff}` | `actions_pending` / `actions_status`, `approve`, `reject` (**human UI actions; still never MCP tools**) |
| | `POST /api/actions/{rec}/execute` · `GET /api/actions/inbox/{token}` | `actions_execute_approved(rec)`, `actions_inbox` |
| | `POST /api/actions/verify-caller` | `check_action(VERIFY_CALLER)` |
| Demo | `POST /api/demo/load {stage}` · `/hero-form` · `/tamper` | `load_fixtures.load(reset=True)`, `submit_hero_form`, `simulate_insider_edit` (copied) |
| | `GET /api/demo/story` | **new** `api/story.py`: the 10 steps' progress worked out from the ledger |

**API rules:**
- Binds to 127.0.0.1 only. CORS is enabled only for the Vite dev server.
- Pydantic errors → 422. `LedgerError` / `PolicyError` / `ExecutionError` → 400 with their readable messages.
- Every JSON response is PII-checked (`find_pii`), as defence in depth.
- Call codes appear **only** in the inbox (the customer's phone view), the same as in Streamlit. The AI never sees one, because MCP tools are unchanged.

**Story progress (`api/story.py`, a pure function of the ledger, for hero `cust_af4200`):**
1. Hero has an ACCOUNT score.
2. Hero is or was on the Quiet Help list.
3. A QUIET_HELP_PUSH recommendation exists for hero.
4. A person approved it.
5. A QuietHelpPush ACTION exists for hero.
6. Hero has a HARDSHIP_RESPONSE promise.
7. Hero has an INTERACTION score and an open case (combined 75).
8. A BOOK_MEETING recommendation for hero is approved and carried out (`CONTACT_SCHEDULED` exists).
9. A BLOCKED P2 decision exists for hero.
10. A BLOCKED P3 decision exists for hero.

Each step also returns a "next: go to <page> and do <thing>" hint.

## UI: GEL components, every current feature kept
- **App shell:** GEL `Header` (WBC), navigation for **Home / Ledger (C) / Policy (D) / Actions (E)**, `Footer`, and fallback fonts only.
- **One tab, always fresh.** TanStack Query refetches on focus and every few seconds, and invalidates after every button. That removes the "refresh the other page" problem.
- **Demo controls in one place**, in a shared panel: load stage, hero form (stand-in for B5), simulate insider edit, record checkpoint.

| Page | Same features as today, built with GEL |
|---|---|
| **Home** (new, plan E4) | C → D → E pipeline with live counts per node; the 10-step story as a `ProgressIndicator` that ticks itself, with the next-step hint |
| **Ledger (C)** | Integrity `Alert` (verified / tampered + checkpoint), Risk Dashboard `Table` + urgency `Badge`s, Quiet Help `Table`, customer lookup (score, A, B, open case, history), full ledger `Table` with filters, the bad row highlighted, and the full JSON per entry |
| **Policy (D)** | Check-an-action form (`Select`, `Input`, `Button`) → ALLOW / BLOCK `Alert`; Deadlines; Recommendations with status `Badge`s; Decisions; Explain (rule, facts, AI words); Policy sweep (with / without AI) + run log replay |
| **Actions (E)** | `Tabs`: Approval Queue (staff `Select`, Approve / Reject, Execute), Customer Experience (phone mock-up in a `Panel`: lock-screen text, messages, `PassCodeView` call code), Caller verification (P3), Activity & Status `Table`s |

## Work breakdown (tickets on the branch)
| Ticket | What | Done when |
|---|---|---|
| **R-1** | Create branch, install Node 22+, scaffold `web/` per GEL's guide (WBC brand, fallback fonts), app shell + nav | `npm run build` + `tsc --noEmit` pass; GEL Header renders in WBC |
| **R-2** | `api/` + `app.py` (one port, serves `web/dist`) + `tests/test_api.py` | Every endpoint tested incl. errors, human-only approval, PII check, story progress |
| **R-3** | Ledger page | Feature parity with `ui/pages/C.py` |
| **R-4** | Policy page | Feature parity with `ui/pages/D.py` |
| **R-5** | Actions page | Feature parity with `ui/pages/E.py` |
| **R-6** | Home page: pipeline counts + self-ticking 10-step guide + demo controls | All 10 tick while playing the story |
| **R-7** | Playwright `e2e/story.spec.ts` (10 steps, `--no-ai` sweeps, uses the call code from the phone), `docs/DEMO.md`, branch README section | e2e passes from a fresh setup |

## Merge criteria ("totally functional"), all required before a PR to `main`
1. **Feature parity:** every feature of the C, D and E Streamlit pages works in the React UI (checklist above ticked).
2. **The full 10-step story plays in one browser tab** on `app.py`, and the home guide ticks all 10.
3. **All tests pass:** all existing Python tests + `tests/test_api.py` + Playwright e2e + `npm run build` + type-check.
4. **Setup from a fresh clone** works with the documented commands (Node 22+, `pip install`, `npm ci`, `npm run build`, `python app.py`).
5. **You've reviewed it in the browser.**
6. Only then: PR `ui/gel-react` → `main`. That PR decides how docs/README describe the two UIs. Until then, **`main` and `docs/MCP_PLAN.md` are untouched**.

## Verification
- `python -m pytest`: all existing tests plus the API tests.
- `cd web && npm run build && npx tsc --noEmit`.
- `python app.py` → http://127.0.0.1:8600. Play `docs/DEMO.md`'s 10 steps; Home ticks each one.
- `npx playwright test`: the scripted 10-step story in a real browser, on a temporary `GUARDIAN_DB`.
- Regression: the Streamlit pages on the branch still run and pass their tests, because they're unchanged.

---

# Status on the branch (kept up to date while building)

## Feature-parity checklist (merge criterion 1)

Every feature of the Streamlit pages (C, D, E, and since R-9/R-10 A and B), and where it lives in the React UI.

### `ui/pages/C.py` → Ledger (C)
- [x] Demo controls: load a story stage (start / full), wipes the ledger and the checkpoint (now "Load mock fixtures"; the default start is "Reset demo (real pipeline)")
- [x] Demo controls: record a checkpoint
- [x] Demo controls: simulate an insider edit (disabled on an empty ledger)
- [x] Empty ledger: a warning that says how to load demo data
- [x] 1. Integrity: chain verified (entries, newest entry, head hash) or LEDGER TAMPERED (problem, entry, detail)
- [x] 1. Integrity: checkpoint OK / checkpoint broken / no checkpoint yet
- [x] 2. Risk Dashboard: urgency, customer, score + band, promise, due, hours to due, made by, description
- [x] 3. Quiet Help list: customer, score, band, reasons, last Quiet Help
- [x] 4. Customer lookup: customer picker (hero by default), combined score, A, B, open hardship case, reasons, history
- [x] 5. Full ledger: entry, time, customer, type, what, prev hash, hash
- [x] 5. Full ledger: filter by entry types and by customers
- [x] 5. Full ledger: the first bad entry highlighted when tampered
- [x] 5. Full ledger: show one entry in full (JSON)

### `ui/pages/D.py` → Policy (D)
- [x] Demo controls: load a story stage
- [x] Demo controls: hero submits the hardship form → since main #23 (AB-5) this is on the B page's mock input form; the React UI does the same (Interactions (B) → 'Fill in: hero's hardship form' → Submit), and D's status line ("Hero's hardship form is in the ledger" / "submit it on the B page") is in the shared Demo controls
- [x] 1. Check an action: customer, action (collections, credit offers, VERIFY_CALLER), requested by, call code → ALLOW / BLOCK box with policy, flags and reason, and the entry it was recorded as
- [x] 1. Check an action: a readable warning when the check can't run (e.g. VERIFY_CALLER with no code)
- [x] 2. Deadlines (P1): level, customer, promise, due, hours to due, reason; "none" message
- [x] 3. Recommendations: rec, customer, recommendation, why, status, decided by, made
- [x] 4. Decisions: newest first, entry, time, customer, action, ALLOW / BLOCK (policy), reason
- [x] 5. Explain: pick a decision or recommendation (jumps to the one just checked), rule, combined score, open case, overdue promises, calls booked
- [x] 5. Explain: "Explain in plain English (AI)" with a readable message when the AI can't be reached
- [x] 5. Explain: all facts and evidence (call codes hidden)
- [x] 6. Policy sweep: run with the AI / without the AI
- [x] 6. Policy sweep: run log picker (newest / the run just made), status, each step's output, OFF SCRIPT and stopped events, summary, error

### `ui/pages/E.py` → Actions (E)
- [x] Metrics: pending, approved, completed, total
- [x] Approval Queue: acting staff member, each pending recommendation (action, rec, customer, reasons) with Approve / Reject
- [x] Approval Queue: errors and warnings from approve / reject shown
- [x] Approved, awaiting execution: Execute (re-checked by D), shows a block or an execution error
- [x] Customer Experience: customer picker, phone mock-up, lock-screen text only, messages (Quiet Help options, meeting time and call code)
- [x] Caller verification (P3): type the code the caller quoted → genuine / possible scam, recorded in the ledger; warning when empty; never shows the real code
- [x] Activity & Status: recommendation status table, ledger activity table (newest first), "append-only, no reset here" note

### `ui/pages/A.py` → Account (A) (R-9)
- [x] Demo controls: Reset demo (real pipeline), Start empty (A and B not run yet), with the "then run A, then B" note
- [x] No clean data yet: a warning that says how to reset
- [x] 1. Raw → clean: every raw column marked kept / becomes customer_token / dropped (personal information)
- [x] 1. One customer's first raw transaction (picker by name) next to its clean row (local view)
- [x] 1. Clean file summary (transactions, customers, date range) or an error if the columns are wrong
- [x] 2. Run Node A's workflow with / without the AI: status, error, each step's output, summary
- [x] 3. Account scores: customer, score, band, reasons, the five signals, in the ledger (yes / not yet)
- [x] 3. The rules (expandable)
- [x] 4. Node A's SCORE entries, newest first, or "hasn't written any scores yet"

### `ui/pages/B.py` → Interactions (B) (R-10)
- [x] Demo controls: Reset demo (real pipeline), Start empty
- [x] No clean data yet: a warning that says how to reset
- [x] 1. Run Node B for all customers with / without the AI: "ran for N customers" + customer, status, score, score written, promises written; a ResetError shown
- [x] 2. Mock input form: customer (fake names), handled by staff or self-service, date (demo date), channel, type, form status only for HARDSHIP_FORM, call back on / at only for CALLBACK_REQUEST (+2 days 14:00), free text, use-the-AI switch
- [x] 2. "Fill in: hero's hardship form (SPEC step 6)" and "Fill in: steady_bnpl's chat"
- [x] 3. After submit: Kept (clean row) vs Thrown away (local view), "the text became the flags … and was deleted"
- [x] 3. Node B's workflow run: status, each step's output, summary
- [x] 4. The customer now: combined score, interaction score (B), open hardship case, promises table (or "No promises")
- [x] 5. All clean interactions (tokens and flags only) and Node B's ledger entries (SCORE / PROMISE)

### New in the React UI
- [x] Home: A → B → C → D → E pipeline with live counts per node (clean data for A and B, the ledger for C–E)
- [x] Home: the 10-step story ticks itself, with a "next: go to … and do …" hint
- [x] Demo controls in one shared panel (real-pipeline reset, start empty, mock fixtures, checkpoint, insider edit)
- [x] One tab, always fresh (TanStack Query refetch on focus + every 3 s, invalidated after every button)

## Deviations from the plan (and why)
- **Story guide component.** GEL's `ProgressIndicator` is a loading spinner, not a list of steps. The
  10-step guide uses GEL's `ProgressRope` (vertical connected steps, ticking itself), with a
  `ProgressBar` for "N of 10" and a `Badge` on every done step (steps can happen out of order).
  `ProgressIndicator` is used where it fits: the spinner while a policy sweep runs.
- **Call code on the phone.** GEL's `PassCodeView` is a code *entry* screen (with "update" and
  "Resend code" links), so the booked call's code is shown with GEL's `PassCode` (six boxes, read-only)
  inside the phone `Panel`. Caller verification keeps E.py's free-text box (GEL `Field` + `Input`, up
  to 12 characters), so codes typed like `u5p-xlw` still work.
- **Call codes are hidden in the Ledger view.** C.py shows a CONTACT_SCHEDULED entry's code in the
  table and the JSON. Here the rule "call codes appear only in the customer's phone view" wins: the
  ledger API returns `(hidden)` (same as `nodes/policy.py` explanations and the MCP tools).
- **Caller verification is its own tab** (as the plan says); on E.py it sat next to the phone. The
  acting-staff picker offers all four demo staff tokens (D.py's list; E.py offered two), default
  `staff_19c` as on E.py.
- **PII check exemptions.** `find_pii` flags runs of digits inside sha256 hashes (as a mobile number)
  and inside agent.py's timestamped run ids (`20261116-204508-…` passes the card Luhn check). The API
  leaves out hash-shaped values and `run_id` values in agent.py's exact format before the scan;
  everything else in every response is checked. Tests cover both cases.
- **A few extra read-only endpoints** for the screens: `GET /api/demo/meta` (demo time, hero, stages,
  staff, checkable actions), `GET /api/demo/status`, `GET /api/demo/pipeline` (Home counts) and
  `GET /api/ledger/customers`. Shared bits live in `api/common.py`. The explain-in-words endpoint
  answers **503** with a readable message when the AI can't be reached (D.py showed a warning).
- **Demo controls** are one shared component: a panel on Home and a folded `Collapsible` at the top of
  Ledger / Policy (where the Streamlit sidebars were). "Check an action" sorts the action list
  (D.py's order came from a Python set, which changes between runs).
- **Routing** uses the URL hash (`#/ledger`), so `app.py` serves `web/dist` as plain files.
- **Phones:** the Actions tabs use short labels below 768 px (GEL `useBreakpoint`), so nothing
  scrolls sideways at 390 px.
- **Node 22** was installed from the official nodejs.org tarball (checksum verified) instead of nvm;
  any Node 22+ works.
- **Tests:** `tests/test_tamper_demo.py` imports `scripts/tamper_demo.py`, which isn't in git on
  `main` (it exists only in a local checkout), so it can't run on this branch; every other existing
  test passes unchanged. `tests/test_api.py` is kept local like the other test files.
- **Main merged in (Nov 16, #19–#24: A/B nodes, real pipeline, start-empty demo).** The branch follows
  main's changes: the run-log list shows policy sweeps only (as D.py now does), the e2e also isolates
  `GUARDIAN_CLEAN_DIR`, and `app.py` relies on agent.py's new `GUARDIAN_RUNS_DIR`. The A and B pages
  and the real-pipeline demo followed as R-8..R-11 (below).

# R-8..R-11: Account (A), Interactions (B) and the start-empty demo (added after the first review)

The user asked for main's A and B Streamlit pages (AB-5, #23) and the start-empty demo (#24) in GEL too,
still on this branch only. Same rules: only new files under `api/`, `web/`, `app.py`,
`requirements-web.txt` and these docs; every endpoint wraps an existing, tested function.

| Ticket | What | Done when |
|---|---|---|
| **R-8** | API: `api/account.py`, `api/interaction.py`, `POST /api/demo/reset` (`reset_demo.reset`, real pipeline or `empty=true`), the PII-check allow-list for the raw views | A/B endpoints tested incl. errors, the allow-list pinned, typed PII never stored or returned outside the raw views |
| **R-9** | Account (A) page in GEL | Parity with `ui/pages/A.py` (checklist above) |
| **R-10** | Interactions (B) page in GEL with the mock input form | Parity with `ui/pages/B.py` (checklist above) |
| **R-11** | Demo controls (real-pipeline reset first, start empty, hero-form button retired), Home A → B → C → D → E, story hints, e2e, docs | Story e2e does step 6 on the B page; start-empty and B-privacy specs pass |

| Area | Endpoint | Existing function |
|---|---|---|
| A | `GET /api/account/overview` | raw column names vs `CLEAN_TRANSACTION_COLUMNS`, `account.check_data()` |
| | `GET /api/account/raw-sample?customer_id=` **(raw view)** | the raw row + `sanitize.sanitize_transactions([row])[0]` |
| | `GET /api/account/scores` · `/rules` · `/entries` | `score_all_customers`, `account_signals`, `account.RULES`, A's SCORE entries |
| | `POST /api/account/run?ai=` | `agent.run(runbooks/a_account.md, ai, server=…)` |
| B | `GET /api/interaction/form-options` **(raw view)** | B.py's `fake_customers` / `fake_staff` (copied), the 2 examples in `form_submissions.json` |
| | `POST /api/interaction/submit` (**`thrown_away` field** is the raw view) | `sanitize.add_interaction(raw)` → `agent.run(runbooks/b_interaction.md, {"token"}, ai)` → `combined_score`, `has_open_hardship_case`, `interaction.customer_promises` |
| | `POST /api/interaction/run-all?ai=` | `reset_demo.run_node_b_for_everyone(server, ai)` (`ResetError` → 400) |
| | `GET /api/interaction/overview` | the clean interactions, B's SCORE(INTERACTION) + PROMISE entries |
| Demo | `POST /api/demo/reset {empty}` | `reset_demo.reset(quiet=True[, empty=True])` (`ResetError` → 400) |

**PII rule for the raw views.** The raw panels and the form are LOCAL views for the demo (MCP_PLAN §6:
they never go through MCP or the AI), so they legitimately show the fake PII. `api/main.py` has ONE
explicit allow-list, `RAW_VIEWS`: A's raw sample, B's form options (pickers + examples), and only the
`thrown_away` field of B's submit response. Every other response, every other field of the submit
response and every error response is still checked with `find_pii`. The raw submission is never stored
or logged: `add_interaction` writes only the clean row, the runbook only gets the customer's token,
uvicorn's access log is off, and error messages never echo the input. `tests/test_api.py` pins the
allow-list, makes the PII check flag everything to prove every other GET (and the rest of submit) is
blocked, and checks that a name + phone typed into the form appear in no clean file, ledger entry,
run log or non-raw response; the Playwright B-privacy spec checks the Ledger page too.

### Deviations (R-8..R-11)
- **The hero-form button is retired** from Demo controls (as main did on D.py): step 6 is the B page's
  form, and the story hint says so. `POST /api/demo/hero-form` stays in the API as the scripted shortcut
  (main kept `load_fixtures --step hero-form` too); no button uses it.
- **"Load demo data" is now "Load mock fixtures"**, below the real-pipeline reset and start-empty
  buttons. The insider-edit and ledger-filter e2e specs still use the fixtures, because they check fixed
  entry IDs (E-0004, 40 entries).
- **Endpoints are grouped** per page section: A's people picker comes with the raw sample (one raw view,
  not two), and B's pickers come with the examples and the form's choices and defaults.
- **Form fields:** dates and times use GEL `Input` with `type="date"` / `type="time"` rather than GEL's
  `DatePicker` (a calendar widget for picking dates relative to today; the demo pins dates to
  16 Nov 2026). The use-the-AI option is a GEL `Switch`.
- **Home pipeline** is one row A → B → C → D → E (the tiles for A and B show the clean data and their
  scores); the SPEC's diagram has A and B both feeding C, which the caption says.
- **Commits:** R-9 and R-10 are one commit (App.tsx's navigation imports both pages, so neither half
  builds alone).

## Test status (latest run on the branch)
- `python -m pytest`: 499 passed (422 existing tests + 77 in `tests/test_api.py`, 22 of them for A, B
  and the real-pipeline demo)
- `cd web && npm run build` and `npx tsc --noEmit`: pass
- `npx playwright test`: 5 passed: the 10-step story from a real-pipeline reset, with step 6 on the B
  page's form, no-AI sweeps and the call code read from the phone; start empty → run A (9 entries) →
  run B for all (19) with the same head hash as a one-click reset; B privacy (a typed name and phone are
  thrown away and never reach the Ledger page); insider edit caught + sweep stops; ledger filters
