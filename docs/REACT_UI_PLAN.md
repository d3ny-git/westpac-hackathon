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

Every feature of the three Streamlit pages, and where it lives in the React UI.

### `ui/pages/C.py` → Ledger (C)
- [x] Demo controls: load a story stage (start / full), wipes the ledger and the checkpoint
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
- [ ] Demo controls: load a story stage
- [ ] Demo controls: hero submits the hardship form (stand-in for B5), disabled once it's in the ledger, with its status line
- [ ] 1. Check an action: customer, action (collections, credit offers, VERIFY_CALLER), requested by, call code → ALLOW / BLOCK box with policy, flags and reason, and the entry it was recorded as
- [ ] 1. Check an action: a readable warning when the check can't run (e.g. VERIFY_CALLER with no code)
- [ ] 2. Deadlines (P1): level, customer, promise, due, hours to due, reason; "none" message
- [ ] 3. Recommendations: rec, customer, recommendation, why, status, decided by, made
- [ ] 4. Decisions: newest first, entry, time, customer, action, ALLOW / BLOCK (policy), reason
- [ ] 5. Explain: pick a decision or recommendation (jumps to the one just checked), rule, combined score, open case, overdue promises, calls booked
- [ ] 5. Explain: "Explain in plain English (AI)" with a readable message when the AI can't be reached
- [ ] 5. Explain: all facts and evidence (call codes hidden)
- [ ] 6. Policy sweep: run with the AI / without the AI
- [ ] 6. Policy sweep: run log picker (newest / the run just made), status, each step's output, OFF SCRIPT and stopped events, summary, error

### `ui/pages/E.py` → Actions (E)
- [ ] Metrics: pending, approved, completed, total
- [ ] Approval Queue: acting staff member, each pending recommendation (action, rec, customer, reasons) with Approve / Reject
- [ ] Approval Queue: errors and warnings from approve / reject shown
- [ ] Approved, awaiting execution: Execute (re-checked by D), shows a block or an execution error
- [ ] Customer Experience: customer picker, phone mock-up, lock-screen text only, messages (Quiet Help options, meeting time and call code)
- [ ] Caller verification (P3): type the code the caller quoted → genuine / possible scam, recorded in the ledger; warning when empty; never shows the real code
- [ ] Activity & Status: recommendation status table, ledger activity table (newest first), "append-only, no reset here" note

### New in the React UI
- [ ] Home: C → D → E pipeline with live counts per node
- [ ] Home: the 10-step story ticks itself, with a "next: go to … and do …" hint
- [ ] Demo controls in one shared panel (load stage, hero form, insider edit, checkpoint)
- [ ] One tab, always fresh (TanStack Query refetch on focus + every 3 s, invalidated after every button)

## Deviations from the plan (and why)
- (filled in while building)
