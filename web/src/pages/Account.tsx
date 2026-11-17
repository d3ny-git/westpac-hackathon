// Node A – Account. Same features as ui/pages/A.py:
//   1. Raw data -> clean data (columns kept / tokenised / dropped; one customer's raw row next to its
//      clean row)  2. Run Node A's workflow (with / without the AI) and its step log
//   3. Every customer's account score, reasons, signals, in the ledger; the rules  4. A's ledger entries
// The raw panel is a LOCAL view for the demo (docs/MCP_PLAN.md §6): raw data never goes through MCP
// or the AI. Node A itself only ever reads the clean data.
import { Accordion, AccordionItem } from '@westpac/ui/accordion';
import { Alert } from '@westpac/ui/alert';
import { Button } from '@westpac/ui/button';
import { Field } from '@westpac/ui/field';
import { ProgressIndicator } from '@westpac/ui/progress-indicator';
import { Select } from '@westpac/ui/select';
import { useState } from 'react';

import {
  AccountEntry,
  AccountOverview,
  AccountRule,
  AccountScore,
  RawSample,
  RunResult,
  errorText,
  post,
  useAction,
  useApi,
  useMeta,
} from '../api';
import {
  BandBadge,
  Caption,
  Code,
  CodeBadge,
  DataTable,
  ErrorAlert,
  FieldTable,
  Loading,
  PageTitle,
  RunView,
  Section,
  titleCase,
  when,
} from '../components';
import { DemoControlsFold } from '../DemoControls';

const COLUMN: Record<string, [string, 'success' | 'info' | 'danger']> = {
  kept: ['Kept', 'success'],
  customer_token: ['Becomes customer_token', 'info'],
  dropped: ['Dropped (personal information)', 'danger'],
};

