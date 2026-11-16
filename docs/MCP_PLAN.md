# Customer Guardian: Final MCP Build Plan

## Context
Hackathon project (see `docs/SPEC.pdf`, `docs/basics.txt`, `docs/customer_guardian_overview.png`). Westpac was fined $26m for missing hardship requests. Customer Guardian tracks the bank's **promises** and checks that they were kept:

A (Account score) + B (Interaction score + promises) → C (hash-chained ledger, Quiet Help, Risk Dashboard) → D (Policy Agent) → E (Actions, human-approved) → back to C.

The team is 4 people who know Python but are new to MCP, so A, B, D and E are kept deliberately simple (4 tools each). The ledger (C) is the core of the system, so it gets the full treatment: SQLite, append-only triggers and 5 tools.

**A and B follow the same simple pattern:**
```
A:  mock CSV (with PII)         ─►  sanitize  ─►  agentic workflow (runbooks/a_account.md)      ─►  ledger
B:  mock input form (with PII)  ─►  sanitize  ─►  agentic workflow (runbooks/b_interaction.md)  ─►  ledger
```
In the agentic workflow, **the AI chooses the next tool by following the runbook, and the tools do the work.** The AI never calculates a score or reads customer text.

**Stack:**
- One FastMCP server
- OpenRouter for the LLM
- Streamlit for the UI
- Runs locally; code on GitHub

**Owners:** A = Owner-A · B = Owner-B · C + D + shared setup = Owner-CD (technical lead) · E = Owner-E.

---

## 1. Rules and how the code enforces them

### No PII: a sanitizing step comes before everything
A and B receive **realistic bank data that contains PII**: names, emails, phones, date of birth, address, BSB/account numbers, staff names, and free text. A gets a mock transactions CSV; B gets a mock input form plus a mock history CSV. Plain code (no AI) sanitizes it before anything else can see it:

```
A: data/raw/transactions_raw.csv     B: mock input form + data/raw/interactions_raw.csv
            (has PII)                              (has PII)
                 │                                     │
                 ▼                                     ▼
            sanitize.py   (plain code, no AI)
               1. tokenise IDs
               2. drop PII columns
               3. extract keyword flags, then delete free text
                 │
                 ▼
            data/clean/*.csv      (no PII)
                 │
                 ▼
            agent.py + runbook  ──►  MCP tools (code does the work)  ──►  ledger
```

`shared/pii_guard.py` (owned by B, used by all nodes):

| Function | What it does |
|---|---|
| `tokenise(customer_id)` | Returns `"cust_" + hmac_sha256(TOKEN_SECRET, id)[:6]`. The same ID always gives the same token, and the token can't be reversed without the secret. Staff become `staff_xxx` the same way. |
| `keep_columns(df, allow_list)` | Keeps only the allow-listed columns. Any unknown or new column is dropped by default. |
| `scrub_text(text)` | Regex for emails, AU phones, BSB/account numbers, card numbers, DOBs and a names list. Used only to extract keyword **flags**; the text itself is then deleted. |
| `assert_no_pii(obj)` + `@safe_tool` | Every MCP tool's output is checked. If PII is found, the tool errors instead of returning. |

**Security boundaries:**
1. The MCP server and every node only read from `data/clean/` and the ledger DB. **No code path from an MCP tool touches `data/raw/`**; a test greps for this.
2. Sanitizing is **plain code, not an MCP tool**, so the AI never triggers a read of raw data. For A it runs as a script; for B it runs when the form is submitted.
3. Defence in depth: `@safe_tool` runs on every tool in A–E, and `shared/llm.py` (the only file that talks to OpenRouter) runs `assert_no_pii()` on everything before sending it.

### Deterministic
- Rules are plain Python. Weights and cut-offs live in `shared/config.py`.
- No rule uses `datetime.now()`: everything uses a fixed `AS_OF = 2026-11-16T10:00`.
- The LLM only follows a markdown runbook at `temperature=0`. `--no-ai` runs the same steps without the LLM.

### AI recommends, humans decide
Approve/Reject is **only a Streamlit button**. It isn't an MCP tool, so the AI can't approve anything.

### Tamper-proof
Ledger entries are hash-chained. SQLite triggers block UPDATE and DELETE, and `ledger_verify_chain` detects any edit.

---

## 2. Repo structure

