# Customer Guardian

Westpac hackathon project. Westpac was fined $26m for missing customer hardship requests. Customer Guardian keeps track of the **promises** the bank makes to customers (call them back, answer a hardship form, book a meeting) and checks that they were kept. It scores each customer's risk from their account activity and their interactions with the bank, records everything in a tamper-proof ledger, applies plain-code policies, and recommends actions that a human must approve. Built in Python with one FastMCP server, an OpenRouter LLM, a Streamlit UI and SQLite, all running locally.

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
| **D** Policy Agent | Checks actions against policies P1-P4 and recommends next steps. |
| **E** Actions | Runs recommendations only after a person approves them in the UI. |

## The 4 core rules

1. **No PII ever reaches the AI.** Raw CSVs (names, emails, phones, account numbers, transcripts) are sanitized by plain code first (`sanitize.py`). Everything downstream only sees tokens like `cust_xxxxxx`.
2. **Deterministic.** Scoring and policy rules are plain Python, not AI. Same input, same output.
3. **AI only recommends, humans approve.** Approve/Reject is a button in the Streamlit UI, not something the AI can call.
4. **Tamper-proof ledger.** Every ledger entry is hash-chained to the one before it, and the database blocks edits and deletes. Any tampering is detected.

## Owners

| Area | Owner |
|---|---|
| A: Account | Owner-A |
| B: Interactions (incl. `shared/pii_guard.py`) | Owner-B |
| C: Ledger + D: Policy Agent + shared setup (tech lead) | Owner-CD |
| E: Actions (incl. home page and demo reset) | Owner-E |

## Docs

- [docs/MCP_PLAN.md](docs/MCP_PLAN.md): the full build plan (tools, tasks per node, data, phases). Start here.
- [docs/Customer_Guardian_MCP_Plan.pdf](docs/Customer_Guardian_MCP_Plan.pdf): the same plan as a PDF.
- `docs/SPEC.pdf`, `docs/basics.txt`, `docs/customer_guardian_overview.png`: the original brief.

## Setup (once Phase 0 lands)

> These commands will not work yet. The code, `requirements.txt` and scripts arrive in Phase 0.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# create a .env file with the values Owner-CD shares with the team (not stored in GitHub)
python scripts/reset_demo.py     # generate -> sanitize -> load -> score
streamlit run ui/app.py
```

## Team workflow

- **One branch per task**, named `<node>/<short-name>`, e.g. `a/score-rules`, `b/pii-guard`, `c/hash-chain`.
- Open a **pull request into `main`** when it's ready. Don't push straight to `main`.
- **Owner-CD reviews any change to `shared/` or `sanitize.py`.** `shared/schemas.py` is the contract between nodes, so changes to it go through a PR everyone sees.
- **Never commit `.env` or real data.** Only the fake, generated data in `data/raw/` belongs in the repo. `.env`, `data/clean/`, `data/guardian.db` and `data/runs/` are gitignored.