export function AccountPage() {
  const meta = useMeta();
  const overview = useApi<AccountOverview>('/api/account/overview');
  const o = overview.data;
  return (
    <>
      <PageTitle title="Customer Guardian" subtitle="Node A – Account">
        <strong>Gets data from:</strong> the bank's transactions (sanitized first: no personal information) ·{' '}
        <strong>Sends data to:</strong> C (an account hardship SCORE per customer) · Demo time: {when(meta.data?.now)}
      </PageTitle>
      <DemoControlsFold />
      {overview.error && <ErrorAlert error={overview.error} />}
      {!o ? (
        <Loading />
      ) : !o.clean_ready ? (
        <Alert look="warning" heading="There's no clean transaction data yet">
          Use <strong>Reset demo (real pipeline)</strong> in Demo controls (or run <Code>python scripts/reset_demo.py</Code>).
        </Alert>
      ) : (
        <>
          <RawToClean overview={o} />
          <RunWorkflow />
          <Scores />
          <Entries />
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// 1. Raw -> clean
// ---------------------------------------------------------------------------
function RawToClean({ overview }: { overview: AccountOverview }) {
  const [pick, setPick] = useState<string | null>(null);
  const sample = useApi<RawSample>(`/api/account/raw-sample${pick ? `?customer_id=${encodeURIComponent(pick)}` : ''}`, {
    refetch: false,
  });
  const s = sample.data;
  const check = overview.check;
  return (
    <Section
      title="1. Raw data → clean data"
      caption="Local view for the demo only: raw data never goes through MCP or the AI. The sanitizer (plain code) keeps only the allowed columns and swaps the customer ID for a token."
    >
      {overview.columns.length === 0 ? (
        <Alert look="info">No raw transaction file.</Alert>
      ) : (
        <DataTable
          testId="raw-columns"
          caption="Raw columns and what happens to them"
          rows={overview.columns}
          rowKey={c => c.column}
          columns={[
            { header: 'Raw column', cell: c => <Code>{c.column}</Code> },
            {
              header: 'In clean data',
              cell: c => <CodeBadge color={COLUMN[c.status][1]}>{COLUMN[c.status][0]}</CodeBadge>,
            },
          ]}
        />
      )}
      {s && (
        <>
          <Field label="Show one customer's first transaction" className="mt-3 mb-2 md:max-w-xs">
            <Select value={s.customer_id} onChange={e => setPick(e.target.value)} width="full" data-testid="sample-customer">
              {s.people.map(p => (
                <option key={p.customer_id} value={p.customer_id}>
                  {p.full_name} ({p.customer_id})
                </option>
              ))}
            </Select>
          </Field>
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <p className="mb-1 typography-body-9 font-bold">Raw (fake personal information)</p>
              <FieldTable row={s.raw} caption="Raw transaction" testId="raw-row" />
            </div>
            <div>
              <p className="mb-1 typography-body-9 font-bold">Clean (what Node A sees)</p>
              <FieldTable row={s.clean} caption="Clean transaction" testId="clean-row" />
            </div>
          </div>
        </>
      )}
      {check &&
        (check.columns_ok ? (
          <Caption>
            Clean file: {check.rows} transactions for {check.customers} customers, {check.first_date} to {check.last_date}.
          </Caption>
        ) : (
          <Alert look="danger" className="mt-2">
            The clean transaction file has unexpected columns. Re-run the sanitizer (reset the demo).
          </Alert>
        ))}
    </Section>
  );
}

// ---------------------------------------------------------------------------
// 2. Run the workflow
// ---------------------------------------------------------------------------
function RunWorkflow() {
  const [result, setResult] = useState<RunResult | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const run = useAction((ai: boolean) => post<RunResult>(`/api/account/run?ai=${ai}`));
  const go = (ai: boolean) =>
    run.mutate(ai, {
      onSuccess: r => {
        setResult(r);
        setFailure(null);
      },
      onError: err => setFailure(errorText(err)),
    });
  return (
    <Section
      title="2. Run Node A's workflow"
      caption={
        <>
          <Code>runbooks/a_account.md</Code>: check the data → score everyone → publish to the ledger → verify the
          ledger. With the AI, it follows the checklist and writes a summary; without it, the same steps run directly.
          Unchanged scores aren't written twice.
        </>
      }
    >
      <div className="grid gap-2 md:grid-cols-2">
        <Button look="hero" soft block disabled={run.isPending} onClick={() => go(true)}>
          Run with the AI
        </Button>
        <Button look="primary" block disabled={run.isPending} onClick={() => go(false)}>
          Run without the AI
        </Button>
      </div>
      {run.isPending && (
        <div className="mt-2 flex items-center gap-2" role="status">
          <ProgressIndicator size="medium" label="Running Node A's workflow" />
          <span className="typography-body-10 text-text-muted">Running Node A's workflow…</span>
        </div>
      )}
      {failure && (
        <Alert look="danger" className="mt-2">
          {failure}
        </Alert>
      )}
      {result && (
        <div className="mt-2">
          <RunView run={result} testId="a-run" />
        </div>
      )}
    </Section>
  );
}

// ---------------------------------------------------------------------------
// 3. Scores and rules, 4. A's ledger entries
// ---------------------------------------------------------------------------
const SIGNALS = ['salary_stopped', 'dishonour', 'overdrawn_days', 'bnpl_providers', 'loan_arrears'];
const signal = (v: number | boolean | undefined) => (typeof v === 'boolean' ? (v ? 'yes' : 'no') : String(v ?? ''));

function Scores() {
  const scores = useApi<AccountScore[]>('/api/account/scores');
  const rules = useApi<AccountRule[]>('/api/account/rules', { refetch: false });
  return (
    <Section title="3. Account scores">
      {scores.error && <ErrorAlert error={scores.error} />}
      {scores.data && (
        <DataTable
          testId="a-scores"
          caption="Account scores"
          rows={scores.data}
          rowKey={s => s.customer_token}
          columns={[
            { header: 'Customer', cell: s => s.customer_token },
            { header: 'Score', cell: s => s.score },
            { header: 'Band', cell: s => <BandBadge band={s.band} /> },
            { header: 'Reasons', cell: s => s.reasons.join(', ') || '–' },
            ...SIGNALS.map(k => ({ header: titleCase(k), cell: (s: AccountScore) => signal(s.signals[k]) })),
            {
              header: 'In the ledger',
              cell: s => (s.in_ledger ? <CodeBadge color="success">Yes</CodeBadge> : <CodeBadge color="warning">Not yet</CodeBadge>),
            },
          ]}
        />
      )}
      <div className="mt-2">
        <Accordion>
          <AccordionItem key="rules" id="rules" title="The rules">
            {rules.data && (
              <DataTable
                caption="Node A's rules"
                rows={rules.data}
                rowKey={r => r.reason}
                columns={[
                  { header: 'Reason', cell: r => <Code>{r.reason}</Code> },
                  { header: 'Points', cell: r => r.points },
                  { header: 'Rule', cell: r => r.rule },
                ]}
              />
            )}
          </AccordionItem>
        </Accordion>
      </div>
    </Section>
  );
}

function Entries() {
  const entries = useApi<AccountEntry[]>('/api/account/entries');
  return (
    <Section title="4. Node A's entries in the ledger">
      {entries.data && entries.data.length === 0 && (
        <Alert look="info">Node A hasn't written any scores yet. Run the workflow above.</Alert>
      )}
      {entries.data && entries.data.length > 0 && (
        <DataTable
          testId="a-entries"
          caption="Node A's ledger entries"
          rows={entries.data}
          rowKey={e => e.entry_id}
          columns={[
            { header: 'Entry', cell: e => e.entry_id, className: 'whitespace-nowrap' },
            { header: 'Customer', cell: e => e.customer_token },
            { header: 'Score', cell: e => `${e.score} ${e.band}` },
            { header: 'Reasons', cell: e => e.reasons.join(', ') || '–' },
          ]}
        />
      )}
    </Section>
  );
}
