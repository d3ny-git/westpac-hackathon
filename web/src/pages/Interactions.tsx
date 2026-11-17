// Node B – Interactions with the mock input form (B5). Same features as ui/pages/B.py:
//   1. Run Node B for all customers (with / without the AI) and the results
//   2. The mock input form: type an interaction as it would really reach the bank, fake personal
//      information included; or fill in hero's hardship form (SPEC step 6) / steady_bnpl's chat
//   3. On submit: what the sanitizer KEPT vs THREW AWAY, the flags, then Node B's workflow run
//   4. That customer now: combined score, B's score, open case, promises
//   5. All clean interactions (tokens and flags only) and Node B's ledger entries
// The raw panels are a LOCAL view (docs/MCP_PLAN.md §6): raw data never goes through MCP or the AI,
// and only the sanitized row is ever stored.
import { Alert } from '@westpac/ui/alert';
import { Button } from '@westpac/ui/button';
import { Field } from '@westpac/ui/field';
import { Input } from '@westpac/ui/input';
import { ProgressIndicator } from '@westpac/ui/progress-indicator';
import { Select } from '@westpac/ui/select';
import { Switch } from '@westpac/ui/switch';
import { Textarea } from '@westpac/ui/textarea';
import { FormEvent, useEffect, useState } from 'react';

import {
  FormOptions,
  InteractionOverview,
  RawSubmission,
  RunAllResult,
  SubmitResult,
  errorText,
  post,
  useAction,
  useApi,
  useMeta,
} from '../api';
import {
  Caption,
  Code,
  CodeBadge,
  DataTable,
  ErrorAlert,
  FieldTable,
  Loading,
  Metric,
  PageTitle,
  RunView,
  Section,
  stamp,
  when,
} from '../components';
import { DemoControlsFold } from '../DemoControls';

const SELF_SERVICE = '';

type Form = {
  customer_id: string;
  staff_id: string;
  date: string;
  channel: string;
  type: string;
  form_status: string;
  callback_day: string;
  callback_time: string;
  text: string;
  ai: boolean;
};