```
westpac-hackathon/
  README.md
  requirements.txt  # mcp, openai, streamlit, pandas, pydantic, python-dotenv, pyyaml, pytest
  .env              # NOT in GitHub. Owner-CD shares the values: OPENROUTER_API_KEY,
                    # OPENROUTER_MODEL, TOKEN_SECRET, CALL_CODE_SECRET
  shared/
    schemas.py      # Pydantic models for every JSON message in SPEC (CD, frozen after Phase 0)
    config.py       # AS_OF, rule weights, band cut-offs, column allow-lists
    pii_guard.py    # tokenise, keep_columns, scrub_text, assert_no_pii, @safe_tool (B)
    llm.py          # the ONLY file that calls OpenRouter: PII check, temperature 0, logging (CD)
  sanitize.py       # sanitize_transactions() (A) + sanitize_interaction() (B)
  nodes/
    account.py      # A: rules + 4 tools
    interaction.py  # B: rules + 4 tools
    ledger/         # C (full version)
      store.py        # SQLite append/read + append-only triggers
      chain.py        # sha256 hash chain + verify
      quiet_help.py   # combined score + Quiet Help rule
      dashboard.py    # Risk Dashboard ranking
      tools.py        # 5 MCP tools
    policy.py       # D: P1–P4 + recommendations + 4 tools
    actions.py      # E: approve/reject (UI only) + execute + 4 tools
  server.py         # FastMCP: each node's register(mcp)
  agent.py          # runs a runbook: AI picks the next tool, tools do the work (CD)
  runbooks/         # a_account.md (A), b_interaction.md (B), policy_sweep.md, execute.md (CD)
  ui/app.py + ui/pages/  A.py B.py C.py D.py E.py
  data/
    raw/            # mock CSVs WITH fake PII (inputs only)
    clean/          # sanitized CSVs (gitignored, rebuilt)
    fixtures/       # ready-made node outputs, so nobody waits
    guardian.db     # SQLite ledger (gitignored, rebuilt)
  scripts/ generate_raw_data.py  reset_demo.py  tamper_demo.py
  tests/            # one per node + test_pii.py + test_story.py
```

Each simple node is **one Python file** containing plain functions and a `register(mcp)` that wraps 4 of them as tools:
```python
def register(mcp):
    @mcp.tool()
    @safe_tool
    def account_score_all() -> list[dict]:
        return [s.model_dump() for s in score_all_customers()]
```
Nodes write to the ledger with `ledger.store.append(...)` in Python. **`append` is not an MCP tool.**

---

## 3. Tools and tasks per node

### A: Account (Owner-A)
**Workflow:** mock CSV → sanitize → agentic workflow → ledger

```
1. generate_raw_data.py      → data/raw/transactions_raw.csv   (fake PII)      [code]
2. sanitize_transactions()   → data/clean/transactions.csv     (tokens only)   [code]
3. agent.py runbooks/a_account.md                                [AI follows runbook]
     account_check_data → account_score_all → account_publish
     → ledger_verify_chain → summary
```

**Raw columns:** customer_id, full_name, email, phone, dob, address, bsb, account_number, date, account_type, amount, category, merchant, description, balance_after.

**After sanitizing:** customer_token, date, account_type, amount, category, merchant, balance_after.

| Tool | Returns |
|---|---|
| `account_check_data()` | Row and customer counts, plus confirmation that only allow-listed columns are present |
| `account_score_all()` | `[{token, score, band, reasons}]`, calculated by the rules in code |
| `account_publish()` | Writes a SCORE entry per customer to the ledger and returns the count |
| `account_rules()` | The rule table, so the AI can explain reasons |

Tasks:
- **A1.** `generate_raw_data.py` (transactions part): seeded mock CSV with fake PII, personas as in §5.
- **A2.** `sanitize_transactions()`: tokenise, apply the allow-list, drop `description` (it can contain names, e.g. "TRANSFER TO J CITIZEN").
- **A3.** Signal rules in `nodes/account.py`:
  - salary stopped +25
  - dishonour +10
  - overdrawn +2 per day
  - 3+ BNPL providers +8
  - loan arrears +15
  - cap at 100, then assign the band
  - Golden test: hero → **63 HIGH**
- **A4.** The 4 tools + `runbooks/a_account.md`. Check that `--no-ai` and AI mode give the same ledger entries.
- **A5.** `ui/pages/A.py`: "raw columns → kept columns" panel, a **Run workflow** button, the run log, and the score and reasons per customer.

### B: Interactions (Owner-B)
**Workflow:** mock input form → sanitize → agentic workflow → ledger

```
1. ui/pages/B.py mock form   pick a fake customer, channel, type; type free
                             text (PII included)                           [human]
2. sanitize_interaction()    on submit: tokenise, extract keyword flags,
                             DELETE the text, append to clean CSV          [code]
3. agent.py runbooks/b_interaction.md --token cust_xxxxxx   [AI follows runbook]
     interaction_score → interaction_promises → interaction_publish
     → ledger_verify_chain → summary
```
A small mock history CSV (`data/raw/interactions_raw.csv`) is sanitized the same way at reset, so rules like "3+ contacts in 14 days" and the scripted personas have data behind them.

