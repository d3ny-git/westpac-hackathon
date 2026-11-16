// Types for the live apps (the customer app and the Westpac dashboard), matching api/customer.py,
// api/westpac.py and api/live.py. The walkthrough's types stay in ../api.ts.
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
  lock_screen: string;
  in_app_title: string;
  in_app_body: string;
  options?: string[];
  meeting_time?: string;
  call_code?: string;
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
};
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
