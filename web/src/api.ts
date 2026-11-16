// Typed client for the Customer Guardian API (api/ on the Python side), plus TanStack Query hooks.
// Every query refetches every few seconds and on focus (main.tsx); every action invalidates all
// queries when it finishes, so every page in the one tab is always up to date.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

// ---------------------------------------------------------------------------
// Types (same shapes as the API's JSON)
// ---------------------------------------------------------------------------
export type Meta = { now: string; hero: string; stages: string[]; staff: string[]; checkable: string[] };
export type DemoStatus = { count: number; hero_form_submitted: boolean; clean_ready: boolean };
export type ResetReport = { transactions: number; customers: number; promises: number; entries: number; empty: boolean };

/** A workflow run (agent.RunResult) as the API returns it. */
export type RunStep = { n: number; tool: string; args: Record<string, unknown>; ok: boolean; output: unknown };
export type RunResult = {
  run_id: string;
  runbook: string;
  mode: string;
  status: string;
  summary: string;
  error: string | null;
  steps: RunStep[];
};

// Account (A)
export type AccountOverview = {
  clean_ready: boolean;
  raw_file: string | null;
  columns: { column: string; status: 'kept' | 'customer_token' | 'dropped' }[];
  check: {
    rows: number | null;
    customers: number | null;
    columns_ok: boolean;
    first_date?: string | null;
    last_date?: string | null;
  } | null;
};
export type RawSample = {
  people: { customer_id: string; full_name: string }[];
  customer_id: string;
  raw: Record<string, string>;
  clean: Record<string, string>;
};
export type AccountScore = {
  customer_token: string;
  score: number;
  band: string;
  reasons: string[];
  signals: Record<string, number | boolean>;
  in_ledger: boolean;
};
export type AccountRule = { reason: string; points: number; rule: string };
export type AccountEntry = { entry_id: string; customer_token: string; score: number; band: string; reasons: string[] };

// Interactions (B)
export type InteractionOverview = {
  clean_ready: boolean;
  clean_rows: Record<string, string>[];
  entries: { entry_id: string; customer_token: string; entry_type: string; what: string }[];
};
export type RawSubmission = {
  customer_id: string;
  full_name: string;
  email: string;
  phone: string;
  staff_id: string;
  staff_name: string;
  date: string;
  channel: string;
  type: string;
  form_status: string;
  callback_due: string;
  text: string;
};
export type FormOptions = {
  customers: { customer_id: string; full_name: string; email: string; phone: string }[];
  staff: { staff_id: string; staff_name: string }[];
  examples: RawSubmission[];
  channels: string[];
  types: string[];
  form_statuses: string[];
  defaults: { date: string; callback_day: string; callback_time: string };
};
export type CustomerPromise = {
  promise_id: string | null;
  promise_type: string;
  due: string;
  made_by: string;
  description: string;
};
export type CustomerNow = {
  customer_token: string;
  score: CombinedScore | null;
  open_case: boolean;
  promises: CustomerPromise[];
};
export type SubmitResult = {
  clean: Record<string, string>;
  thrown_away: Record<string, string>;
  flags: string;
  run: RunResult;
  customer: CustomerNow;
};
export type RunAllResult = {
  customers: number;
  rows: { customer_token: string; status: string; score: string; score_written: boolean; promises_written: string[] }[];
};

export type ChainReport = {
  valid: boolean;
  entries_checked: number;
  first_bad_entry: string | null;
  problem: string | null;
  detail: string | null;
  last_entry_id: string | null;
  head_hash: string;
};
export type Checkpoint = { last_entry_id: string; head_hash: string; entries: number; holds: boolean };
export type Integrity = { count: number; report: ChainReport; checkpoint: Checkpoint | null };

export type Entry = {
  entry_id: string;
  created_at: string;
  customer_token: string;
  entry_type: string;
  what: string;
  data: Record<string, unknown>;
  prev_hash: string;
  hash: string;
};
export type Entries = { entries: Entry[]; customers: string[]; types: string[]; bad_entry: string | null };

export type DashboardRow = {
  promise_id: string;
  customer_token: string;
  promise_type: string;
  description: string;
  made_by: string;
  due: string;
  hours_to_due: number;
  urgency: 'OVERDUE' | 'DUE_SOON' | 'UPCOMING';
  score: number;
  band: string;
};
export type QuietHelpCandidate = {
  customer_token: string;
  score: number;
  band: string;
  reasons: string[];
  last_quiet_help: string | null;
};
export type CombinedScore = {
  customer_token: string;
  account_score: number | null;
  interaction_score: number | null;
  score: number;
  band: string;
  reasons: string[];
  based_on: string[];
};
export type PromiseMsg = { promise_id: string; promise_type: string; due: string; description: string; status: string };
export type CustomerLookup = {
  customer_token: string;
  score: CombinedScore | null;
  open_case: PromiseMsg | null;
  history: Entry[];
};

