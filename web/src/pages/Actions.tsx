// Node E – Human approval & customer actions. Same features as ui/pages/E.py:
//   metrics · Approval Queue (staff, Approve / Reject, Execute) · Customer Experience (phone mock-up)
//   · Caller verification (P3) · Activity & Status
// Human decisions persist in Node C's append-only ledger. Approved actions are re-checked by Node D
// before they're carried out. The call code is only ever shown on the customer's phone.
import { Alert } from '@westpac/ui/alert';
import { Button } from '@westpac/ui/button';
import { Field } from '@westpac/ui/field';
import { PadlockIcon } from '@westpac/ui/icon';
import { Input } from '@westpac/ui/input';
import { Panel, PanelBody } from '@westpac/ui/panel';
import { PassCode } from '@westpac/ui/pass-code';
import { Select } from '@westpac/ui/select';
import { Tabs, TabsPanel } from '@westpac/ui/tabs';
import { VisuallyHidden } from '@westpac/ui/visually-hidden';
import { FormEvent, ReactNode, useState } from 'react';

import {
  ActionItem,
  CheckResult,
  Entries,
  ExecuteResult,
  InboxMessage,
  Queue,
  errorText,
  post,
  useAction,
  useApi,
  useMeta,
} from '../api';
import { Caption, DataTable, ErrorAlert, Metric, Metrics, PageTitle, StatusBadge, stamp, titleCase } from '../components';

type Note = { look: 'success' | 'warning' | 'danger'; text: string } | null;

