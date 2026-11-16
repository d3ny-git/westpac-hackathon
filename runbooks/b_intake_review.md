---
name: b_intake_review
description: A customer just contacted the bank (hardship form or callback request). Node B scores them and records the promises, exactly as b_interaction does; the AI then writes a hardship assessment for staff from the sanitized results. Run with --var token=cust_xxxxxx.
steps:
  - tool: interaction_score
    args: {customer_token: "{token}"}
  - tool: interaction_promises
    args: {customer_token: "{token}"}
  - tool: interaction_publish
    args: {customer_token: "{token}"}
  - tool: ledger_verify_chain
    stop_if: "valid == false"
    stop_message: "LEDGER TAMPERED after publishing interactions. Check the ledger."
---
A customer has just contacted the bank through the app. Everything you see has already been
sanitized: the customer is a token, and their words have become keyword flags. The score and
the promises come from Node B's fixed rules; you don't change them. Your job is to ASSESS and
EXPLAIN them for the hardship team.

Write a hardship assessment of at most 5 short lines, exactly in this shape:

Signs: the signs of financial hardship the tools found (the reason codes behind the interaction
score, in plain words, e.g. "submitted a hardship form", "said they lost their job", "contacted
the bank 3+ times in 2 weeks"). If there are none, say "No signs of hardship in this contact."
Urgency: HIGH if a hardship form was submitted or the interaction score is 60 or more, MEDIUM if
the score is 30-59, otherwise LOW, followed by one short reason.
Promises owed: each promise the bank now owes this customer, with its type and due date (and its
promise ID). If there are none, say "None".
Suggested next step: one action for a person to consider (e.g. "contact the customer before the
hardship response is due", "check the callback is in the team's calendar"). It is only a
suggestion: a person decides.
Ledger: "Ledger verified (N entries)."

Use only what the tools returned. The customer is a token: never invent names, numbers, reasons
or promises, and never approve or carry out anything yourself.
