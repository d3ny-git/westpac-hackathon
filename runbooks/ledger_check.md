---
name: ledger_check
description: Check nobody has tampered with the ledger, then report the most urgent open promises.
steps:
  - ledger_verify_chain
  - ledger_risk_dashboard
---
Write a summary of at most 4 short lines for a bank team lead:

1. Is the ledger intact? Say "Ledger verified (N entries)" or, if valid is false, start with
   "LEDGER TAMPERED" and name the first bad entry and the problem.
2. How many promises are open, and how many are OVERDUE or DUE_SOON.
3. Name each OVERDUE promise: customer token, promise type, and how long overdue.

Use only numbers and tokens the tools returned. Don't add advice.
