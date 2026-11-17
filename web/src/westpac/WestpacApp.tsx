// The Westpac dashboard (/westpac/): what the hardship team needs to operate Customer Guardian.
//   Overview (integrity, the automatic sweeps and their AI summary, P1 alerts, Risk Dashboard,
//   Quiet Help) · New contacts (with the AI hardship assessment) · Approvals (explain + approve /
//   reject; carried out automatically) · Check an action · Customers · Audit
// Tokens only. Nothing that only exists to explain the system (no raw data, run buttons, rules,
// story guide, demo controls, tamper or fixtures): the sweeps run by themselves (`app.py --live`).
import { Accordion, AccordionItem } from '@westpac/ui/accordion';
import { Alert } from '@westpac/ui/alert';
import { Badge } from '@westpac/ui/badge';
import { Button } from '@westpac/ui/button';
import { Field } from '@westpac/ui/field';
import { Footer } from '@westpac/ui/footer';
import { Header } from '@westpac/ui/header';
import { Heading } from '@westpac/ui/heading';
import { Input } from '@westpac/ui/input';
import { Panel, PanelBody } from '@westpac/ui/panel';
import { ProgressIndicator } from '@westpac/ui/progress-indicator';
import { Select } from '@westpac/ui/select';
import { Tabs, TabsPanel } from '@westpac/ui/tabs';
import { FormEvent, ReactNode, useState } from 'react';

import {
  CustomerLookup,
  DashboardRow,
  DeadlineAlert,
  DecisionRow,
  Entries,
  Explanation,
  Integrity,
  QuietHelpCandidate,
  TrackedRec,
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
  DecisionBadge,
  ErrorAlert,
  JsonView,
  LevelBadge,
  Loading,
  Metric,
  Metrics,
  QuietHelpMessageBadge,
  quietHelpReason,
  StatusBadge,
  UrgencyBadge,
  stamp,
  titleCase,
  when,
} from '../components';
import { DecisionAlert } from '../pages/Policy';
import { useRemembered } from '../live/shared';
import {
  ActionDone,
  Intake,
  LiveStatus,
  ScamAlert,
  WestpacCheck,
} from '../live/types';

export function WestpacApp() {
  const [staff, setStaff] = useRemembered('guardian.staff');
  return (
    <div className="flex min-h-screen flex-col bg-background-pale">
      <Header brand="wbc" logoLink="#" logoAssistiveText="Customer Guardian staff dashboard" skipToContentId="#main">
        <span className="flex items-center gap-2 typography-body-10 text-text-muted">
          Customer Guardian · hardship team
          {staff && (
            <>
              <Badge color="hero" soft tag="span" data-testid="signed-in-staff">
                {staff}
              </Badge>
              <Button look="link" size="small" onClick={() => setStaff(null)}>
                Sign out
              </Button>
            </>
          )}
        </span>
      </Header>
      <main id="main" className="mx-auto w-full max-w-lg flex-1 px-2 py-4 sm:px-3">
        {!staff ? <StaffSignIn onSignIn={setStaff} /> : <Dashboard staff={staff} />}
      </main>
      <Footer brand="wbc" logoAssistiveText="Westpac">
        <p className="typography-body-10">
          Customer Guardian staff dashboard · demo · customers are tokens only: no personal information here
        </p>
      </Footer>
    </div>
  );
}

function StaffSignIn({ onSignIn }: { onSignIn: (staff: string) => void }) {
  const staff = useApi<string[]>('/api/westpac/staff', { refetch: false });
  const [pick, setPick] = useState('');
  const chosen = pick || staff.data?.[1] || staff.data?.[0] || '';
  return (
    <div className="mx-auto max-w-xs">
      <Panel heading="Staff sign-in" headingTag="h1">
        <PanelBody>
          <Alert look="info" className="mb-3">
            Demo sign-in: pick a staff token. It's used for approvals and policy checks.
          </Alert>
          <form
            aria-label="Staff sign-in"
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              if (chosen) onSignIn(chosen);
            }}
          >
            <Field label="Staff member">
              <Select value={chosen} onChange={e => setPick(e.target.value)} width="full" data-testid="sign-in-staff">
                {(staff.data ?? []).map(s => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Select>
            </Field>
            <Button type="submit" look="primary" block className="mt-3" disabled={!chosen}>
              Sign in
            </Button>
          </form>
        </PanelBody>
      </Panel>
    </div>
  );
}

