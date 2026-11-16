# Customer Guardian

Westpac hackathon project. Westpac was fined $26m for missing customer hardship requests. Customer Guardian keeps track of the **promises** the bank makes to customers (call them back, answer a hardship form, book a meeting) and checks that they were kept. It:
- scores each customer's risk from their account activity and their interactions with the bank
- records everything in a tamper-proof ledger
- applies plain-code policies
- recommends actions that a human must approve

Built in Python with one MCP server (`mcp` 2.x), an OpenRouter LLM, a Streamlit UI and SQLite, all running locally.

## Status

| What | State |
|---|---|
| Plan, docs, mock data | Done (`docs/`, `mock_input_output/`) |
| `shared/`: `llm.py` (AI gateway), `pii_guard.py` (PII check + `@safe_tool`), `config.py`, `schemas.py` | Done ([shared/README.md](shared/README.md)) |
| C-2 Ledger store: `store.append()`, `read()`, `next_id()` | Done |
| C-7 MCP server: `server.py` + `scripts/try_tool.py`. **A, B, E can now add their tools** ([nodes/README.md](nodes/README.md)) | Done |
| C-3 Tamper check: `verify_chain()` + `ledger_verify_chain` tool | Done |
| C-5/C-6 Ledger logic: combined score, open hardship case, Quiet Help list, Risk Dashboard. **All 5 ledger tools done** | Done |
| D-1 Policy gatekeeper: `check_action()` with P2 (no collections during hardship) and P4 (no credit offers to HIGH+). P3 caller check is a fail-closed placeholder until D-2 | Done |
| C-8 Seed data: `python scripts/load_fixtures.py` loads a realistic demo ledger (`--stage start` or `full`) | Done |
| C-9 Ledger page: `streamlit run ui/pages/C.py` (integrity badge + checkpoint, Risk Dashboard, Quiet Help, customer lookup, full ledger, demo controls) | Done |
| D-2 Caller check (P3): a caller is ALLOWED only if their call code matches a booked call (`CONTACT_SCHEDULED`); otherwise BLOCKED as a possible scam | Done |
| D-3 Deadline watcher (P1): `check_deadlines()` flags open promises due within 24h (ALERT) or overdue (ESCALATE) | Done |
| D-4 Recommendations: `recommend()` suggests ESCALATE / BOOK_MEETING / QUIET_HELP_PUSH (awaiting human approval, no repeats within 30 days). `tracked_recommendations()` gives each one's status, ready for Node E | Done |
| D-5 Explain: `explain(entry_id)` gives the facts behind any decision or recommendation (as known at the time, call codes hidden); `explain_in_words()` has the AI rephrase them for staff | Done |
| D-6 Policy tools: `policy_check_action`, `policy_deadlines`, `policy_recommend`, `policy_explain` (the server now has 9 tools) | Done |
| D-7 `agent.py`: runs a runbook with the AI, keeping it on script (only the listed tools, in order, with the runbook's arguments). **A and B can now write and run their runbooks** ([runbooks/README.md](runbooks/README.md)) | Done |
| D-8 Runbooks: stop rules (e.g. stop if the ledger was tampered with), `--no-ai` mode (same steps, no AI: identical ledger), `policy_sweep.md`, `execute.md` (waits for E's tools) | Done |
| D-9 Policy page: `streamlit run ui/pages/D.py` (check an action, deadlines, recommendations, decisions, explain with AI, run the policy sweep + replay runs) | Done |
| **C and D board complete.** | Done |
| E-1/E-3 (Node E): approve/reject + ledger-connected dashboard `streamlit run ui/pages/E.py` | Done |
| FLOW-1/2/3: E carries out approved actions (push, meeting + call code), stand-in for B's hardship form, E's MCP tools, `execute.md`, caller check on the E page. **The SPEC's full story runs C → D → E** | Done |
| AB-1 Sanitizing: `python sanitize.py` turns raw data (fake PII) into clean data (tokens only); `tokenise`, `keep_columns`, `scrub_text` in `shared/pii_guard.py` | Done |
| AB-2 Node A (`nodes/account.py`) and AB-3 Node B (`nodes/interaction.py`): scoring from clean data, B's promises, 4 MCP tools each. **The server now has all 5 nodes (21 tools)** | Done |
| AB-4 A/B runbooks (`a_account.md`, `b_interaction.md`) + `python scripts/reset_demo.py`: the REAL pipeline, raw data → sanitize → A and B → ledger, with a PII self-check | Done |
| AB-5 A and B pages: `streamlit run ui/pages/A.py` (raw → clean, run A's workflow, scores) and `ui/pages/B.py` (**B's mock input form**: kept vs thrown away → B's workflow → promises) | Done |
| **A, B, C, D and E are all built; the SPEC's full story runs on the real pipeline.** Next: FLOW-4 (GEL React UI) on branch `ui/gel-react` | In progress |
| Nodes A–E, UI | Not started. Build against `mock_input_output/` until upstream nodes are ready. |

## The pipeline

```
A  Account score ─────┐
                      ├──►  C  Ledger  ──►  D  Policy Agent  ──►  E  Actions
B  Interaction score ─┘     (hash-chained)                         (human-approved)
   + promises                    ▲                                     │
                                 └─────────────────────────────────────┘
```

| Node | What it does |
|---|---|
| **A** Account | Scores each customer from their transactions (salary stopped, dishonours, overdrawn days, BNPL, arrears). |
| **B** Interactions | Scores each customer from their contacts with the bank and extracts the promises the bank made. |
| **C** Ledger | Append-only, hash-chained record of every score, promise and decision. Also the Quiet Help list and Risk Dashboard. |
| **D** Policy Agent | Checks actions against policies P1–P4 and recommends next steps. |
| **E** Actions | Runs recommendations only after a person approves them in the UI. |

### How A and B work

Both follow the same three steps:

```
A:  mock CSV (with PII)         ─►  sanitize  ─►  agentic workflow (runbooks/a_account.md)      ─►  ledger
B:  mock input form (with PII)  ─►  sanitize  ─►  agentic workflow (runbooks/b_interaction.md)  ─►  ledger
```

1. **Mock input:** A reads a transactions CSV. B takes entries from a Streamlit form (plus a small history CSV). Both contain fake PII.
2. **Sanitize:** plain code swaps IDs for tokens (`cust_xxxxxx`), drops PII columns, and for B extracts keyword flags and then **deletes the free text**.
3. **Agentic workflow:** `agent.py` follows the node's markdown runbook. The AI picks the next tool from the runbook's list; the tools (plain Python) calculate the score and write it to the ledger; the AI then writes a short summary.

## Where the AI fits

The AI is an **operator with a checklist**. It never calculates a score, reads customer text, makes a decision or approves anything.

| File | Role |
|---|---|
| `shared/llm.py` | The **only** file that talks to OpenRouter. Temperature 0, checks everything for PII before sending, logs every call. Teammates may use `llm.ask()` to *explain* results, but never inside scoring, policy or approval code. |
| `agent.py` | Runs a runbook: gives the AI only the tools the runbook lists, rejects any call that's out of order, logs each step to `data/runs/`. `--no-ai` runs the same steps without the AI, as a demo fallback and to check that both give the same result. |
| `runbooks/*.md` | The checklists: `a_account.md` (A), `b_interaction.md` (B), `policy_sweep.md` and `execute.md` (CD). |

## The 4 core rules

1. **No PII ever reaches the AI.** Raw data (names, emails, phones, account numbers, free text) is sanitized by plain code first. Everything downstream only sees tokens like `cust_xxxxxx`, and every MCP tool's output is checked for PII again.
2. **Deterministic.** Scoring and policy rules are plain Python, not AI. Rules use a fixed `AS_OF` date, never "now". Same input, same output.
3. **AI only recommends, humans approve.** Approve/Reject is a button in the Streamlit UI, not something the AI can call.
4. **Tamper-proof ledger.** Every ledger entry is hash-chained to the one before it, and the database blocks edits and deletes. Any tampering is detected.

## Owners

| Area | Owner |
|---|---|
| A: Account | Owner-A |
| B: Interactions | Owner-B |
| C: Ledger + D: Policy Agent + shared setup incl. `shared/llm.py` and `agent.py` (tech lead) | Owner-CD |
| E: Actions (incl. home page and demo reset) | Owner-E |

## Mock data

[`mock_input_output/`](mock_input_output/README.md) holds fake inputs and the correct outputs for A and B, so everyone can build in parallel:

- **`A_account/`**
  - `input/transactions_raw.csv` (fake PII)
  - `output/transactions_clean.csv` (sanitized)
  - `output/account_scores.json`
- **`B_interaction/`**
  - `input/interactions_history_raw.csv` + `input/form_submissions.json` (fake PII)
  - `output/interactions_clean.csv` (text deleted)
  - `output/interaction_scores.json` + `output/promises.json`
- **`personas.json`**: 8 customers (hero, fine, critical, open_case, recent_push, late_callback, steady_bnpl, tight_month) with their tokens and expected scores. Hero: A = **63 HIGH**, B = **50 MODERATE**, combined **75 HIGH**.

Set `TOKEN_SECRET=mock-demo-secret` when testing against these files, or the tokens won't match. The exact rule definitions are in [`mock_input_output/README.md`](mock_input_output/README.md).

## Docs

- [docs/MCP_PLAN.md](docs/MCP_PLAN.md): the full build plan (tools, tasks per node, runbooks, UI, phases). Start here.
- [docs/Customer_Guardian_MCP_Plan.pdf](docs/Customer_Guardian_MCP_Plan.pdf): the same plan as a PDF.
- `docs/SPEC.pdf`, `docs/basics.txt`, `docs/customer_guardian_overview.png`: the original brief.

## Planned layout

```
shared/        schemas.py  config.py  pii_guard.py  llm.py
sanitize.py    sanitize_transactions() (A) + sanitize_interaction() (B)
nodes/         account.py  interaction.py  ledger/  policy.py  actions.py
server.py      one MCP server (each node registers its tools)
agent.py       runbook runner
runbooks/      a_account.md  b_interaction.md  policy_sweep.md  execute.md
ui/            app.py + pages/ A.py B.py C.py D.py E.py
scripts/       generate_raw_data.py  reset_demo.py  tamper_demo.py
tests/
```

## Setup (once Phase 0 lands)

> These commands won't work yet. The code, `requirements.txt` and scripts arrive in Phase 0.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# create a .env file with the values Owner-CD shares with the team (not stored in GitHub):
#   OPENROUTER_API_KEY, OPENROUTER_MODEL, TOKEN_SECRET, CALL_CODE_SECRET
python -m shared.llm             # check your OpenRouter key + model work (works today)
python -m pytest                 # run the tests (works today)
python scripts/reset_demo.py     # start a demo: raw data -> sanitize -> A and B -> ledger (works today)
python scripts/reset_demo.py --empty   # or start with an empty ledger and run A and B live on their pages
python scripts/load_fixtures.py  # or: load mock demo data straight into the ledger (--stage full = end state)
python server.py --list          # list every MCP tool, grouped by node (works today)
python scripts/try_tool.py       # call a tool by hand, as the AI would (works today)
streamlit run ui/pages/A.py      # the account page (works today)
streamlit run ui/pages/B.py      # the interactions page + mock input form (works today)
streamlit run ui/pages/C.py      # the ledger page (works today)
streamlit run ui/pages/D.py      # the policy page (works today)
streamlit run ui/pages/E.py      # the actions page (works today)
python agent.py runbooks/ledger_check.md   # the AI runs a runbook (works today, needs .env)
python agent.py runbooks/policy_sweep.md --no-ai   # the policy sweep without the AI (works today)
python scripts/reset_demo.py     # generate -> sanitize -> run A and B workflows (--no-ai)
streamlit run ui/app.py
```

## Team workflow

- **One branch per task**, named `<node>/<short-name>`, e.g. `a/score-rules`, `b/pii-guard`, `c/hash-chain`.
- Open a **pull request into `main`** when it's ready. Don't push straight to `main`.
- **Anyone can change `shared/`.** It's used by every node, so mention it in the team chat when you do. See [shared/README.md](shared/README.md).
- **Never commit `.env` or real data.** Only fake data belongs in the repo (`mock_input_output/`, `data/raw/`). `.env`, `data/clean/`, `data/guardian.db` and `data/runs/` are gitignored.
