# `runbooks/`: checklists the AI follows

A runbook is a markdown file that tells the AI **which tools to call, in which order**, and **what to say at the end**. `agent.py` runs it:

```bash
python agent.py runbooks/ledger_check.md
python agent.py runbooks/b_interaction.md --var token=cust_af4200     # fills {token} in the runbook
```

The AI decides nothing: the tools (plain Python) do the work, and the AI only calls them in order and writes a summary.

## The format

```markdown
---
name: ledger_check
description: Check nobody has tampered with the ledger, then report the most urgent open promises.
steps:
  - ledger_verify_chain                 # a tool with no inputs: just its name
  - ledger_risk_dashboard
  - tool: ledger_combined_score         # a tool with inputs: give them here
    args: {customer_token: "{token}"}   # {token} comes from --var token=...
---
Plain-English instructions for the SUMMARY: what to report, how long, what to leave out.
```

- **`steps`** are the only tools the AI is given, and it must call them **in exactly this order**.
- **`args`** are fixed by you. The AI can't change them, and the tool always runs with the runbook's values.
- The text after the second `---` is shown to the AI. Use it to describe the summary you want.

## What `agent.py` checks for you

| If the AI… | The run stops as |
|---|---|
| calls a tool that isn't the next step, changes an argument, or calls an extra tool | `OFF_SCRIPT` |
| stops before every step is done | `INCOMPLETE` |
| hits a tool error (e.g. bad input) | `TOOL_ERROR` |
| would send or receive anything that looks like personal information | `BLOCKED_PII` |
| finishes every step and writes the summary | `COMPLETED` |

Every run is logged step by step to `data/runs/<run_id>.jsonl` (gitignored). The AI calls themselves are logged to `data/runs/llm_calls.jsonl`.

## Runbooks

| File | Owner | Steps |
|---|---|---|
| `ledger_check.md` | CD | `ledger_verify_chain` → `ledger_risk_dashboard` |
| `a_account.md` | A | `account_check_data` → `account_score_all` → `account_publish` → `ledger_verify_chain` |
| `b_interaction.md` | B | `interaction_score` → `interaction_promises` → `interaction_publish` → `ledger_verify_chain` (with `--var token=…`) |
| `policy_sweep.md` | CD | `ledger_verify_chain` → `policy_deadlines` → `ledger_quiet_help_candidates` → `policy_recommend` (D-8) |
| `execute.md` | CD | `actions_pending` → `actions_execute_approved` → `ledger_verify_chain` (D-8, once E's tools exist) |

A runbook can only use tools that are on the server: check with `python server.py --list`.
