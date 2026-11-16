// Node D – Policy Agent. Same features as ui/pages/D.py:
//   1. Check an action  2. Deadlines (P1)  3. Recommendations  4. Decisions
//   5. Explain a decision or recommendation  6. Policy sweep (with / without the AI) + run log replay
// The rules are plain Python; the AI only runs the sweep's checklist and explains. Nothing here can
// approve a recommendation: that's a person's job on the Actions page.
import { Accordion, AccordionItem } from '@westpac/ui/accordion';
import { Alert } from '@westpac/ui/alert';
import { Button } from '@westpac/ui/button';
import { Field } from '@westpac/ui/field';
import { Input } from '@westpac/ui/input';
import { ProgressIndicator } from '@westpac/ui/progress-indicator';
import { Select } from '@westpac/ui/select';
import { FormEvent, useMemo, useState } from 'react';

import {
  CheckResult,
  DeadlineAlert,
  Decision,
  DecisionRow,
  Explanation,
  Integrity,
  RunLog,
  RunSummary,
  SweepResult,
  TrackedRec,
  errorText,
  post,
  useAction,
  useApi,
  useMeta,
} from '../api';
import {
  Caption,
  Code,
  DataTable,
  DecisionBadge,
  ErrorAlert,
  JsonView,
  LevelBadge,
  Loading,
  Metric,
  Metrics,
  PageTitle,
  Section,
  StatusBadge,
  when,
} from '../components';
import { DemoControlsFold } from '../DemoControls';