export function InteractionsPage() {
  const meta = useMeta();
  const overview = useApi<InteractionOverview>('/api/interaction/overview');
  const o = overview.data;
  return (
    <>
      <PageTitle title="Customer Guardian" subtitle="Node B – Interactions">
        <strong>Gets data from:</strong> customers' calls, chats, emails and forms (sanitized first: no personal
        information) · <strong>Sends data to:</strong> C (an interaction hardship SCORE and the PROMISES the bank made)
        · Demo time: {when(meta.data?.now)}
      </PageTitle>
      <DemoControlsFold />
      {overview.error && <ErrorAlert error={overview.error} />}
      {!o ? (
        <Loading />
      ) : !o.clean_ready ? (
        <Alert look="warning" heading="There's no clean interaction data yet">
          Use <strong>Reset demo (real pipeline)</strong> in Demo controls (or run <Code>python scripts/reset_demo.py</Code>).
        </Alert>
      ) : (
        <>
          <RunForEveryone />
          <MockInputForm />
          <CleanData overview={o} />
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// 1. Run Node B for everyone
// ---------------------------------------------------------------------------
function RunForEveryone() {
  const [result, setResult] = useState<RunAllResult | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const run = useAction((ai: boolean) => post<RunAllResult>(`/api/interaction/run-all?ai=${ai}`));
  const go = (ai: boolean) =>
    run.mutate(ai, {
      onSuccess: r => {
        setResult(r);
        setFailure(null);
      },
      onError: err => {
        setResult(null);
        setFailure(errorText(err));
      },
    });
  return (
    <Section
      title="1. Run Node B for all customers"
      caption={
        <>
          Runs <Code>runbooks/b_interaction.md</Code> once per customer in the interaction history: each customer's
          interaction score and the promises the bank made, written to the ledger. Anything already there is skipped,
          so running it twice adds nothing.
        </>
      }
    >
      <div className="grid gap-2 md:grid-cols-2">
        <Button look="hero" soft block disabled={run.isPending} onClick={() => go(true)}>
          Run for all customers with the AI
        </Button>
        <Button look="primary" block disabled={run.isPending} onClick={() => go(false)}>
          Run for all customers without the AI
        </Button>
      </div>
      {run.isPending && (
        <div className="mt-2 flex items-center gap-2" role="status">
          <ProgressIndicator size="medium" label="Running Node B for every customer" />
          <span className="typography-body-10 text-text-muted">Running Node B's workflow for every customer…</span>
        </div>
      )}
      {failure && (
        <Alert look="danger" className="mt-2">
          {failure}
        </Alert>
      )}
      {result && (
        <div className="mt-2" data-testid="b-everyone">
          <Alert look="success">Node B ran for {result.customers} customers.</Alert>
          <DataTable
            caption="Node B for every customer"
            rows={result.rows}
            rowKey={r => r.customer_token}
            columns={[
              { header: 'Customer', cell: r => r.customer_token },
              { header: 'Status', cell: r => r.status },
              { header: 'Score', cell: r => r.score },
              { header: 'Score written', cell: r => (r.score_written ? 'yes' : 'unchanged') },
              { header: 'Promises written', cell: r => r.promises_written.join(', ') || '–' },
            ]}
          />
        </div>
      )}
    </Section>
  );
}

// ---------------------------------------------------------------------------
// 2-4. The mock input form, what it kept and threw away, the run, the customer now
// ---------------------------------------------------------------------------
function fromExample(example: RawSubmission, base: Form): Form {
  return {
    ...base,
    customer_id: example.customer_id,
    staff_id: example.staff_id || SELF_SERVICE,
    date: example.date,
    channel: example.channel,
    type: example.type,
    form_status: example.form_status || 'SUBMITTED',
    text: example.text,
  };
}

function MockInputForm() {
  const options = useApi<FormOptions>('/api/interaction/form-options', { refetch: false });
  const o = options.data;
  const [form, setForm] = useState<Form | null>(null);
  const [result, setResult] = useState<SubmitResult | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const submit = useAction((body: object) => post<SubmitResult>('/api/interaction/submit', body));

  useEffect(() => {
    if (o && !form) {
      setForm({
        customer_id: o.customers[0]?.customer_id ?? '',
        staff_id: SELF_SERVICE,
        date: o.defaults.date,
        channel: o.channels[0],
        type: o.types[0],
        form_status: 'SUBMITTED',
        callback_day: o.defaults.callback_day,
        callback_time: o.defaults.callback_time,
        text: '',
        ai: false,
      });
    }
  }, [o, form]);

  if (options.error) return <ErrorAlert error={options.error} />;
  if (!o || !form) return <Loading />;
  const set = (patch: Partial<Form>) => setForm({ ...form, ...patch });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setFailure(null);
    submit.mutate(
      {
        customer_id: form.customer_id,
        staff_id: form.staff_id,
        date: form.date,
        channel: form.channel,
        type: form.type,
        form_status: form.type === 'HARDSHIP_FORM' ? form.form_status : '',
        callback_due: form.type === 'CALLBACK_REQUEST' ? `${form.callback_day}T${form.callback_time}:00` : '',
        text: form.text,
        ai: form.ai,
      },
      {
        onSuccess: r => setResult(r),
        onError: err => {
          setResult(null);
          setFailure(errorText(err));
        },
      },
    );
  };

  return (
    <>
      <Section
        title="2. Mock input form"
        caption="Type an interaction as it would really reach the bank, personal details and all. Only the sanitized version ever reaches Node B, the ledger or the AI."
      >
        <div className="mb-3 grid gap-2 md:grid-cols-2">
          <Button look="faint" soft block onClick={() => setForm(fromExample(o.examples[0], form))}>
            Fill in: hero's hardship form (SPEC step 6)
          </Button>
          <Button look="faint" soft block onClick={() => setForm(fromExample(o.examples[1], form))}>
            Fill in: steady_bnpl's chat
          </Button>
        </div>
        <form
          onSubmit={onSubmit}
          aria-label="Mock input form"
          className="rounded-xl border border-border-muted-soft bg-background-white p-3"
        >
          <div className="grid gap-2 md:grid-cols-3">
            <Field label="Customer">
              <Select value={form.customer_id} onChange={e => set({ customer_id: e.target.value })} width="full">
                {o.customers.map(c => (
                  <option key={c.customer_id} value={c.customer_id}>
                    {c.full_name} ({c.customer_id})
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Handled by">
              <Select value={form.staff_id} onChange={e => set({ staff_id: e.target.value })} width="full">
                <option value={SELF_SERVICE}>— self-service (no staff member)</option>
                {o.staff.map(s => (
                  <option key={s.staff_id} value={s.staff_id}>
                    {s.staff_name} ({s.staff_id})
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Date">
              <Input type="date" value={form.date} onChange={e => set({ date: e.target.value })} />
            </Field>
            <Field label="Channel">
              <Select value={form.channel} onChange={e => set({ channel: e.target.value })} width="full">
                {o.channels.map(c => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Type">
              <Select value={form.type} onChange={e => set({ type: e.target.value })} width="full">
                {o.types.map(t => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </Select>
            </Field>
            {form.type === 'HARDSHIP_FORM' && (
              <Field label="Form status">
                <Select value={form.form_status} onChange={e => set({ form_status: e.target.value })} width="full">
                  {o.form_statuses.map(s => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
            {form.type === 'CALLBACK_REQUEST' && (
              <div className="grid grid-cols-2 gap-2">
                <Field label="Call back on">
                  <Input type="date" value={form.callback_day} onChange={e => set({ callback_day: e.target.value })} />
                </Field>
                <Field label="Call back at">
                  <Input type="time" value={form.callback_time} onChange={e => set({ callback_time: e.target.value })} />
                </Field>
              </div>
            )}
          </div>
          <Field label="What the customer said / wrote" className="mt-2">
            <Textarea
              value={form.text}
              onChange={e => set({ text: e.target.value })}
              rows={4}
              maxLength={2000}
              placeholder="e.g. Hi, it's Jane Citizen. I lost my job and can't afford my repayments..."
            />
          </Field>
          <div className="mt-2">
            <Switch
              label="Run Node B's workflow with the AI (slower; needs the .env key)"
              isSelected={form.ai}
              onChange={ai => set({ ai })}
            />
          </div>
          <Button type="submit" look="primary" className="mt-2" disabled={submit.isPending}>
            Submit to Node B
          </Button>
          {submit.isPending && (
            <div className="mt-2 flex items-center gap-2" role="status">
              <ProgressIndicator size="medium" label="Running Node B's workflow" />
              <span className="typography-body-10 text-text-muted">Running Node B's workflow…</span>
            </div>
          )}
        </form>
        {failure && (
          <Alert look="warning" className="mt-2">
            Can't submit that: {failure}
          </Alert>
        )}
      </Section>
      {result && <Submitted result={result} />}
    </>
  );
}

function Submitted({ result }: { result: SubmitResult }) {
  const { clean, thrown_away, run, customer } = result;
  const s = customer.score;
  return (
    <>
      <Section title="3. What the sanitizer kept and threw away">
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <p className="mb-1 typography-body-9 font-bold">Kept (all Node B ever sees)</p>
            <FieldTable row={clean} caption="Kept" testId="kept" />
          </div>
          <div>
            <p className="mb-1 typography-body-9 font-bold">Thrown away (local view only)</p>
            <FieldTable row={thrown_away} caption="Thrown away" testId="thrown-away" />
            <Caption>
              The text became the flags <Code>{result.flags || 'none'}</Code> and was deleted.
            </Caption>
          </div>
        </div>
        <p className="mt-3 mb-1 typography-body-9 font-bold">Node B's workflow</p>
        <RunView run={run} title={`b_interaction for ${clean.customer_token}`} testId="b-run" />
      </Section>
      <Section title={`4. ${customer.customer_token} now`}>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3" data-testid="customer-now">
          <Metric label="Combined score" value={s ? `${s.score} ${s.band}` : 'not scored'} testId="b-combined" />
          <Metric label="Interaction score (B)" value={s?.interaction_score ?? '–'} />
          <Metric label="Open hardship case" value={customer.open_case ? 'yes' : 'no'} testId="b-open-case" />
        </div>
        <div className="mt-2">
          {customer.promises.length === 0 ? (
            <Caption>No promises for this customer.</Caption>
          ) : (
            <DataTable
              testId="b-promises"
              caption={`Promises to ${customer.customer_token}`}
              rows={customer.promises}
              rowKey={p => `${p.promise_type}-${p.due}`}
              columns={[
                { header: 'Promise', cell: p => p.promise_id ?? 'not published' },
                { header: 'Type', cell: p => p.promise_type },
                { header: 'Due', cell: p => stamp(p.due), className: 'whitespace-nowrap' },
                { header: 'Made by', cell: p => p.made_by },
                { header: 'Description', cell: p => p.description },
              ]}
            />
          )}
        </div>
      </Section>
    </>
  );
}

// ---------------------------------------------------------------------------
// 5. Clean data and B's ledger entries
// ---------------------------------------------------------------------------
function CleanData({ overview }: { overview: InteractionOverview }) {
  const rows = overview.clean_rows;
  const columns = rows.length ? Object.keys(rows[0]) : [];
  return (
    <Section
      title="5. Clean interaction data and Node B's ledger entries"
      caption={
        <>
          <Code>data/clean/interactions.csv</Code>: {rows.length} interactions, tokens and keyword flags only (no names,
          contact details or text).
        </>
      }
    >
      {rows.length > 0 && (
        <DataTable
          testId="clean-interactions"
          caption="Clean interactions"
          rows={rows.map((r, i) => ({ ...r, _i: String(i) }))}
          rowKey={r => r._i}
          columns={columns.map(c => ({ header: c, cell: (r: Record<string, string>) => r[c] }))}
        />
      )}
      <div className="mt-3">
        {overview.entries.length === 0 ? (
          <Alert look="info">Node B hasn't written anything yet. Run Node B for all customers above.</Alert>
        ) : (
          <DataTable
            testId="b-entries"
            caption="Node B's ledger entries"
            rows={overview.entries}
            rowKey={e => e.entry_id}
            columns={[
              { header: 'Entry', cell: e => e.entry_id, className: 'whitespace-nowrap' },
              { header: 'Customer', cell: e => e.customer_token },
              { header: 'Type', cell: e => <CodeBadge color={e.entry_type === 'SCORE' ? 'info' : 'hero'}>{e.entry_type}</CodeBadge> },
              { header: 'What', cell: e => e.what },
            ]}
          />
        )}
      </div>
    </Section>
  );
}
