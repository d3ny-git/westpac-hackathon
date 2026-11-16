---
name: a_account
description: Node A scores every customer from their clean transactions and writes the scores to the ledger.
steps:
  - tool: account_check_data
    stop_if: "columns_ok == false"
    stop_message: "STOPPED: the clean transaction data has unexpected columns, so nothing was scored. Re-run sanitize.py."
  - account_score_all
  - account_publish
  - tool: ledger_verify_chain
    stop_if: "valid == false"
    stop_message: "LEDGER TAMPERED after publishing account scores. Check the ledger page."
---
Write a summary of at most 4 short lines for the hardship team lead:

1. "Checked N transactions for M customers (dates FROM to TO)."
2. How many customers are in each band (LOW, MODERATE, HIGH, CRITICAL), and name the HIGH and
   CRITICAL ones by token with their score.
3. How many scores were written to the ledger and how many were unchanged.
4. "Ledger verified (N entries)."

Use only what the tools returned. Customers are tokens like cust_af4200: never invent names,
numbers or reasons.