export function ActionsPage() {
  const meta = useMeta();
  const queue = useApi<Queue>('/api/actions');
  const items = queue.data?.items ?? [];
  const staffList = meta.data?.staff ?? [];
  const hero = meta.data?.hero ?? 'cust_af4200';
  const [staff, setStaff] = useState<string | null>(null);
  const [customer, setCustomer] = useState<string | null>(null);
  const actingStaff = staff ?? staffList[1] ?? staffList[0] ?? ''; // E.py's default: staff_19c
  const customers = [...new Set(items.map(i => i.customer_token))].sort();
  const chosenCustomer =
    customer && customers.includes(customer) ? customer : customers.includes(hero) ? hero : customers[0] ?? null;

  const staffPicker = (
    <Field label="Acting staff member" className="mb-2 md:max-w-xs">
      <Select value={actingStaff} onChange={e => setStaff(e.target.value)} width="full" data-testid="staff-select">
        {staffList.map(s => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </Select>
    </Field>
  );
  const customerPicker = (
    <Field label="Select customer" className="mb-2 md:max-w-xs">
      <Select
        value={chosenCustomer ?? ''}
        onChange={e => setCustomer(e.target.value)}
        width="full"
        data-testid="customer-select"
      >
        {customers.map(c => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </Select>
    </Field>
  );

  const counts = queue.data?.counts;
  return (
    <>
      <PageTitle title="Customer Guardian" subtitle="Node E – Human Approval & Customer Actions">
        Human decisions are saved in Node C's append-only ledger. Approved actions are re-checked by Node D's policies
        before they are carried out.
      </PageTitle>
      {queue.error && <ErrorAlert error={queue.error} />}
      <Metrics>
        <Metric label="Pending" value={counts?.pending ?? '–'} testId="metric-pending" />
        <Metric label="Approved" value={counts?.approved ?? '–'} testId="metric-approved" />
        <Metric label="Completed" value={counts?.completed ?? '–'} testId="metric-completed" />
        <Metric label="Total" value={counts?.total ?? '–'} testId="metric-total" />
      </Metrics>
      <div className="mt-4">
        <Tabs aria-label="Actions">
          <TabsPanel key="queue" title="Approval Queue">
            <div className="pt-3">
              {staffPicker}
              <ApprovalQueue items={items} staff={actingStaff} />
            </div>
          </TabsPanel>
          <TabsPanel key="customer" title="Customer Experience">
            <div className="pt-3">
              {chosenCustomer ? (
                <>
                  {customerPicker}
                  <Phone customer={chosenCustomer} />
                </>
              ) : (
                <Alert look="info">No customer recommendations in the ledger yet.</Alert>
              )}
            </div>
          </TabsPanel>
          <TabsPanel key="verify" title="Caller verification">
            <div className="pt-3">
              {chosenCustomer ? (
                <>
                  <div className="grid gap-2 md:grid-cols-2">
                    {customerPicker}
                    {staffPicker}
                  </div>
                  <CallerVerification customer={chosenCustomer} staff={actingStaff} />
                </>
              ) : (
                <Alert look="info">No customer recommendations in the ledger yet.</Alert>
              )}
            </div>
          </TabsPanel>
          <TabsPanel key="activity" title="Activity & Status">
            <div className="pt-3">
              <Activity items={items} />
            </div>
          </TabsPanel>
        </Tabs>
      </div>
      <p className="mt-4 typography-body-10 text-text-muted">Customer Guardian · Node E · Westpac Hackathon Prototype</p>
    </>
  );
}

// ---------------------------------------------------------------------------
// Approval Queue
// ---------------------------------------------------------------------------
function Card({ item, children }: { item: ActionItem; children?: ReactNode }) {
  return (
    <div
      className="rounded-xl border border-border-muted-soft bg-background-white p-2"
      data-testid={`rec-${item.rec_id}`}
      aria-label={`${item.rec_id} ${item.recommendation} for ${item.customer_token}`}
    >
      <p className="typography-body-9 font-bold text-text-heading">{titleCase(item.recommendation)}</p>
      <Caption>
        {item.rec_id} · {item.customer_token}
      </Caption>
      {children}
    </div>
  );
}

function ApprovalQueue({ items, staff }: { items: ActionItem[]; staff: string }) {
  const pending = items.filter(i => i.status === 'AWAITING_APPROVAL');
  const approved = items.filter(i => i.status === 'APPROVED');
  const [note, setNote] = useState<Note>(null);
  const [execNote, setExecNote] = useState<Note>(null);
  const decide = useAction(({ rec, accept }: { rec: string; accept: boolean }) =>
    post<{ status: string; warning?: string }>(`/api/actions/${rec}/${accept ? 'approve' : 'reject'}`, { staff }),
  );
  const execute = useAction((rec: string) => post<ExecuteResult>(`/api/actions/${rec}/execute`));

  const onDecide = (rec: string, accept: boolean) =>
    decide.mutate(
      { rec, accept },
      {
        onSuccess: r =>
          setNote(r.warning ? { look: 'warning', text: r.warning } : { look: 'success', text: `${rec}: ${r.status} — saved in ledger` }),
        onError: err => setNote({ look: 'danger', text: errorText(err) }),
      },
    );
  const onExecute = (rec: string) =>
    execute.mutate(rec, {
      onSuccess: r =>
        setExecNote(
          r.blocked
            ? { look: 'danger', text: `Blocked by Node D (${r.blocked.policy}): ${r.blocked.reason}` }
            : { look: 'success', text: `${rec}: carried out — ${titleCase(String(r.action))} written to the ledger` },
        ),
      onError: err => setExecNote({ look: 'danger', text: errorText(err) }),
    });

  return (
    <div className="grid gap-3 md:grid-cols-5">
      <div className="md:col-span-3">
        <p className="mb-2 typography-body-8 font-bold text-text-heading">Approval Queue</p>
        {note && (
          <Alert look={note.look} className="mb-2" dismissible onClose={() => setNote(null)}>
            {note.text}
          </Alert>
        )}
        {pending.length === 0 && <Alert look="success">No recommendations awaiting approval.</Alert>}
        <div className="flex flex-col gap-2">
          {pending.map(item => (
            <Card key={item.rec_id} item={item}>
              <Caption>Reasons: {item.why.join(', ')}</Caption>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <Button look="primary" block disabled={decide.isPending} onClick={() => onDecide(item.rec_id, true)}>
                  Approve
                </Button>
                <Button look="faint" soft block disabled={decide.isPending} onClick={() => onDecide(item.rec_id, false)}>
                  Reject
                </Button>
              </div>
            </Card>
          ))}
        </div>
      </div>
      <div className="md:col-span-2">
        <p className="mb-2 typography-body-8 font-bold text-text-heading">Approved — Awaiting Execution</p>
        <Caption>Each action is re-checked by Node D's policies before it is carried out.</Caption>
        {execNote && (
          <Alert look={execNote.look} className="my-2" dismissible onClose={() => setExecNote(null)}>
            {execNote.text}
          </Alert>
        )}
        {approved.length === 0 && (
          <Alert look="info" className="mt-2">
            No approved actions available.
          </Alert>
        )}
        <div className="mt-2 flex flex-col gap-2">
          {approved.map(item => (
            <Card key={item.rec_id} item={item}>
              <Button look="hero" block className="mt-2" disabled={execute.isPending} onClick={() => onExecute(item.rec_id)}>
                Execute
              </Button>
            </Card>
          ))}
        </div>
        <Caption>
          Execute writes the action to the ledger and marks it DONE. The customer sees it in the Customer Experience tab.
        </Caption>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Customer Experience: the phone mock-up (the ONLY place a call code is shown)
// ---------------------------------------------------------------------------
function Phone({ customer }: { customer: string }) {
  const inbox = useApi<InboxMessage[]>(`/api/actions/inbox/${customer}`);
  const messages = inbox.data ?? [];
  return (
    <div className="mx-auto w-full max-w-xs" data-testid="phone">
      <div className="rounded-5xl border-4 border-border-hero bg-background-hero p-2">
        <div className="pb-2 text-center typography-body-10 text-text-mono">9:41 · Westpac Mobile</div>
        <Panel heading="Customer Notifications" headingTag="h3" look="hero">
          <PanelBody>
            {inbox.error && <ErrorAlert error={inbox.error} />}
            {messages.length === 0 ? (
              <Caption>No messages have been sent to this customer yet.</Caption>
            ) : (
              <>
                {/* The lock screen never shows details. */}
                <Alert look="info" heading="Lock screen" data-testid="lock-screen">
                  {messages[messages.length - 1].lock_screen}
                </Alert>
                <p className="mt-3 mb-1 typography-body-10 font-bold text-text-muted">Inside the app</p>
                <div className="flex flex-col gap-2">
                  {messages.map((m, n) => (
                    <Message key={`${m.kind}-${n}`} message={m} />
                  ))}
                </div>
              </>
            )}
          </PanelBody>
        </Panel>
      </div>
    </div>
  );
}

function Message({ message: m }: { message: InboxMessage }) {
  return (
    <div className="rounded-xl border border-border-muted-soft bg-background-white p-2" data-testid={`message-${m.kind}`}>
      <p className="typography-body-9 font-bold text-text-heading">{m.in_app_title}</p>
      <p className="mt-1 typography-body-10 text-text-body">{m.in_app_body}</p>
      {m.kind === 'QUIET_HELP' ? (
        <div className="mt-2 flex flex-col gap-1">
          {(m.options ?? []).map(o => (
            <Button key={o} look="faint" soft block size="small" disabled>
              {titleCase(o)}
            </Button>
          ))}
        </div>
      ) : (
        <div className="mt-2">
          <p className="typography-body-10">Call booked for {stamp(m.meeting_time)}</p>
          <p className="mt-2 mb-1 flex items-center gap-1 typography-body-10 font-bold text-text-heading">
            <PadlockIcon size="small" color="hero" /> Your call code
          </p>
          <PassCode
            length={(m.call_code ?? '').length || 6}
            type="alphanumeric"
            value={(m.call_code ?? '').split('')}
            onChange={() => undefined}
          />
          <VisuallyHidden>
            Your call code is <span data-testid="call-code">{m.call_code}</span>
          </VisuallyHidden>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Caller verification (P3)
// ---------------------------------------------------------------------------
function CallerVerification({ customer, staff }: { customer: string; staff: string }) {
  const [quoted, setQuoted] = useState('');
  const [warning, setWarning] = useState<string | null>(null);
  const [result, setResult] = useState<CheckResult | null>(null);
  const verify = useAction((code: string) =>
    post<CheckResult>('/api/actions/verify-caller', { customer_token: customer, call_code: code, staff }),
  );

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setResult(null);
    if (!quoted.trim()) {
      setWarning('Type the code the caller quoted first.');
      return;
    }
    verify.mutate(quoted, {
      onSuccess: r => {
        setWarning(null);
        setResult(r);
      },
      onError: err => setWarning(errorText(err)),
    });
  };

  return (
    <div className="md:max-w-md">
      <p className="typography-body-8 font-bold text-text-heading">Caller Verification</p>
      <Caption>
        Someone calls the customer saying they're from Westpac. Type the code the CALLER quotes; Node D's policy P3
        checks it against the calls Westpac really booked.
      </Caption>
      {/* The real code is never shown here: it's only on the customer's phone. */}
      <form onSubmit={submit} className="mt-2 flex flex-col gap-2" aria-label="Caller verification">
        <Field label="Code provided by caller">
          <Input
            value={quoted}
            onChange={e => setQuoted(e.target.value)}
            maxLength={12}
            placeholder="e.g. U5PXLW"
            autoComplete="off"
          />
        </Field>
        <Button type="submit" look="primary" disabled={verify.isPending}>
          Verify Caller
        </Button>
      </form>
      <div className="mt-2" aria-live="polite">
        {warning && <Alert look="warning">{warning}</Alert>}
        {result &&
          (result.decision.decision === 'ALLOW' ? (
            <Alert look="success" heading="Genuine Westpac caller" data-testid="verdict">
              {result.decision.reason}
            </Alert>
          ) : (
            <Alert look="danger" heading={`Possible scam (${result.decision.policy})`} data-testid="verdict">
              {result.decision.reason}
            </Alert>
          ))}
        {result && <Caption>The check is recorded in the ledger as {result.entry_id}.</Caption>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Activity & Status
// ---------------------------------------------------------------------------
function Activity({ items }: { items: ActionItem[] }) {
  const ledger = useApi<Entries>('/api/ledger/entries');
  const events = [...(ledger.data?.entries ?? [])].reverse();
  const reference = (d: Record<string, unknown>) => String(d.rec_id ?? d.ref_id ?? d.promise_id ?? '');
  return (
    <>
      <p className="mb-2 typography-body-8 font-bold text-text-heading">Recommendation Status</p>
      {items.length === 0 ? (
        <Caption>No recommendations recorded yet.</Caption>
      ) : (
        <DataTable
          testId="status-table"
          caption="Recommendation status"
          rows={items}
          rowKey={i => i.rec_id}
          columns={[
            { header: 'ID', cell: i => i.rec_id },
            { header: 'Customer', cell: i => i.customer_token },
            { header: 'Action', cell: i => i.recommendation },
            { header: 'Status', cell: i => <StatusBadge status={i.status} /> },
          ]}
        />
      )}
      <p className="mt-4 mb-2 typography-body-8 font-bold text-text-heading">Promise Ledger Activity</p>
      {ledger.error && <ErrorAlert error={ledger.error} />}
      {events.length === 0 ? (
        <Caption>No ledger activity yet.</Caption>
      ) : (
        <DataTable
          caption="Promise Ledger activity"
          rows={events}
          rowKey={e => e.entry_id}
          columns={[
            { header: 'Entry', cell: e => e.entry_id, className: 'whitespace-nowrap' },
            { header: 'Type', cell: e => e.entry_type },
            { header: 'Customer', cell: e => e.customer_token },
            { header: 'Reference', cell: e => reference(e.data) },
            { header: 'Created', cell: e => e.created_at.replace('T', ' '), className: 'whitespace-nowrap' },
          ]}
        />
      )}
      <Caption>The ledger is append-only. Demo reset is intentionally not available here.</Caption>
    </>
  );
}
