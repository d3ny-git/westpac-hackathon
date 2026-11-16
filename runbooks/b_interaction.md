---
name: b_interaction
description: Node B scores one customer from their clean interactions, finds the promises the bank made, and writes both to the ledger. Run with --var token=cust_xxxxxx.
steps:
  - tool: interaction_score
    args: {customer_token: "{token}"}
  - tool: interaction_promises
    args: {customer_token: "{token}"}
  - tool: interaction_publish
    args: {customer_token: "{token}"}
  - tool: ledger_verify_chain
    stop_if: "valid == false"
    stop_message: "LEDGER TAMPERED after publishing interactions. Check the ledger page."
---
Write a summary of at most 4 short lines for the hardship team lead:

1. The customer's interaction score and band, with the reason codes.
2. The promises the bank has made to them: type, due date, and whether each was just written
   to the ledger or was already there (give the promise IDs).
3. "Ledger verified (N entries)."

Use only what the tools returned. The customer is a token: never invent names, numbers or reasons.