**Raw fields (form or CSV):** customer_id, full_name, email, phone, staff_name, date, channel, type, form_status, callback_due, text.

**After sanitizing:** customer_token, staff_token, date, channel, type, form_status, callback_due, flags (e.g. `JOB_LOSS`, `CANT_AFFORD`). **The text is deleted.**

| Tool | Returns |
|---|---|
| `interaction_score(token)` | Score message (source = INTERACTION), calculated by the rules in code |
| `interaction_promises(token)` | Promise messages built from rules (HARDSHIP_FORM → HARDSHIP_RESPONSE due +21 days; CALLBACK_REQUEST → CALLBACK due `callback_due`). Descriptions come from fixed templates. |
| `interaction_publish(token)` | Writes the SCORE + new PROMISE entries for that customer to the ledger |
| `interaction_rules()` | The rule and keyword table |

Tasks:
- **B1.** `shared/pii_guard.py` + `tests/test_pii.py`. This is the security centrepiece.
- **B2.** `sanitize_interaction()` (used by both the form and the history CSV) + the mock history CSV with fake PII in the text.
- **B3.** Rules in `nodes/interaction.py`:
  - form +40
  - keywords +25
  - 3+ contacts in 14 days +10
  - abandoned form +15
  - Golden test: hero → **50 MODERATE**
- **B4.** The 4 tools + `runbooks/b_interaction.md`. Check that `--no-ai` and AI mode give the same ledger entries.
- **B5.** `ui/pages/B.py`: the **mock input form**. On submit it shows "kept vs thrown away" (local UI only, never the AI), runs the workflow, and shows the promises that reached the ledger.

### C: Ledger (Owner-CD, full version)
Each entry has the SPEC fields: entry_id, customer_token, entry_type, data, created_at, prev_hash, hash. Entry types are SCORE / PROMISE / CONTACT_SCHEDULED / ACTION / BLOCKED / STATUS_UPDATE, plus **RECOMMENDATION** and **APPROVAL** (additions to the spec).

| Tool | Returns |
|---|---|
| `ledger_get_history(token)` | All entries for a customer |
| `ledger_verify_chain()` | `{valid, entries_checked, first_bad_entry}` |
| `ledger_combined_score(token)` | `min(100, floor(max + min/4))`, band, and whether a hardship case is open. Hero → **75 HIGH**. |
| `ledger_quiet_help_candidates()` | HIGH+ AND no open hardship case AND no Quiet Help push in the last 30 days |
| `ledger_risk_dashboard()` | Open promises sorted by combined score, then hours to due date |

Tasks:
- **C1 (Phase 0, first).** `schemas.py`, `config.py`, `store.py` (SQLite append/read), an empty `server.py`, `shared/llm.py` and a basic `assert_no_pii` (B replaces it later). Push to main and share the `.env` values with the team outside GitHub.
- **C2.** `chain.py`:
  - hash = sha256 of canonical JSON (sorted keys) of the entry plus prev_hash; the genesis entry's prev_hash is 64 zeros
  - SQLite triggers abort on UPDATE or DELETE
  - `scripts/tamper_demo.py` drops a trigger, edits one row, and shows verify failing
  - tests
- **C3.** `quiet_help.py` + `dashboard.py` + combined score, with tests.
- **C4.** `data/fixtures/ledger_seed.json`, `scores.json` and `promises.json`, so D and E can start immediately.
- **C5.** `ui/pages/C.py`: ledger table with hash columns, a big green/red "Chain verified" badge, a tamper button, the Risk Dashboard and the Quiet Help list.

### D: Policy Agent (Owner-CD)
| Tool | Returns |
|---|---|
| `policy_check_action(token, action, requested_by, call_code?)` | ALLOW/BLOCK + policy + reason, written to the ledger (ACTION or BLOCKED). P2 blocks a default/collections notice while a hardship case is open. P3 blocks a caller with no matching CONTACT_SCHEDULED call code. P4 blocks a credit offer to a HIGH+ customer. |
| `policy_deadlines()` | P1: promises due within 24h (ALERT) or past due (ESCALATE) |
| `policy_recommend()` | Quiet Help list → QUIET_HELP_PUSH; open hardship with no meeting → BOOK_MEETING; missed deadline → ESCALATE. Written as RECOMMENDATION (AWAITING_APPROVAL). |
| `policy_explain(entry_id)` | The facts behind a decision, for the AI to put into plain English |

