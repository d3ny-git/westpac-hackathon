---
name: policy_sweep
description: Node D's regular sweep. Check the ledger, find missed deadlines and Quiet Help candidates, and create recommendations for a person to approve.
steps:
  - tool: ledger_verify_chain
    stop_if: "valid == false"
    stop_message: "LEDGER TAMPERED: the sweep stopped before doing anything. Nothing was recommended. Check the ledger page."
  - policy_deadlines
  - ledger_quiet_help_candidates
  - policy_recommend
---
Write a summary of at most 5 short lines for the hardship team lead:

1. "Ledger verified (N entries)."
2. Deadlines: how many promises are OVERDUE and how many are due within 24 hours. Name each
   overdue one: customer token, promise type, how long overdue.
3. Quiet Help: how many customers are on the list, with their tokens and scores.
4. New recommendations: how many were created, and for each one the rec_id, customer token and
   recommendation. If none were created, say "No new recommendations (nothing new since the last sweep)."
5. End with: "All recommendations are waiting for a person to approve them."

Use only what the tools returned. Never invent customers, numbers or reasons, and don't suggest
actions of your own.
