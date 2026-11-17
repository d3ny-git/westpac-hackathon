// Types for the live apps (the customer app and the Westpac dashboard), matching api/customer.py,
// api/westpac.py and api/live.py. The walkthrough's types stay in ../api.ts.
import type { CheckResult } from '../api';
import type { RunResult } from '../api';

// ---------------------------------------------------------------------------
// Customer app
// ---------------------------------------------------------------------------
export type SignInOption = { customer_id: string; full_name: string };
export type CustomerAccount = {
  account_type: string;
  name: string;
  number: string;
  bsb: string;
  balance: number;
  as_of: string;
};
export type CustomerTransaction = {
  date: string;
  account: string;
  description: string;
  amount: number;
  balance_after: number;
};
export type CustomerOverview = {
  first_name: string;
  full_name: string;
  accounts: CustomerAccount[];
  transactions: CustomerTransaction[];
  today: string;
};
export type CustomerMessage = {
  n: number;
  kind: 'QUIET_HELP' | 'MEETING';
  variant?: 'OFFER' | 'TIP'; // QUIET_HELP only: the support offer, or a gentle tip (no hardship wording)
  lock_screen: string;
  in_app_title: string;
  in_app_body: string;
  options?: string[];
  meeting_time?: string;
  call_code?: string;
  id: string; // the hash of the ledger entry that sent it
  seen: boolean; // already shown in the app
  answered: boolean; // the customer acted on it (asked for help after an offer)
  answered_on: string | null;
};
export type CustomerPromise = { kind: string; text: string; due: string };
export type Received = { received: boolean; message: string };
export type CallVerdict = { genuine: boolean; message: string };

// ---------------------------------------------------------------------------
// Westpac dashboard
// ---------------------------------------------------------------------------
export type LiveCycle = {
  n: number;
  trigger?: string;
  started?: string;
  finished?: string;
  error?: string;
  scoring?: { status: string; account_scores_written?: number; customers?: number; promises_written?: number; note?: string };
  sweep?: RunResult & { ai_used: boolean; ai_note: string | null };
  executed?: Record<string, unknown>[];
  execute_error?: string;
  paused?: string; // the ledger didn't verify: nothing was scored or carried out
};
/** "Check an action" on the dashboard: fails closed (paused) when the ledger doesn't verify. */
export type WestpacCheck = Omit<CheckResult, 'entry_id'> & { entry_id: string | null; paused: boolean };
/** A caller who couldn't give the customer's call code (P3). */
export type ScamAlert = { entry_id: string; created_at: string; customer_token: string; reason: string | null };
export type LiveStatus = {
  enabled: boolean;
  interval_seconds: number;
  ai: boolean;
  busy: string | null;
  cycles: number;
  next_check_in_seconds: number | null;
  pending_intakes: number;
  last_cycle: LiveCycle | null;
};
export type Intake = {
  n: number;
  customer_token: string;
  date: string;
  channel: string;
  type: string;
  form_status: string;
  callback_due: string;
  flags: string[];
  status: string;
  score: number | null;
  band: string | null;
  reasons: string[];
  promises: { promise_id: string | null; promise_type: string; due: string }[];
  promises_written: string[];
  assessment: string;
  ai_used: boolean;
  ai_note: string | null;
};
export type ActionDone = {
  entry_id: string;
  created_at: string;
  customer_token: string;
  action: string;
  [key: string]: unknown;
};