Tasks:
- **D1.** P1–P4 as pure functions, plus one test per policy.
- **D2.** Recommendation rules.
- **D3.** `agent.py` + `policy_sweep.md` and `execute.md` (see §4). Build `agent.py` early, since A and B use it for their workflows too.
- **D4.** `data/fixtures/action_requests.json`: default notice, credit offer, scam call (wrong code), real call (right code).
- **D5.** `ui/pages/D.py`: an action request form → decision, P1 alerts, and the agent run log.

### E: Actions (Owner-E)
| Tool | Returns |
|---|---|
| `actions_pending()` | Recommendations awaiting approval |
| `actions_execute_approved()` | Runs **only** items with an APPROVAL entry, after re-checking policy. QUIET_HELP_PUSH creates message M-xxxx. BOOK_MEETING creates a call code plus CONTACT_SCHEDULED and PROMISE(MEETING) entries. |
| `actions_inbox(token)` | What the customer's app shows |
| `actions_status(rec_id)` | AWAITING / APPROVED / REJECTED / DONE |

Not tools: `approve(rec_id, staff)` and `reject(rec_id, staff)`, called only by the UI.

Tasks:
- **E1.** Approve/reject/execute with ledger write-back. The call code is `hmac(CALL_CODE_SECRET, rec_id)` → 6 characters, so it is repeatable and can't be guessed.
- **E2.** Tests: unapproved items are refused, approved items run, a meeting becomes a promise.
- **E3.** `ui/pages/E.py`: approval queue (staff dropdown + Approve/Reject buttons) and a **mock phone**. The lock screen only says "You have a new message from Westpac"; tapping it shows the options and the call code. Includes a "verify caller code" box.
- **E4.** `ui/app.py` home page: the A→E pipeline with live counts per node and a **"Next step"** button that walks SPEC's 10-step story.
- **E5.** `scripts/reset_demo.py` (generate → sanitize → run the A and B runbooks with `--no-ai`) + a demo rehearsal checklist.

---

## 4. AI workflow: markdown runbooks

**The idea:** the AI is an operator with a checklist. The runbook says which tools to call and in what order; the tools (plain Python) do all the work; the AI then writes a short summary. The AI never scores, decides or approves anything.

**`shared/llm.py`** (about 40 lines) is the only file that talks to OpenRouter:
- uses the `openai` SDK with `base_url=https://openrouter.ai/api/v1` and the model from `.env`
- `temperature=0`
- runs `assert_no_pii()` on everything before sending it
- logs each request and response to `data/runs/`

Teammates may also call `llm.ask()` to **explain** results (e.g. an "Explain this score" button), but never inside scoring, policy or approval code.

**`agent.py`** (about 100 lines) runs a runbook:
1. Reads the runbook's tool list and instructions.
2. Starts `server.py` over stdio with the `mcp` client.
3. Gives the model **only** the tools listed in the runbook.
4. Loops through `llm.py`: the AI asks for a tool, `agent.py` checks it's the next expected step (otherwise it stops with `OFF_SCRIPT`), calls the tool, and sends the result back.
5. Logs every step to `data/runs/<run_id>.jsonl`, which the UI pages show.

`--no-ai` calls the listed steps directly. This is the demo fallback and proves the result is the same.

| Runbook | Owner | Steps |
|---|---|---|
| `a_account.md` | A | account_check_data → account_score_all → account_publish → ledger_verify_chain → summary |
| `b_interaction.md` | B | interaction_score → interaction_promises → interaction_publish → ledger_verify_chain → summary (for one `--token`) |
| `policy_sweep.md` | CD | ledger_verify_chain (stop if invalid) → policy_deadlines → ledger_quiet_help_candidates → policy_recommend → summary |
| `execute.md` | CD | actions_pending → actions_execute_approved → ledger_verify_chain → summary |

Example (`runbooks/policy_sweep.md`):
```markdown
---
tools: [ledger_verify_chain, policy_deadlines, ledger_quiet_help_candidates, policy_recommend]
---
Call these tools in exactly this order. If ledger_verify_chain says valid=false, stop and say "LEDGER TAMPERED".
Then write a 3-line summary using only numbers and tokens the tools returned.
```

---

## 5. Synthetic data (parallel work, not waterfall)

### Raw data
`scripts/generate_raw_data.py` (fixed seed) writes `data/raw/transactions_raw.csv` (A's input) and `data/raw/interactions_raw.csv` (B's mock history) with **realistic fake PII**. The names, emails, phones and account numbers are invented, and the text mentions names and numbers. This is exactly what the sanitizer must remove. B's live input comes from the mock form on top of that history.

