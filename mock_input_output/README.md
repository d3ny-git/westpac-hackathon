# Mock input and output for Nodes A and B

This folder lets A and B be built and tested **in parallel**. Nobody has to wait for anyone else.

- **`input/`** is what the node receives. It contains **FAKE PII** on purpose (names, emails, phones, DOB, address, BSB, account numbers), because that's what the sanitizer must remove.
- **`output/`** is the correct answer. Your sanitizer and rules should produce exactly these files from the inputs. Use them as golden test data.

> Every person here is invented. Phone numbers come from the ACMA range reserved for fiction (0491 570 xxx), and emails use `example.com`. **Never put real customer data in this folder.**

## Settings used

| Setting | Value |
|---|---|
| `AS_OF` | `2026-11-16T10:00:00` (all "last N days" windows count back from here) |
| `TOKEN_SECRET` | `mock-demo-secret` (use this in `.env` when testing against these files, or your tokens won't match) |
| Customer token | `"cust_" + hmac_sha256(TOKEN_SECRET, customer_id).hexdigest()[:6]` |
| Staff token | `"staff_" + hmac_sha256(TOKEN_SECRET, staff_id).hexdigest()[:3]` |

## Folder layout

```
mock_input_output/
  personas.json                         who's who: persona → token → expected scores (no PII)
  A_account/
    input/transactions_raw.csv          333 transactions, 8 customers, 18 Aug – 15 Nov 2026 (HAS PII)
    output/transactions_clean.csv       after sanitize: PII columns dropped, IDs → tokens
    output/account_scores.json          Score messages Node A sends to the ledger
  B_interaction/
    input/interactions_history_raw.csv  10 past calls/chats/forms/emails (HAS PII, incl. inside the text)
    input/form_submissions.json         2 entries typed into the mock input form (HAS PII)
    output/interactions_clean.csv       history + form after sanitize: tokens + keyword flags, TEXT DELETED
    output/interaction_scores.json      Score messages Node B sends to the ledger
    output/promises.json                Promise messages Node B sends to the ledger
```

## A: Account

**Sanitize** `transactions_raw.csv` → `transactions_clean.csv`:
- keep `customer_token, date, account_type, amount, category, merchant, balance_after`
- drop `customer_id, full_name, email, phone, dob, address, bsb, account_number, description`. The description can contain names and account numbers, e.g. "TRANSFER FROM J CITIZEN SAVINGS 032-101 481203".

**Rules** (on the clean data):

| Signal | Exact definition | Points | Reason code |
|---|---|---|---|
| Salary stopped | SALARY 36–90 days before AS_OF, and none in the last 35 days | +25 | `SALARY_STOPPED` |
| Dishonour | any DISHONOUR in the last 30 days | +10 | `DISHONOUR` |
| Overdrawn | +2 per day in the last 30 days where the end-of-day TRANSACTION balance < 0 (the last `balance_after` that day, carried forward over days with no rows) | +2/day | `OVERDRAWN` |
| BNPL stacking | 3+ different BNPL `merchant`s in the last 30 days | +8 | `BNPL_STACKING` |
| Loan arrears | LOAN_REPAYMENT 36–90 days before AS_OF, and none in the last 35 days | +15 | `LOAN_ARREARS` |

Cap at 100. Bands: LOW < 30, MODERATE 30–59, HIGH 60–79, CRITICAL 80+.

## B: Interactions

**Inputs:** the history CSV plus the mock form entries (same fields). In the app, the form entries arrive one at a time from the Streamlit form.

**Sanitize** each row → `interactions_clean.csv`:
- `customer_id` → `customer_token`, `staff_id` → `staff_token` (empty for self-service forms)
- extract keyword **flags** from `text`, then **delete the text**:
  - `JOB_LOSS`: "lost my job", "made redundant", "laid off"
  - `CANT_AFFORD`: "can't afford", "cant afford", "cannot afford", "struggling to pay"
- drop `full_name, email, phone, staff_name`

**Rules** (per customer):

| Rule | Points | Reason code |
|---|---|---|
| HARDSHIP_FORM with form_status SUBMITTED in the last 30 days | +40 | `HARDSHIP_FORM` |
| Any keyword flag in the last 30 days | +25 | `HARDSHIP_KEYWORDS` |
| 3+ interactions in the last 14 days | +10 | `REPEAT_CONTACT` |
| HARDSHIP_FORM with form_status ABANDONED in the last 30 days | +15 | `ABANDONED_FORM` |

**Promises** (descriptions are fixed templates, never customer text). IDs are numbered `P-0001…` in date order:
- SUBMITTED hardship form → `HARDSHIP_RESPONSE`, due = form date 17:00 + 21 days, made_by `SYSTEM`
- CALLBACK_REQUEST → `CALLBACK`, due = `callback_due`, made_by = staff token

## Personas: expected results

| Persona | Token | A score | B score | Story |
|---|---|---|---|---|
| `hero` | `cust_af4200` | **63 HIGH** | **50 MODERATE** | SPEC story: salary stopped 1 Oct, 10 days overdrawn, dishonour, 3 BNPL. Asked for a callback (due 18 Nov 14:00), then submits a hardship form through the mock form (response due 1 Dec). |
| `fine` | `cust_16dea0` | 0 LOW | 0 LOW | Nothing wrong |
| `critical` | `cust_bb4b75` | **86 CRITICAL** | 50 MODERATE | Everything bad, including loan arrears; "can't afford" chat + abandoned hardship form |
| `open_case` | `cust_3d6abe` | 61 HIGH | 65 HIGH | Hardship form already submitted 2 Nov ("lost my job"), so a case is open and they're excluded from Quiet Help |
| `recent_push` | `cust_a26449` | 60 HIGH | 0 LOW | HIGH, but got a Quiet Help push 12 days ago (that push lives in the ledger fixture, not here), so excluded |
| `late_callback` | `cust_2c7c98` | 30 MODERATE | 0 LOW | Callback was due 14 Nov 10:00, so it's **overdue** and policy P1 should escalate |
| `steady_bnpl` | `cust_9f4bf9` | 8 LOW | 25 LOW | 3 BNPL providers; says "struggling to pay" through the mock form |
| `tight_month` | `cust_5e4a19` | 8 LOW | 0 LOW | 4 overdrawn days before payday; a complaint email |

**Hero before the form:** with only the history CSV processed, hero's B score is **0 LOW** (2 contacts, no keywords). That's why hero is a Quiet Help candidate first. Once the mock form is submitted, it becomes 50, and combined with A it's floor(63 + 50/4) = **75 HIGH**.

## How to use this
- **A:** `sanitize_transactions(input/transactions_raw.csv)` should equal `output/transactions_clean.csv`, and running your rules over it should equal `output/account_scores.json`.
- **B:** sanitizing the history plus the form entries should equal `output/interactions_clean.csv`, and running your rules should equal `output/interaction_scores.json` and `output/promises.json`.
- **PII test:** none of the names, emails, phones, BSBs or account numbers in `input/` may appear anywhere in `output/`, the ledger or the run logs.
- **C, D and E:** use the `output/` files as your stand-in for A and B until the real nodes are ready.