function Dashboard({ staff }: { staff: string }) {
  const recs = useApi<TrackedRec[]>('/api/policy/recommendations');
  const intakes = useApi<Intake[]>('/api/live/intake');
  const waiting = (recs.data ?? []).filter(r => r.status === 'AWAITING_APPROVAL').length;
  return (
    <>
      <LiveBar />
      <Tabs aria-label="Dashboard">
        <TabsPanel key="overview" title="Overview">
          <TabBody>
            <Overview />
          </TabBody>
        </TabsPanel>
        <TabsPanel key="contacts" title={`New contacts${intakes.data?.length ? ` (${intakes.data.length})` : ''}`}>
          <TabBody>
            <NewContacts intakes={intakes.data} />
          </TabBody>
        </TabsPanel>
        <TabsPanel key="approvals" title={`Approvals${waiting ? ` (${waiting})` : ''}`}>
          <TabBody>
            <Approvals staff={staff} recs={recs.data} />
          </TabBody>
        </TabsPanel>
        <TabsPanel key="check" title="Check an action">
          <TabBody>
            <CheckAction staff={staff} />
          </TabBody>
        </TabsPanel>
        <TabsPanel key="customers" title="Customers">
          <TabBody>
            <Customers />
          </TabBody>
        </TabsPanel>
        <TabsPanel key="audit" title="Audit">
          <TabBody>
            <Audit />
          </TabBody>
        </TabsPanel>
      </Tabs>
    </>
  );
}

const TabBody = ({ children }: { children: ReactNode }) => <div className="pt-3">{children}</div>;