Tokens come from HMAC, so they won't literally be `cust_8f2a91`. The generator writes `fixtures/personas.json` (persona name → token), and tests look customers up by persona name.

### Personas (6 scripted + about 10 random)
| Persona | Story | What it exercises |
|---|---|---|
| `hero` | SPEC story: salary stopped, dishonour, 3 BNPL, 10 overdrawn days, later a hardship form | A=63, B=50, C=75, Quiet Help → meeting, P2, P3 |
| `fine` | Nothing wrong | LOW, nothing happens |
| `critical` | Everything bad | CRITICAL, P4 blocks credit offer |
| `open_case` | HIGH, hardship case already open | Excluded from Quiet Help |
| `recent_push` | HIGH, pushed 12 days ago | Excluded (30-day rule) |
| `late_callback` | Overdue callback | P1 escalate |

### Fixtures: each person builds against these until the real upstream node is ready
| File | Lets this node start early | Pretends to be |
|---|---|---|
| `fixtures/clean_transactions.csv`, `clean_interactions.csv` | A, B (before the sanitizer is done) | sanitize.py output |
| `fixtures/scores.json`, `promises.json` | C | A + B output |
| `fixtures/ledger_seed.json` | D, E | C |
| `fixtures/recommendations.json` | E | D |
| `fixtures/action_requests.json` | D | staff, collections and scam callers |
| `fixtures/staff.json` | UI | staff tokens |

---

## 6. UI: Streamlit, one page per owner
`streamlit run ui/app.py`. Every page has the same header showing **"← gets data from / sends data to →"** and its latest ledger entries, so the flow is visible on every screen.

| Page | Shows |
|---|---|
| Home (E) | Pipeline diagram with live counts + "Next step" story walkthrough |
| A | Raw → kept columns, Run workflow button + run log, score and reasons per customer |
| B | Mock input form → kept vs thrown away → workflow run log → promises in the ledger |
| C | Ledger with hashes, chain badge, tamper button, Risk Dashboard, Quiet Help list |
| D | Action check (ALLOW/BLOCK), P1 alerts, AI run log |
| E | Approval buttons + mock customer phone + caller code check |

(The raw-data panels on the A and B pages are local Streamlit views for the judges. They never go through MCP or the AI.)

## 7. Hosting
- Local laptops only, with code on GitHub.
- Repo: https://github.com/d3ny-git/westpac-hackathon (private).
- Setup: `pip install -r requirements.txt`, then create `.env` with the values Owner-CD shares (never committed), then `python scripts/reset_demo.py`, then `streamlit run ui/app.py`.
- No database server and no deployment. The MCP server is started automatically by `agent.py` over stdio.
- `.env`, `data/clean/`, `data/guardian.db` and `data/runs/` are gitignored. `data/raw/` is committed because it's fake.

## 8. Project management
- **GitHub Projects board** with columns To do / Doing / Review / Done. One issue per task (A1–E5), labelled by node.
- **One branch per task.** PR into `main`; Owner-CD reviews anything in `shared/` or `sanitize.py`.
- **Phases:**
  - **Phase 0** (CD, first half-day): skeleton, schemas, ledger store, `shared/llm.py`, fixtures. A 30-minute MCP intro for the team.
  - **Phase 1:** everyone builds against fixtures until their golden tests pass.
  - **Phase 2:** swap fixtures for the real nodes; the full 10-step story runs.
  - **Phase 3:** UI polish and rehearsal.
- **Schema changes:** only through a PR that everyone sees. `shared/schemas.py` is the contract between nodes.

## 9. Verification
1. `pytest`: golden scores (63 / 50 / 75), P1–P4, the tamper test, and `test_pii.py`. That test calls every MCP tool and asserts no PII appears in its output; it also asserts that nothing under `nodes/` or `server.py` references `data/raw`.
2. After `reset_demo.py`, grep `data/clean/`, `data/guardian.db`, `data/runs/` and the OpenRouter request logs for every fake name, email and phone from `data/raw/`: there must be **zero hits**.
3. For each runbook (`a_account.md`, `b_interaction.md`, `policy_sweep.md`, `execute.md`), run it with `--no-ai` and then without. The tool calls and ledger entries should match.
4. Submit B's mock form with a fake name, phone and email in the text. Then grep the ledger and `data/runs/` for them: **zero hits**.
5. Run `python scripts/tamper_demo.py`: the C page badge goes red and shows the first bad entry.
6. On a fresh reset, click "Next step" through all 10 SPEC steps. The default notice ends BLOCKED by P2 and the scam call ends BLOCKED by P3.
