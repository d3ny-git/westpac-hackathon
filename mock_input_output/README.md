# Mock input and output for Nodes A, B and E

This folder lets A, B and E be built and tested **in parallel**. Nobody has to wait for anyone else.

- **`input/`** is what the node receives. It contains **FAKE PII** on purpose (names, emails, phones, DOB, address, BSB, account numbers), because that's what the sanitizer must remove. (E's inputs have no PII: they come after sanitizing.)
- **`output/`** is the correct answer. Your sanitizer and rules should produce exactly these files from the inputs. Use them as golden test data.

> Every person here is invented. Phone numbers come from the ACMA range reserved for fiction (0491 570 xxx), and emails use `example.com`. **Never put real customer data in this folder.**

## Settings used

| Setting | Value |
|---|---|
| `AS_OF` | `2026-11-16T10:00:00` (all "last N days" windows count back from here) |
| `TOKEN_SECRET` | `mock-demo-secret` (use this in `.env` when testing against these files, or your tokens won't match) |
| Customer token | `"cust_" + hmac_sha256(TOKEN_SECRET, customer_id).hexdigest()[:6]` |
| Staff token | `"staff_" + hmac_sha256(TOKEN_SECRET, staff_id).hexdigest()[:3]` |
| `CALL_CODE_SECRET` (E only) | `mock-call-code-secret`. Call codes in E's sample are `base32(hmac_sha256(CALL_CODE_SECRET, rec_id))[:6]`, e.g. R-0004 → `U5PXLW` |

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
  E_actions/
    input/recommendations.json          5 recommendations from Node D (awaiting approval)
    input/approvals.json                what staff clicked in the UI (3 approve, 1 reject, 1 not yet)
    output/action_results.json          what E carried out: Quiet Help push, meeting booking, escalation
    output/ledger_writes.json           every ledger entry E writes, in order (13 entries)
    output/customer_inbox.json          what the customer sees in the Westpac app
    output/pending.json                 what actions_pending() returns (still awaiting approval)
    output/status.json                  what actions_status(rec_id) returns for each recommendation
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
| `quiet_struggler` | `cust_6543f0` | **61 HIGH** | – (no interactions) | Alex Morgan (`100200309`). **Only in `data/raw/transactions_raw.csv`** (the demo data), not in the files here or `personas.json`, so the golden outputs are unchanged. Salary stopped after 2 Oct, 14 overdrawn days, 3 BNPL providers (Afterpay, Zip, Humm), no dishonour. Never contacted the bank, so Node B has no score for them and their Quiet Help message is a **gentle tip**, not the support offer |

**Hero before the form:** with only the history CSV processed, hero's B score is **0 LOW** (2 contacts, no keywords). That's why hero is a Quiet Help candidate first. Once the mock form is submitted, it becomes 50, and combined with A it's floor(63 + 50/4) = **75 HIGH**.

## E: Actions

E's input is **D's output**, so there's no raw data or PII here. Everything is already tokens and codes. Every file matches the models in `shared/schemas.py`.

**Inputs**
- `recommendations.json`: what Node D recommended (`Recommendation` messages, status `AWAITING_APPROVAL`).
- `approvals.json`: what staff clicked on E's page (`Approval` messages). In the real app these come from the Approve/Reject buttons, never from the AI.

**The 5 recommendations and what happens to each**

| rec_id | Customer | Recommendation | Human decision | What E does | Final status |
|---|---|---|---|---|---|
| R-0001 | hero `cust_af4200` | QUIET_HELP_PUSH | ✅ approved by `staff_b38` | Sends push **M-0001** with options PAUSE / REDUCE / BOOK_CALL | DONE |
| R-0002 | late_callback `cust_2c7c98` | ESCALATE | ✅ approved by `staff_9bb` | Escalates the overdue callback | DONE |
| R-0003 | critical `cust_bb4b75` | QUIET_HELP_PUSH | ❌ rejected by `staff_9bb` | **Nothing is sent** | REJECTED |
| R-0004 | hero `cust_af4200` | BOOK_MEETING | ✅ approved by `staff_b38` | Books 18 Nov 14:00 with call code **U5PXLW**, schedules the contact, adds a MEETING promise (**P-0005**) | DONE |
| R-0005 | open_case `cust_3d6abe` | BOOK_MEETING | (no decision yet) | **Nothing.** It stays in the approval queue | AWAITING_APPROVAL |

**What E writes to the ledger** (`ledger_writes.json`): each item is exactly what E passes to `ledger.store.append(entry_type, customer_token, data)`. The ledger adds the ID, time and hashes.

| Situation | Entries, in order |
|---|---|
| Approved Quiet Help push / escalation | `APPROVAL` → `ACTION` → `STATUS_UPDATE` (rec → DONE) |
| Approved meeting | `APPROVAL` → `ACTION` (MeetingBooking) → `CONTACT_SCHEDULED` (call code, for policy P3) → `PROMISE` (MEETING) → `STATUS_UPDATE` (rec → DONE) |
| Rejected | `APPROVAL` (approved=false) → `STATUS_UPDATE` (rec → REJECTED). No action |
| No decision yet | nothing |

**What the customer sees** (`customer_inbox.json`): the lock screen only ever says *"You have a new message from Westpac"*. The details (options, meeting time, call code) only show inside the app. This is the data for the mock phone on E's page.

**Caller check examples** for E's "verify caller code" box (the answer comes from Node D, policy P3):
- hero + code `U5PXLW` → **ALLOW** (matches the CONTACT_SCHEDULED entry)
- hero + code `K7P4QX` or anything else → **BLOCK, P3, POSSIBLE_SCAM**
- open_case + any code → **BLOCK, P3** (no meeting booked yet)

Meeting times, message wording and the call-code method are just this sample's choices. E can change any of them.

## How to use this
- **A:** `sanitize_transactions(input/transactions_raw.csv)` should equal `output/transactions_clean.csv`, and running your rules over it should equal `output/account_scores.json`.
- **B:** sanitizing the history plus the form entries should equal `output/interactions_clean.csv`, and running your rules should equal `output/interaction_scores.json` and `output/promises.json`.
- **PII test:** none of the names, emails, phones, BSBs or account numbers in `input/` may appear anywhere in `output/`, the ledger or the run logs.
- **E:** feed `input/recommendations.json` + `input/approvals.json` through your approve/execute code; the ledger entries you write should match `output/ledger_writes.json`, and `actions_pending()`, `actions_status()` and `actions_inbox()` should return `pending.json`, `status.json` and `customer_inbox.json`.
- **C, D and E:** use A's and B's `output/` files as your stand-in for A and B until the real nodes are ready.