export function PolicyPage() {
  const meta = useMeta();
  const integrity = useApi<Integrity>('/api/ledger/integrity');
  const [explainPick, setExplainPick] = useState<string | null>(null);
  const count = integrity.data?.count;

  return (
    <>
      <PageTitle title="Customer Guardian" subtitle="Node D – Policy Agent">
        <strong>Gets data from:</strong> C (the ledger: scores, promises, booked calls) · <strong>Sends data to:</strong>{' '}
        E (recommendations for a person to approve) and C (every decision is recorded) · Demo time: {when(meta.data?.now)}
      </PageTitle>
      <DemoControlsFold />
      {integrity.error && <ErrorAlert error={integrity.error} />}
      {count === undefined ? (
        <Loading />
      ) : count === 0 ? (
        <Alert look="warning" heading="The ledger is empty">
          Use <strong>Load demo data</strong> in Demo controls (or run <Code>python scripts/load_fixtures.py</Code>).
        </Alert>
      ) : (
        <>
          <CheckAction onRecorded={setExplainPick} />
          <Deadlines />
          <Recommendations />
          <Decisions />
          <Explain pick={explainPick} setPick={setExplainPick} />
          <Sweep />
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// 1. Check an action
// ---------------------------------------------------------------------------
export function DecisionAlert({ decision }: { decision: Decision }) {
  const d = decision;
  if (d.decision === 'ALLOW') {
    return (
      <Alert look="success" heading={`ALLOW · ${d.action} for ${d.customer_token}`} data-testid="decision">
        {d.reason}
      </Alert>
    );
  }
  const flags = d.flags.length ? ` · ${d.flags.join(', ')}` : '';
  return (
    <Alert look="danger" heading={`BLOCK (${d.policy}) · ${d.action} for ${d.customer_token}${flags}`} data-testid="decision">
      {d.reason}
    </Alert>
  );
}

function CheckAction({ onRecorded }: { onRecorded: (entryId: string) => void }) {
  const meta = useMeta();
  const customers = useApi<string[]>('/api/ledger/customers');
  const tokens = customers.data ?? [];
  const hero = meta.data?.hero ?? 'cust_af4200';
  const actions = meta.data?.checkable ?? [];
  const staffList = meta.data?.staff ?? [];
  const [customer, setCustomer] = useState<string | null>(null);
  const [action, setAction] = useState<string | null>(null);
  const [staff, setStaff] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [result, setResult] = useState<CheckResult | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const check = useAction((body: object) => post<CheckResult>('/api/policy/check', body));

  const token = customer && tokens.includes(customer) ? customer : tokens.includes(hero) ? hero : tokens[0] ?? '';
  const chosenAction = action ?? actions[0] ?? '';
  const chosenStaff = staff ?? staffList[0] ?? '';

  const submit = (e: FormEvent) => {
    e.preventDefault();
    check.mutate(
      { customer_token: token, action: chosenAction, requested_by: chosenStaff, call_code: code || null },
      {
        onSuccess: r => {
          setResult(r);
          setProblem(null);
          onRecorded(r.entry_id); // section 5 jumps to the decision just made
        },
        onError: err => {
          setResult(null);
          setProblem(errorText(err));
        },
      },
    );
  };

  return (
    <Section
      title="1. Check an action"
      caption="Before the bank does something to a customer, it asks D. P2: no collections during an open hardship case · P3: a caller must quote the booked call code · P4: no credit offers to HIGH or CRITICAL customers. Every answer is recorded in the ledger."
    >
      <form onSubmit={submit} className="rounded-xl border border-border-muted-soft bg-background-white p-3" aria-label="Check an action">
        <div className="grid gap-2 md:grid-cols-3">
          <Field label="Customer">
            <Select value={token} onChange={e => setCustomer(e.target.value)} width="full">
              {tokens.map(t => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Action">
            <Select value={chosenAction} onChange={e => setAction(e.target.value)} width="full">
              {actions.map(a => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Requested by">
            <Select value={chosenStaff} onChange={e => setStaff(e.target.value)} width="full">
              {staffList.map(s => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Call code the caller quoted (only for VERIFY_CALLER)" className="mt-2 md:max-w-xs">
          <Input value={code} onChange={e => setCode(e.target.value)} maxLength={12} autoComplete="off" />
        </Field>
        <Button type="submit" look="primary" className="mt-2" disabled={check.isPending || !token}>
          Check with D
        </Button>
      </form>
      <div className="mt-2" aria-live="polite">
        {problem && <Alert look="warning">Can't check that: {problem}</Alert>}
        {result && (
          <>
            <DecisionAlert decision={result.decision} />
            <Caption>Recorded in the ledger as {result.entry_id}. Explain it in section 5.</Caption>
          </>
        )}
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------------------
// 2. Deadlines, 3. Recommendations, 4. Decisions
// ---------------------------------------------------------------------------
function Deadlines() {
  const alerts = useApi<DeadlineAlert[]>('/api/policy/deadlines');
  return (
    <Section title="2. Deadlines (P1)" caption="Open promises that are overdue (escalate) or due within 24 hours (alert). Read-only.">
      {alerts.error && <ErrorAlert error={alerts.error} />}
      {alerts.data && alerts.data.length === 0 && (
        <Alert look="success">No promises are overdue or due within 24 hours.</Alert>
      )}
      {alerts.data && alerts.data.length > 0 && (
        <DataTable
          caption="Deadlines"
          rows={alerts.data}
          rowKey={a => a.promise_id}
          columns={[
            { header: 'Level', cell: a => <LevelBadge level={a.level} /> },
            { header: 'Customer', cell: a => a.customer_token },
            { header: 'Promise', cell: a => `${a.promise_id} ${a.promise_type}` },
            { header: 'Due', cell: a => when(a.due), className: 'whitespace-nowrap' },
            { header: 'Hours to due', cell: a => a.hours_to_due },
            { header: 'Reason', cell: a => a.reason },
          ]}
        />
      )}
    </Section>
  );
}

function Recommendations() {
  const recs = useApi<TrackedRec[]>('/api/policy/recommendations');
  return (
    <Section
      title="3. Recommendations"
      caption="What D has suggested. Nothing reaches a customer until a person approves it on the Actions page. Run the policy sweep (section 6) to create new ones."
    >
      {recs.error && <ErrorAlert error={recs.error} />}
      {recs.data && recs.data.length === 0 && <Alert look="info">No recommendations yet. Run the policy sweep in section 6.</Alert>}
      {recs.data && recs.data.length > 0 && (
        <DataTable
          testId="recommendations"
          caption="Recommendations"
          rows={recs.data}
          rowKey={r => r.rec_id}
          columns={[
            { header: 'Rec', cell: r => r.rec_id, className: 'whitespace-nowrap' },
            { header: 'Customer', cell: r => r.customer_token },
            { header: 'Recommendation', cell: r => r.recommendation },
            { header: 'Why', cell: r => r.why.join(', ') },
            { header: 'Status', cell: r => <StatusBadge status={r.status} /> },
            { header: 'Decided by', cell: r => r.decided_by ?? '' },
            { header: 'Made', cell: r => when(r.recorded_at), className: 'whitespace-nowrap' },
          ]}
        />
      )}
    </Section>
  );
}

function Decisions() {
  const rows = useApi<DecisionRow[]>('/api/policy/decisions');
  return (
    <Section title="4. Decisions">
      {rows.error && <ErrorAlert error={rows.error} />}
      {rows.data && rows.data.length === 0 && <Alert look="info">No decisions yet. Check an action in section 1.</Alert>}
      {rows.data && rows.data.length > 0 && (
        <DataTable
          testId="decisions"
          caption="Decisions"
          rows={rows.data}
          rowKey={d => d.entry_id}
          columns={[
            { header: 'Entry', cell: d => d.entry_id, className: 'whitespace-nowrap' },
            { header: 'Time', cell: d => when(d.created_at), className: 'whitespace-nowrap' },
            { header: 'Customer', cell: d => d.customer_token },
            { header: 'Action', cell: d => d.action },
            { header: 'Decision', cell: d => <DecisionBadge decision={d.decision} policy={d.policy} /> },
            { header: 'Reason', cell: d => d.reason },
          ]}
        />
      )}
    </Section>
  );
}

// ---------------------------------------------------------------------------
// 5. Explain
// ---------------------------------------------------------------------------
function Explain({ pick, setPick }: { pick: string | null; setPick: (id: string) => void }) {
  const recs = useApi<TrackedRec[]>('/api/policy/recommendations');
  const decisions = useApi<DecisionRow[]>('/api/policy/decisions');
  const options = useMemo(() => {
    const labels = [
      ...(recs.data ?? []).map(r => ({ id: r.entry_id, label: `${r.entry_id} · ${r.customer_token} · recommend ${r.recommendation}` })),
      ...(decisions.data ?? []).map(d => ({ id: d.entry_id, label: `${d.entry_id} · ${d.customer_token} · ${d.action} → ${d.decision}` })),
    ];
    return labels.sort((a, b) => Number(b.id.slice(2)) - Number(a.id.slice(2))); // newest first
  }, [recs.data, decisions.data]);
  const chosen = pick && options.some(o => o.id === pick) ? pick : options[0]?.id ?? null;
  const facts = useApi<Explanation>(chosen ? `/api/policy/explain/${chosen}` : null);
  const [words, setWords] = useState<{ id: string; text: string; look: 'info' | 'warning' } | null>(null);
  const ask = useAction((id: string) => post<{ text: string }>(`/api/policy/explain/${id}/words`));

  return (
    <Section title="5. Explain a decision or recommendation">
      {options.length === 0 ? (
        <Alert look="info">Nothing to explain yet: check an action or run the policy sweep.</Alert>
      ) : (
        <>
          <Field label="Pick one" className="mb-2 md:max-w-md">
            <Select value={chosen ?? ''} onChange={e => setPick(e.target.value)} width="full" data-testid="explain-pick">
              {options.map(o => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </Select>
          </Field>
          {facts.error && <ErrorAlert error={facts.error} />}
          {facts.data && facts.data.entry_id === chosen && (
            <>
              <p className="mb-2 typography-body-9">
                <strong>Rule:</strong> {facts.data.rule}
              </p>
              <Metrics>
                <Metric
                  label="Combined score at the time"
                  value={facts.data.facts.combined_score !== null ? `${facts.data.facts.combined_score} ${facts.data.facts.band}` : '–'}
                />
                <Metric
                  label="Open hardship case"
                  value={facts.data.facts.open_hardship_case ? `due ${facts.data.facts.open_hardship_case.due.slice(0, 10)}` : 'no'}
                />
                <Metric label="Overdue promises" value={facts.data.facts.overdue_promises.length} />
                <Metric label="Calls booked" value={facts.data.facts.calls_booked} />
              </Metrics>
              <Button
                look="hero"
                soft
                className="mt-2"
                disabled={ask.isPending}
                onClick={() =>
                  ask.mutate(chosen!, {
                    onSuccess: r => setWords({ id: chosen!, text: r.text, look: 'info' }),
                    onError: err => setWords({ id: chosen!, text: errorText(err), look: 'warning' }),
                  })
                }
              >
                {ask.isPending ? 'Asking the AI to explain the facts…' : 'Explain in plain English (AI)'}
              </Button>
              {words && words.id === chosen && (
                <Alert look={words.look} className="mt-2">
                  {words.text}
                </Alert>
              )}
              <div className="mt-2">
                <Accordion>
                  <AccordionItem key="facts" id="facts" title="All facts and the ledger entries it relied on (call codes hidden)">
                    <JsonView value={facts.data} label="Explanation facts" />
                  </AccordionItem>
                </Accordion>
              </div>
            </>
          )}
        </>
      )}
    </Section>
  );
}

// ---------------------------------------------------------------------------
// 6. Policy sweep
// ---------------------------------------------------------------------------
function Sweep() {
  const runs = useApi<RunSummary[]>('/api/policy/runs');
  const [chosen, setChosen] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const sweep = useAction((ai: boolean) => post<SweepResult>(`/api/policy/sweep?ai=${ai}`));
  const names = runs.data?.map(r => r.run_id) ?? [];
  const runId = chosen && names.includes(chosen) ? chosen : names[0] ?? null;
  const log = useApi<RunLog>(runId ? `/api/policy/runs/${runId}` : null);

  const run = (ai: boolean) =>
    sweep.mutate(ai, {
      onSuccess: r => {
        setChosen(r.run_id);
        setFailure(null);
      },
      onError: err => setFailure(errorText(err)),
    });

  return (
    <Section
      title="6. Policy sweep"
      caption={
        <>
          Runs <Code>runbooks/policy_sweep.md</Code>: verify the ledger (stops if tampered) → deadlines → Quiet Help list
          → create recommendations. With the AI, it follows the checklist and writes a summary; without it, the same
          steps run directly. Both leave the ledger identical.
        </>
      }
    >
      <div className="grid gap-2 md:grid-cols-2">
        <Button look="hero" soft block disabled={sweep.isPending} onClick={() => run(true)}>
          Run sweep with the AI
        </Button>
        <Button look="primary" block disabled={sweep.isPending} onClick={() => run(false)}>
          Run sweep without the AI
        </Button>
      </div>
      {sweep.isPending && (
        <div className="mt-2 flex items-center gap-2" role="status">
          <ProgressIndicator size="medium" label="Running the policy sweep" />
          <span className="typography-body-10 text-text-muted">Running the policy sweep…</span>
        </div>
      )}
      {failure && (
        <Alert look="danger" className="mt-2">
          {failure}
        </Alert>
      )}
      <div className="mt-3">
        {names.length === 0 ? (
          <Alert look="info">No sweeps have run yet.</Alert>
        ) : (
          <>
            <Field label="Run log" className="mb-2 md:max-w-md">
              <Select value={runId ?? ''} onChange={e => setChosen(e.target.value)} width="full" data-testid="run-pick">
                {names.map(n => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </Select>
            </Field>
            {log.data && log.data.run_id === runId && <RunReplay log={log.data} />}
          </>
        )}
      </div>
    </Section>
  );
}

function RunReplay({ log }: { log: RunLog }) {
  const steps = log.events.filter(e => e.event === 'step');
  return (
    <div data-testid="run-log">
      <Alert look={log.status === 'COMPLETED' ? 'success' : 'danger'} heading={log.status}>
        {log.run_id}
      </Alert>
      {steps.length > 0 && (
        <Accordion key={log.run_id} className="mt-2">
          {steps.map(e => (
            <AccordionItem key={`s${e.n}`} id={`s${e.n}`} title={`${e.ok ? '✔' : '✘'} Step ${e.n}: ${e.tool}`}>
              <JsonView value={e.output} label={`Output of step ${e.n}`} />
            </AccordionItem>
          ))}
        </Accordion>
      )}
      {log.events
        .filter(e => e.event === 'off_script' || e.event === 'stopped')
        .map((e, i) => (
          <Alert key={i} look="danger" className="mt-2">
            {e.event === 'off_script'
              ? `OFF SCRIPT at step ${e.step}: the AI called ${e.called}, the runbook says ${e.expected}`
              : `Stopped at step ${e.step} (${e.rule})`}
          </Alert>
        ))}
      {log.summary && (
        <div className="mt-2">
          <p className="typography-body-9 font-bold">Summary</p>
          <Alert look="info" data-testid="run-summary">
            <span className="whitespace-pre-line">{log.summary}</span>
          </Alert>
        </div>
      )}
      {log.error && log.status !== 'STOPPED' && <Caption>{log.error}</Caption>}
    </div>
  );
}