export type Decision = {
  customer_token: string;
  action: string;
  decision: 'ALLOW' | 'BLOCK';
  policy: string | null;
  reason: string;
  flags: string[];
};
export type CheckResult = { entry_id: string; decision: Decision };
export type DeadlineAlert = {
  customer_token: string;
  promise_id: string;
  promise_type: string;
  due: string;
  level: 'ALERT' | 'ESCALATE';
  hours_to_due: number;
  reason: string;
};
export type TrackedRec = {
  rec_id: string;
  customer_token: string;
  recommendation: string;
  why: string[];
  status: string;
  decided_by: string | null;
  entry_id: string;
  recorded_at: string;
};
export type DecisionRow = {
  entry_id: string;
  created_at: string;
  customer_token: string;
  action: string;
  decision: 'ALLOW' | 'BLOCK';
  policy: string | null;
  reason: string;
  flags: string[];
};
export type Explanation = {
  entry_id: string;
  entry_type: string;
  customer_token: string;
  recorded_at: string;
  outcome: Record<string, unknown>;
  rule: string;
  facts: {
    combined_score: number | null;
    band: string | null;
    account_score: number | null;
    interaction_score: number | null;
    open_hardship_case: { promise_id: string; due: string } | null;
    meeting_booked: boolean;
    overdue_promises: { promise_id: string; promise_type: string; due: string }[];
    calls_booked: number;
    last_quiet_help_push: string | null;
    quiet_help_push_in_last_30_days: boolean;
  };
  evidence: Record<string, unknown>[];
};
export type SweepResult = { run_id: string; status: string; mode: string; summary: string; error: string | null };
export type RunSummary = { run_id: string; runbook: string | null; mode: string | null; status: string };
export type RunEvent = { event: string; [key: string]: unknown };
export type RunLog = RunSummary & { summary: string; error: string | null; events: RunEvent[] };

export type ActionItem = { rec_id: string; customer_token: string; recommendation: string; why: string[]; status: string };
export type Queue = {
  items: ActionItem[];
  counts: { pending: number; approved: number; completed: number; rejected: number; total: number };
};
export type InboxMessage = {
  message_id: string | null;
  kind: 'QUIET_HELP' | 'MEETING';
  lock_screen: string;
  in_app_title: string;
  in_app_body: string;
  options?: string[];
  meeting_time?: string;
  call_code?: string;
};
export type ExecuteResult = { rec_id: string; blocked?: Decision; action?: string; [key: string]: unknown };

export type Hint = { page: string; path: string; text: string };
export type StoryStep = { n: number; route: string; title: string; done: boolean; detail: string | null; hint: Hint | null };
export type Story = {
  customer_token: string;
  steps: StoryStep[];
  done_count: number;
  total: number;
  current: number | null;
  next: Hint | null;
  complete: boolean;
};
export type Pipeline = {
  A: { clean_transactions: number | null; account_scores: number };
  B: { clean_interactions: number | null; interaction_scores: number; promises: number };
  C: { entries: number; valid: boolean; customers: number; open_promises: number; quiet_help: number };
  D: { recommendations: number; deadline_alerts: number; allowed: number; blocked: number };
  E: { awaiting_approval: number; approved: number; done: number; rejected: number; messages_sent: number };
};

// ---------------------------------------------------------------------------
// Fetching
// ---------------------------------------------------------------------------
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!response.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new ApiError(response.status, typeof detail === 'string' ? detail : `${response.status} ${response.statusText}`);
  }
  return data as T;
}

export const get = <T>(path: string) => request<T>('GET', path);
export const post = <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {});

export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------
/** A GET endpoint as a live query. `path` null = don't fetch yet. */
export function useApi<T>(path: string | null, options: { refetch?: boolean } = {}) {
  return useQuery<T>({
    queryKey: [path],
    queryFn: () => get<T>(path!),
    enabled: path !== null,
    refetchInterval: options.refetch === false ? false : 3000,
  });
}

export const useMeta = () => useApi<Meta>('/api/demo/meta', { refetch: false });
export const useStatus = () => useApi<DemoStatus>('/api/demo/status');
export const useStory = () => useApi<Story>('/api/demo/story');

/** A button's action: runs `fn`, then refreshes every query (all pages in the tab stay fresh). */
export function useAction<A, R>(fn: (arg: A) => Promise<R>) {
  const queryClient = useQueryClient();
  return useMutation<R, Error, A>({
    mutationFn: fn,
    onSettled: () => queryClient.invalidateQueries(),
  });
}

export function params(values: Record<string, string[]>): string {
  const search = new URLSearchParams();
  for (const [key, list] of Object.entries(values)) list.forEach(v => search.append(key, v));
  const text = search.toString();
  return text ? `?${text}` : '';
}
