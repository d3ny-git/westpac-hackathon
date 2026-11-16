---
name: execute
description: Node E carries out the recommendations a PERSON has approved, then checks the ledger again.
steps:
  - tool: ledger_verify_chain
    stop_if: "valid == false"
    stop_message: "LEDGER TAMPERED: nothing was carried out. Check the ledger page."
  - actions_pending
  - actions_execute_approved
  - tool: ledger_verify_chain
    stop_if: "valid == false"
    stop_message: "LEDGER TAMPERED after carrying out actions. Check the ledger page."
---
Write a summary of at most 4 short lines for the hardship team lead:

1. How many recommendations are still waiting for a person to approve them.
2. What was carried out: for each one the rec_id, customer token and action (Quiet Help push,
   meeting booked, escalation). Never repeat a call code.
3. "Ledger verified (N entries)." after the actions.

Use only what the tools returned. Only APPROVED recommendations are ever carried out; say so if
nothing was approved.