function H({ children, caption }: { children: ReactNode; caption?: ReactNode }) {
  return (
    <div className="mt-4 mb-2 first:mt-0">
      <Heading size={7} tag="h2">
        {children}
      </Heading>
      {caption && <Caption>{caption}</Caption>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// The live bar: are the automatic sweeps on, and what are they doing?
// ---------------------------------------------------------------------------
function LiveBar() {
  const status = useApi<LiveStatus>('/api/live/status');
  const s = status.data;
  if (!s) return null;
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-border-muted-soft bg-background-white p-2" data-testid="live-bar">
      {s.enabled ? (
        <CodeBadge color="success">Automatic sweeps on</CodeBadge>
      ) : (
        <CodeBadge color="warning">Automatic sweeps off (start with python app.py --live)</CodeBadge>
      )}
      <CodeBadge color={s.ai ? 'info' : 'muted'}>{s.ai ? 'AI on' : 'AI off'}</CodeBadge>
      {s.busy ? (
        <span className="flex items-center gap-1 typography-body-10 text-text-muted">
          <ProgressIndicator size="xsmall" label="Working" /> {s.busy}…
        </span>
      ) : (
        <span className="typography-body-10 text-text-muted">
          {s.cycles} sweep{s.cycles === 1 ? '' : 's'} so far
          {s.enabled && s.next_check_in_seconds !== null ? ` · next check in ${s.next_check_in_seconds}s (runs only if something changed)` : ''}
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------
function Overview() {
  const integrity = useApi<Integrity>('/api/ledger/integrity');
  const status = useApi<LiveStatus>('/api/live/status');
  const deadlines = useApi<DeadlineAlert[]>('/api/policy/deadlines');
  const risk = useApi<DashboardRow[]>('/api/ledger/dashboard');
  const quiet = useApi<QuietHelpCandidate[]>('/api/ledger/quiet-help');
  const scams = useApi<ScamAlert[]>('/api/westpac/scam-alerts');
  const r = integrity.data?.report;
  const cycle = status.data?.last_cycle;
  return (
    <>
      {scams.data && scams.data.length > 0 && (
        <div className="mb-3 flex flex-col gap-2" data-testid="scam-alerts">
          {scams.data.slice(0, 3).map(a => (
            <Alert key={a.entry_id} look="danger" heading={`Possible scam call · ${a.customer_token}`}>
              Someone said they were calling from Westpac but couldn't give this customer's call code, so they were
              told to hang up ({stamp(a.created_at)}, policy P3, {a.entry_id}). Check the customer is safe.
            </Alert>
          ))}
          {scams.data.length > 3 && <Caption>{scams.data.length - 3} earlier scam-call alerts in the Audit tab.</Caption>}
        </div>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        <div data-testid="integrity">
          {r &&
            (r.valid ? (
              <Alert look="success" heading="Ledger verified">
                {r.entries_checked} entries, nothing changed, removed or inserted.
              </Alert>
            ) : (
              <Alert look="danger" heading="LEDGER TAMPERED">
                {r.problem} at <strong>{r.first_bad_entry}</strong>. Sweeps and every action (checks, approvals, carrying
                out) are paused until this is investigated.
              </Alert>
            ))}
        </div>
        <div data-testid="sweep-status">
          {!cycle ? (
            <Alert look="info" heading="No automatic sweep yet">
              {status.data?.enabled ? 'The first one runs within seconds.' : 'Start the app with python app.py --live.'}
            </Alert>
          ) : cycle.error ? (
            <Alert look="danger" heading={`Sweep ${cycle.n}: error`}>
              {cycle.error}
            </Alert>
          ) : (
            <Alert
              look={cycle.sweep?.status === 'COMPLETED' ? 'success' : 'danger'}
              heading={`Last sweep (#${cycle.n}): ${cycle.sweep?.status ?? 'unknown'}`}
            >
              <span className="block typography-body-10">
                Triggered by {cycle.trigger === 'change' ? 'a change (submission or approval)' : cycle.trigger}
                {cycle.finished ? ` · finished ${cycle.finished.slice(11, 19)}` : ''} · scoring {cycle.scoring?.status} ·{' '}
                {cycle.sweep?.ai_used ? 'with the AI' : `without the AI${cycle.sweep?.ai_note ? ` (${cycle.sweep.ai_note})` : ''}`} ·{' '}
                {cycle.paused
                  ? 'actions paused: the ledger did not verify'
                  : `${cycle.executed?.length ?? 0} approved action${cycle.executed?.length === 1 ? '' : 's'} carried out`}
              </span>
            </Alert>
          )}
        </div>
      </div>
      {cycle?.sweep?.summary && (
        <Panel heading={cycle.sweep.ai_used ? 'Sweep summary (AI)' : 'Sweep summary'} headingTag="h2" className="mt-3">
          <PanelBody>
            <p className="whitespace-pre-line typography-body-9" data-testid="sweep-summary">
              {cycle.sweep.summary}
            </p>
          </PanelBody>
        </Panel>
      )}

      <H caption="Promises that are overdue (escalate) or due within 24 hours (alert).">Deadline alerts (P1)</H>
      {deadlines.data && deadlines.data.length === 0 && <Alert look="success">No promises are overdue or due within 24 hours.</Alert>}
      {deadlines.data && deadlines.data.length > 0 && (
        <DataTable
          testId="deadlines"
          caption="Deadline alerts"
          rows={deadlines.data}
          rowKey={a => a.promise_id}
          columns={[
            { header: 'Level', cell: a => <LevelBadge level={a.level} /> },
            { header: 'Customer', cell: a => a.customer_token },
            { header: 'Promise', cell: a => `${a.promise_id} ${a.promise_type}` },
            { header: 'Due', cell: a => when(a.due), className: 'whitespace-nowrap' },
            { header: 'Reason', cell: a => a.reason },
          ]}
        />
      )}

      <H caption="Every promise not kept yet, most at-risk customers first, then soonest due.">Risk Dashboard</H>
      {risk.data && (
        <DataTable
          testId="risk-dashboard"
          caption="Risk Dashboard"
          rows={risk.data}
          rowKey={x => x.promise_id}
          columns={[
            { header: 'Urgency', cell: x => <UrgencyBadge urgency={x.urgency} /> },
            { header: 'Customer', cell: x => x.customer_token },
            { header: 'Score', cell: x => `${x.score} ${x.band}` },
            { header: 'Promise', cell: x => `${x.promise_id} ${x.promise_type}` },
            { header: 'Due', cell: x => stamp(x.due), className: 'whitespace-nowrap' },
            { header: 'Hours to due', cell: x => x.hours_to_due },
          ]}
        />
      )}

      <H caption="HIGH or CRITICAL, no open hardship case, no Quiet Help message in 30 days. The sweep recommends a push; a person approves it.">
        Quiet Help list
      </H>
      {quiet.data && quiet.data.length === 0 && <Alert look="info">Nobody needs a Quiet Help nudge right now.</Alert>}
      {quiet.data && quiet.data.length > 0 && (
        <DataTable
          testId="quiet-help"
          caption="Quiet Help list"
          rows={quiet.data}
          rowKey={c => c.customer_token}
          columns={[
            { header: 'Customer', cell: c => c.customer_token },
            { header: 'Score', cell: c => c.score },
            { header: 'Band', cell: c => <BandBadge band={c.band} /> },
            { header: 'Reasons', cell: c => c.reasons.join(', ') },
          ]}
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// New contacts (the AI intake review)
// ---------------------------------------------------------------------------
function NewContacts({ intakes }: { intakes: Intake[] | undefined }) {
  if (!intakes) return <Loading />;
  return (
    <>
      <Caption>
        Each hardship form or call-back request from the customer app: sanitized on arrival (tokens and keyword flags
        only), scored by Node B's fixed rules, then assessed by the AI for the team. The AI explains; it decides nothing.
      </Caption>
      {intakes.length === 0 && (
        <Alert look="info" className="mt-2">
          No new contacts yet.
        </Alert>
      )}
      <div className="mt-2 flex flex-col gap-2">
        {intakes.map(i => (
          <div key={i.n} className="rounded-xl border border-border-muted-soft bg-background-white p-3" data-testid="intake">
            <div className="flex flex-wrap items-center gap-2">
              <span className="typography-body-9 font-bold text-text-heading">{i.customer_token}</span>
              <CodeBadge color="hero">{titleCase(i.type)}</CodeBadge>
              <span className="typography-body-10 text-text-muted">
                {i.channel} · {i.date}
                {i.callback_due ? ` · call back ${stamp(i.callback_due)}` : ''}
              </span>
              {i.flags.map(f => (
                <CodeBadge key={f} color="warning">
                  {f}
                </CodeBadge>
              ))}
            </div>
            {i.status === 'PENDING' ? (
              <div className="mt-2 flex items-center gap-2" role="status">
                <ProgressIndicator size="small" label="Assessing" />
                <span className="typography-body-10 text-text-muted">Received. Node B and the AI are reviewing it…</span>
              </div>
            ) : (
              <>
                <p className="mt-2 typography-body-10">
                  Interaction score <strong>{i.score ?? '–'}</strong> {i.band && <BandBadge band={i.band} />}{' '}
                  {i.reasons.length > 0 && <span className="text-text-muted">({i.reasons.join(', ')})</span>}
                  {i.promises_written.length > 0 && <> · new promises: {i.promises_written.join(', ')}</>}
                </p>
                <div className="mt-2 rounded-lg bg-surface-info-faint p-2" data-testid="assessment">
                  <p className="mb-1 flex items-center gap-1 typography-body-10 font-bold text-text-info">
                    Hardship assessment{' '}
                    <CodeBadge color={i.ai_used ? 'info' : 'muted'}>{i.ai_used ? 'AI' : 'AI unavailable'}</CodeBadge>
                  </p>
                  <p className="whitespace-pre-line typography-body-10 text-text-body">{i.assessment}</p>
                </div>
              </>
            )}
          </div>
        ))}
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Approvals
// ---------------------------------------------------------------------------
function Approvals({ staff, recs }: { staff: string; recs: TrackedRec[] | undefined }) {
  const [note, setNote] = useState<{ look: 'success' | 'danger'; text: string } | null>(null);
  const decide = useAction(({ rec, accept }: { rec: string; accept: boolean }) =>
    post<{ status: string; live: boolean }>(`/api/westpac/recommendations/${rec}/${accept ? 'approve' : 'reject'}`, { staff }),
  );
  if (!recs) return <Loading />;
  const pending = recs.filter(r => r.status === 'AWAITING_APPROVAL');
  const decided = recs.filter(r => r.status !== 'AWAITING_APPROVAL').reverse();
  const onDecide = (rec: string, accept: boolean) =>
    decide.mutate(
      { rec, accept },
      {
        onSuccess: r =>
          setNote({
            look: 'success',
            text: accept
              ? `${rec} approved by ${staff}. ${r.live ? 'The next sweep carries it out (Node D re-checks it first).' : 'Automatic sweeps are off: carry it out from the walkthrough.'}`
              : `${rec} rejected by ${staff}. Nothing is sent to the customer.`,
          }),
        onError: err => setNote({ look: 'danger', text: errorText(err) }),
      },
    );
  return (
    <>
      <Caption>
        What the sweep recommends. Nothing reaches a customer until a person approves it; approved items are carried out
        automatically by the next sweep.
      </Caption>
      {note && (
        <Alert look={note.look} className="mt-2" dismissible onClose={() => setNote(null)}>
          {note.text}
        </Alert>
      )}
      {pending.length === 0 && (
        <Alert look="success" className="mt-2">
          Nothing is waiting for approval.
        </Alert>
      )}
      <div className="mt-2 flex flex-col gap-2">
        {pending.map(r => (
          <PendingCard key={r.rec_id} rec={r} busy={decide.isPending} onDecide={onDecide} />
        ))}
      </div>
      <H>Decided</H>
      {decided.length === 0 ? (
        <Caption>Nothing decided yet.</Caption>
      ) : (
        <DataTable
          testId="decided"
          caption="Decided recommendations"
          rows={decided}
          rowKey={r => r.rec_id}
          columns={[
            { header: 'Rec', cell: r => r.rec_id },
            { header: 'Customer', cell: r => r.customer_token },
            { header: 'Recommendation', cell: r => titleCase(r.recommendation) },
            {
              header: 'Message',
              cell: r =>
                r.recommendation === 'QUIET_HELP_PUSH' ? (
                  <span className="flex flex-col items-start gap-1">
                    <QuietHelpMessageBadge message={r.message} />
                    {r.message_reason && (
                      <span className="typography-body-10 text-text-muted">{quietHelpReason(r.message_reason)}</span>
                    )}
                  </span>
                ) : (
                  ''
                ),
            },
            { header: 'Status', cell: r => <StatusBadge status={r.status} /> },
            { header: 'Decided by', cell: r => r.decided_by ?? '' },
            {
              header: 'Next',
              cell: r =>
                r.status === 'APPROVED' ? 'carried out by the next sweep' : r.status === 'DONE' ? 'carried out' : 'nothing sent',
            },
          ]}
        />
      )}
    </>
  );
}

function PendingCard({
  rec,
  busy,
  onDecide,
}: {
  rec: TrackedRec;
  busy: boolean;
  onDecide: (rec: string, accept: boolean) => void;
}) {
  const facts = useApi<Explanation>(`/api/policy/explain/${rec.entry_id}`, { refetch: false });
  const [words, setWords] = useState<{ look: 'info' | 'warning'; text: string } | null>(null);
  const ask = useAction(() => post<{ text: string }>(`/api/policy/explain/${rec.entry_id}/words`));
  const f = facts.data?.facts;
  return (
    <div className="rounded-xl border border-border-muted-soft bg-background-white p-3" data-testid={`approval-${rec.rec_id}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="typography-body-9 font-bold text-text-heading">{titleCase(rec.recommendation)}</span>
        <span className="typography-body-10 text-text-muted">
          {rec.rec_id} · {rec.customer_token}
        </span>
      </div>
      {rec.recommendation === 'QUIET_HELP_PUSH' && (
        <p className="mt-1 flex flex-wrap items-center gap-1 typography-body-10" data-testid="message-choice">
          <QuietHelpMessageBadge message={rec.message} />
          {rec.message_reason && <span className="text-text-muted">{quietHelpReason(rec.message_reason)}</span>}
        </p>
      )}
      <Caption>Why: {rec.why.join(', ')}</Caption>
      {facts.data && (
        <p className="mt-1 typography-body-10">
          <strong>Rule:</strong> {facts.data.rule}
        </p>
      )}
      {f && (
        <div className="mt-2">
          <Metrics>
            <Metric label="Combined score" value={f.combined_score !== null ? `${f.combined_score} ${f.band}` : '–'} />
            <Metric label="Open hardship case" value={f.open_hardship_case ? `due ${f.open_hardship_case.due.slice(0, 10)}` : 'no'} />
            <Metric label="Overdue promises" value={f.overdue_promises.length} />
            <Metric label="Quiet Help in 30 days" value={f.quiet_help_push_in_last_30_days ? 'yes' : 'no'} />
          </Metrics>
        </div>
      )}
      {words && (
        <Alert look={words.look} className="mt-2">
          {words.text}
        </Alert>
      )}
      <div className="mt-2 grid gap-2 sm:grid-cols-3">
        <Button
          look="hero"
          soft
          block
          disabled={ask.isPending}
          onClick={() =>
            ask.mutate(undefined, {
              onSuccess: r => setWords({ look: 'info', text: r.text }),
              onError: err => setWords({ look: 'warning', text: errorText(err) }),
            })
          }
        >
          {ask.isPending ? 'Asking the AI…' : 'Explain in plain English (AI)'}
        </Button>
        <Button look="primary" block disabled={busy} onClick={() => onDecide(rec.rec_id, true)}>
          Approve
        </Button>
        <Button look="faint" soft block disabled={busy} onClick={() => onDecide(rec.rec_id, false)}>
          Reject
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Check an action
// ---------------------------------------------------------------------------
function CheckAction({ staff }: { staff: string }) {
  const meta = useMeta();
  const customers = useApi<string[]>('/api/ledger/customers');
  const tokens = customers.data ?? [];
  const actions = meta.data?.checkable ?? [];
  const [customer, setCustomer] = useState<string | null>(null);
  const [action, setAction] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [result, setResult] = useState<WestpacCheck | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  // Fails closed: if the ledger doesn't verify, every action is blocked and nothing is recorded.
  const check = useAction((body: object) => post<WestpacCheck>('/api/westpac/check', body));
  const token = customer && tokens.includes(customer) ? customer : tokens[0] ?? '';
  const chosen = action ?? actions[0] ?? '';
  return (
    <>
      <Caption>
        Before a default notice, a credit offer, or trusting someone who says they're calling from Westpac, ask Node D.
        P2: no collections during an open hardship case · P3: a caller must quote the booked call code · P4: no credit
        offers to HIGH or CRITICAL customers. Every answer is recorded.
      </Caption>
      <form
        aria-label="Check an action"
        className="mt-2 rounded-xl border border-border-muted-soft bg-background-white p-3"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          check.mutate(
            { customer_token: token, action: chosen, requested_by: staff, call_code: code || null },
            {
              onSuccess: r => {
                setResult(r);
                setProblem(null);
              },
              onError: err => {
                setResult(null);
                setProblem(errorText(err));
              },
            },
          );
        }}
      >
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
            <Select value={chosen} onChange={e => setAction(e.target.value)} width="full">
              {actions.map(a => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Call code the caller quoted (VERIFY_CALLER only)">
            <Input value={code} onChange={e => setCode(e.target.value)} maxLength={12} autoComplete="off" />
          </Field>
        </div>
        <Button type="submit" look="primary" className="mt-2" disabled={check.isPending || !token}>
          Check with Node D
        </Button>
        <Caption>Requested by {staff}.</Caption>
      </form>
      <div className="mt-2" aria-live="polite">
        {problem && <Alert look="warning">Can't check that: {problem}</Alert>}
        {result &&
          (result.paused ? (
            <Alert look="danger" heading={`BLOCKED · ${result.decision.action} for ${result.decision.customer_token}`} data-testid="decision">
              {result.decision.reason} Nothing is recorded: the rules would be reading a ledger that may have been changed.
            </Alert>
          ) : (
            <>
              <DecisionAlert decision={result.decision} />
              <Caption>Recorded in the ledger as {result.entry_id}.</Caption>
            </>
          ))}
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Customers
// ---------------------------------------------------------------------------
function Customers() {
  const customers = useApi<string[]>('/api/ledger/customers');
  const tokens = customers.data ?? [];
  const [picked, setPicked] = useState<string | null>(null);
  const token = picked && tokens.includes(picked) ? picked : tokens[0] ?? null;
  const lookup = useApi<CustomerLookup>(token ? `/api/ledger/customers/${token}` : null);
  const d = lookup.data;
  const promises = (d?.history ?? []).filter(e => e.entry_type === 'PROMISE');
  return (
    <>
      <Field label="Customer token" className="mb-2 md:max-w-xs">
        <Select value={token ?? ''} onChange={e => setPicked(e.target.value)} width="full" data-testid="lookup-customer">
          {tokens.map(t => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </Select>
      </Field>
      {lookup.error && <ErrorAlert error={lookup.error} />}
      {d && (
        <>
          <Metrics>
            <Metric label="Combined score" value={d.score ? `${d.score.score} ${d.score.band}` : 'not scored'} testId="combined-score" />
            <Metric label="Account (A)" value={d.score?.account_score ?? '–'} />
            <Metric label="Interactions (B)" value={d.score?.interaction_score ?? '–'} />
            <Metric label="Open hardship case" value={d.open_case ? `due ${stamp(d.open_case.due)}` : 'no'} />
          </Metrics>
          {d.score && d.score.reasons.length > 0 && <Caption>Reasons: {d.score.reasons.join(', ')}</Caption>}
          <H>Promises</H>
          {promises.length === 0 ? (
            <Caption>No promises.</Caption>
          ) : (
            <DataTable
              caption="Promises"
              rows={promises}
              rowKey={e => e.entry_id}
              columns={[
                { header: 'Entry', cell: e => e.entry_id },
                { header: 'What', cell: e => e.what },
              ]}
            />
          )}
          <H>History</H>
          <DataTable
            caption={`History of ${d.customer_token}`}
            rows={d.history}
            rowKey={e => e.entry_id}
            columns={[
              { header: 'Entry', cell: e => e.entry_id, className: 'whitespace-nowrap' },
              { header: 'Time', cell: e => when(e.created_at), className: 'whitespace-nowrap' },
              { header: 'Type', cell: e => e.entry_type },
              { header: 'What', cell: e => e.what },
            ]}
          />
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Audit
// ---------------------------------------------------------------------------
function Audit() {
  const integrity = useApi<Integrity>('/api/ledger/integrity');
  const decisions = useApi<DecisionRow[]>('/api/policy/decisions');
  const done = useApi<ActionDone[]>('/api/westpac/actions-done');
  const ledger = useApi<Entries>('/api/ledger/entries');
  const r = integrity.data?.report;
  return (
    <>
      {r && (
        <Alert look={r.valid ? 'success' : 'danger'} heading={r.valid ? 'Chain verified' : 'LEDGER TAMPERED'}>
          {r.valid ? (
            <>
              {r.entries_checked} entries. Newest {r.last_entry_id}, head hash <Code>{r.head_hash.slice(0, 16)}…</Code>
            </>
          ) : (
            <>
              {r.problem} at {r.first_bad_entry}. {r.detail}
            </>
          )}
        </Alert>
      )}
      <H caption="Every ALLOW / BLOCK Node D recorded, newest first.">Decisions</H>
      {decisions.data && decisions.data.length === 0 && <Caption>No decisions yet.</Caption>}
      {decisions.data && decisions.data.length > 0 && (
        <DataTable
          testId="audit-decisions"
          caption="Decisions"
          rows={decisions.data}
          rowKey={x => x.entry_id}
          columns={[
            { header: 'Entry', cell: x => x.entry_id },
            { header: 'Customer', cell: x => x.customer_token },
            { header: 'Action', cell: x => x.action },
            { header: 'Decision', cell: x => <DecisionBadge decision={x.decision} policy={x.policy} /> },
            { header: 'Reason', cell: x => x.reason },
          ]}
        />
      )}
      <H caption="What Node E carried out after a person approved it (call codes hidden).">Actions carried out</H>
      {done.data && done.data.length === 0 && <Caption>Nothing carried out yet.</Caption>}
      {done.data && done.data.length > 0 && (
        <DataTable
          testId="audit-actions"
          caption="Actions carried out"
          rows={done.data}
          rowKey={x => x.entry_id}
          columns={[
            { header: 'Entry', cell: x => x.entry_id },
            { header: 'Customer', cell: x => x.customer_token },
            { header: 'Action', cell: x => titleCase(x.action) },
            {
              header: 'Details',
              cell: x =>
                x.message_id
                  ? `message ${String(x.message_id)}`
                  : x.meeting_time
                    ? `call ${stamp(String(x.meeting_time))}, code ${String(x.call_code)}`
                    : Array.isArray(x.why)
                      ? (x.why as string[]).join(', ')
                      : '',
            },
          ]}
        />
      )}
      <div className="mt-4">
        <Accordion>
          <AccordionItem key="ledger" id="ledger" title="The full ledger (read-only, append-only)">
            {ledger.data && (
              <DataTable
                caption="The full ledger"
                rows={[...ledger.data.entries].reverse()}
                rowKey={e => e.entry_id}
                highlighted={e => e.entry_id === ledger.data?.bad_entry}
                columns={[
                  { header: 'Entry', cell: e => e.entry_id, className: 'whitespace-nowrap' },
                  { header: 'Time', cell: e => when(e.created_at), className: 'whitespace-nowrap' },
                  { header: 'Customer', cell: e => e.customer_token },
                  { header: 'Type', cell: e => e.entry_type },
                  { header: 'What', cell: e => e.what },
                ]}
              />
            )}
          </AccordionItem>
          <AccordionItem key="json" id="json" title="Last sweep in full (each step's output)">
            <LastSweepJson />
          </AccordionItem>
        </Accordion>
      </div>
    </>
  );
}

function LastSweepJson() {
  const status = useApi<LiveStatus>('/api/live/status');
  const sweep = status.data?.last_cycle?.sweep;
  return sweep ? <JsonView value={sweep} label="Last sweep" /> : <Caption>No sweep yet.</Caption>;
}
