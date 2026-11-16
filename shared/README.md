# `shared/`: code every node uses

This folder holds the pieces that **all** nodes (A, B, C, D, E) rely on. You don't need to understand every line to use them. This page explains what each file is for and how to use it from your node.

**You can change anything in here.** If something doesn't fit what you're building, edit it. Other nodes use these files too, so drop a quick message in the team chat when you do (e.g. "added `OFFER_OVERDRAFT` to the action list").

## What's in this folder

| File | What it is | Plain-English version |
|---|---|---|
| `config.py` | Fixed values and word lists | The **settings page**: today's date for the demo, score bands, deadlines, and the allowed words (e.g. which actions exist). |
| `schemas.py` | The shape of every message | The **forms everyone fills in**: what a score, promise or decision must contain. If you fill one in wrong, you get a clear error straight away. |
| `pii_guard.py` | Personal-information detector | A **sniffer dog** for emails, phone numbers, BSBs, dates of birth and card numbers. |
| `llm.py` | The only way to talk to the AI | The **phone line to the AI**. It checks for personal info before sending, logs every call, and keeps answers consistent. |
| `__init__.py` | Empty file | Tells Python this folder is a package. Leave it alone. |

---

## `config.py`: the settings page

The values you'll use most:

```python
from shared.config import AS_OF, now, band, Band

now()          # 2026-11-16 10:00:00. Use this instead of datetime.now(), ALWAYS
band(63)       # Band.HIGH
band(25)       # Band.LOW
```

Why `now()` instead of the real time? The demo "lives" on 16 Nov 2026, so the same data always gives the same scores. If you use the real clock, results change every day and tests break.

**Bands:** LOW (under 30), MODERATE (30–59), HIGH (60–79), CRITICAL (80+).

**Other values in here:** the 21-day hardship deadline, the 24-hour P1 alert window, the 30-day Quiet Help cooldown, the list of allowed actions (`SEND_DEFAULT_NOTICE`, `OFFER_CREDIT_CARD`, …), transaction categories, channels, and so on.

## `schemas.py`: the forms

Each message type is a **model**. You create a message by filling in the model; Python checks every field for you.

```python
from shared.schemas import ScoreMessage

msg = ScoreMessage(
    customer_token="cust_af4200",
    source="ACCOUNT",
    score=63,
    band="HIGH",
    reasons=["SALARY_STOPPED", "OVERDRAWN"],
    timestamp="2026-11-16T10:00:00",
)

msg.model_dump(mode="json")   # turns it into a plain dict, ready for the ledger or a JSON file
```

### Which models you'll probably use

| Node | Models |
|---|---|
| **A** | `CleanTransaction` (one row of your sanitized CSV), `ScoreMessage` (your output) |
| **B** | `CleanInteraction` (one row of your sanitized CSV), `ScoreMessage`, `Promise` (your outputs) |
| **C** | `LedgerEntry`, `validate_entry_data()` |
| **D** | `ActionRequest`, `Decision`, `DeadlineAlert`, `Recommendation` |
| **E** | `Approval`, `QuietHelpPush`, `MeetingBooking`, `Escalation`, `ContactScheduled`, `StatusUpdate` |

Each model has a short comment and, where the SPEC gives one, an example. Open `schemas.py` and search for the name.

### What it catches for you

| You do this | You get an error because… |
|---|---|
| `customer_token="Jane Citizen"` | Customers must be tokens like `cust_af4200` |
| `score=63, band="LOW"` | 63 is HIGH, so the band doesn't match the score |
| add `full_name="..."` | Unknown fields are refused, so personal info can't sneak into a message |
| `decision="BLOCK"` with no `policy` | A block must say which policy (P1–P4) caused it |
| `msg.score = 10` after creating it | Messages can't be changed after they're made, just like the ledger |

### Reading an error

```
1 validation error for ScoreMessage
full_name
  Extra inputs are not permitted [type=extra_forbidden, input_value='x', input_type=str]
```
- Line 1 names the model (`ScoreMessage`).
- Line 2 names the field (`full_name`).
- Line 3 says what's wrong ("Extra inputs are not permitted", meaning this field doesn't exist in the model).

## `pii_guard.py`: the sniffer dog

```python
from shared.pii_guard import find_pii, assert_no_pii

find_pii("call me on 0491 570 156")    # ['AU_MOBILE']  (which KIND was found, never the value)
assert_no_pii({"customer_token": "cust_af4200", "score": 63})   # fine, does nothing
assert_no_pii("email jane@example.com")                          # raises PIIError
```

Use `assert_no_pii()` on anything you're about to send outside your own code, e.g. before returning from an MCP tool.

## `llm.py`: the phone line to the AI

You only need this for **explaining** results in plain English, e.g. an "Explain this score" button:

```python
from shared.llm import explain

text = explain(
    {"score": 63, "band": "HIGH", "reasons": ["SALARY_STOPPED", "OVERDRAWN"]},
    "Why does this customer have this score?",
)
# -> "The customer is HIGH risk mainly because their salary stopped and ..."
```

To check your AI key works: `python -m shared.llm`

**Never use the AI to calculate a score, decide a policy, or approve anything.** Those must stay plain Python, so the same input always gives the same answer.

---

## Changing things: common examples

| You want to… | Do this |
|---|---|
| Add a new reason code (e.g. `GAMBLING_SPEND`) | Nothing to change. Any UPPER_CASE code is allowed in `reasons`. |
| Add a new action (e.g. `OFFER_OVERDRAFT`) | Add it to `ActionType` in `config.py`. If it's a credit offer, also add it to `CREDIT_OFFER_ACTIONS` so policy P4 covers it. |
| Add a transaction category | Add it to `Category` in `config.py`. |
| Change a band cut-off or deadline | Edit the number in `config.py`. |
| Add a field to a message | Add a line to the model in `schemas.py`, e.g. `note_code: Optional[str] = None`. Use `Optional[...] = None` so older messages still work. |
| Add a new message type | Copy a similar model in `schemas.py`, rename it, and change the fields. |

After changing something, post a one-line heads-up in the team chat.

## The three golden rules
1. **No personal information** in any message: customers are `cust_xxxxxx`, staff are `staff_xxx`.
2. **No real clock** in rules: use `now()` from `config.py`.
3. **The AI only explains.** Scores, policies and approvals are plain Python.
