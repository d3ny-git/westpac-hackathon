// Node C – Promise Ledger. Same features as ui/pages/C.py:
//   1. Integrity (chain + checkpoint)  2. Risk Dashboard  3. Quiet Help list
//   4. Customer lookup  5. The full ledger (filters, the bad row highlighted, one entry in full)
// Everything is read straight from the ledger with plain Python; no AI is involved.
import { Accordion, AccordionItem } from '@westpac/ui/accordion';
import { Alert } from '@westpac/ui/alert';
import { Field } from '@westpac/ui/field';
import { MultiSelect, MultiSelectItem } from '@westpac/ui/multi-select';
import { Select } from '@westpac/ui/select';
import { useEffect, useMemo, useState } from 'react';

import {
  CustomerLookup,
  DashboardRow,
  Entries,
  Entry,
  Integrity,
  QuietHelpCandidate,
  params,
  useApi,
  useMeta,
} from '../api';
import {
  BandBadge,
  Caption,
  Code,
  DataTable,
  ErrorAlert,
  JsonView,
  Loading,
  Metric,
  Metrics,
  PageTitle,
  Section,
  UrgencyBadge,
  day,
  stamp,
  when,
} from '../components';
import { DemoControlsFold } from '../DemoControls';

type Selection = 'all' | Set<string | number>;
const asList = (selection: Selection, all: string[]) => (selection === 'all' ? all : [...selection].map(String));

export function LedgerPage() {
  const meta = useMeta();
  const integrity = useApi<Integrity>('/api/ledger/integrity');
  const count = integrity.data?.count;

  return (
    <>
      <PageTitle title="Customer Guardian" subtitle="Node C – Promise Ledger">
        <strong>Gets data from:</strong> A (account scores), B (interaction scores + promises), D (decisions,
        recommendations), E (actions) · <strong>Sends data to:</strong> D (policy checks) and this Risk Dashboard ·
        Demo time: {when(meta.data?.now)}
      </PageTitle>
      <DemoControlsFold />
      {integrity.error && <ErrorAlert error={integrity.error} />}
      {count === undefined ? (
        <Loading />
      ) : count === 0 ? (
        <Alert look="warning" heading="The ledger is empty">
          Use <strong>Reset demo (real pipeline)</strong> in Demo controls (or run <Code>python scripts/reset_demo.py</Code>).
        </Alert>
      ) : (
        <>
          <IntegritySection integrity={integrity.data!} />
          <RiskDashboard />
          <QuietHelp />
          <CustomerLookupSection />
          <FullLedger />
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// 1. Integrity
// ---------------------------------------------------------------------------
function IntegritySection({ integrity }: { integrity: Integrity }) {
  const { report, checkpoint } = integrity;
  return (
    <Section title="1. Integrity">
      <div data-testid="integrity">
        {report.valid ? (
          <Alert look="success" heading="Chain verified">
            {report.entries_checked} entries, nothing changed, removed or inserted. Newest {report.last_entry_id}, head
            hash <Code>{report.head_hash.slice(0, 16)}…</Code>
          </Alert>
        ) : (
          <Alert look="danger" heading="LEDGER TAMPERED">
            {report.problem} at <strong>{report.first_bad_entry}</strong>. {report.detail}
          </Alert>
        )}
      </div>
      <div className="mt-2">
        {checkpoint === null ? (
          <Caption>
            No checkpoint recorded yet. Record one in Demo controls to also catch the newest entries being cut off.
          </Caption>
        ) : checkpoint.holds ? (
          <Caption>
            Checkpoint OK: {checkpoint.last_entry_id} still has hash <Code>{checkpoint.head_hash.slice(0, 16)}…</Code>,
            so history up to it is intact.
          </Caption>
        ) : (
          <Alert look="danger" heading="Checkpoint broken">
            {checkpoint.last_entry_id} no longer has the recorded hash. Entries were removed or history was rebuilt
            since the checkpoint.
          </Alert>
        )}
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------------------
// 2. Risk Dashboard and 3. Quiet Help
// ---------------------------------------------------------------------------
function RiskDashboard() {
  const rows = useApi<DashboardRow[]>('/api/ledger/dashboard');
  return (
    <Section
      title="2. Risk Dashboard"
      caption="Every promise the bank hasn't kept yet, most at-risk customers first, then soonest due."
    >
      {rows.error && <ErrorAlert error={rows.error} />}
      {rows.data && rows.data.length === 0 && <Alert look="info">No open promises.</Alert>}
      {rows.data && rows.data.length > 0 && (
        <DataTable
          testId="risk-dashboard"
          caption="Risk Dashboard"
          rows={rows.data}
          rowKey={r => r.promise_id}
          columns={[
            { header: 'Urgency', cell: r => <UrgencyBadge urgency={r.urgency} /> },
            { header: 'Customer', cell: r => r.customer_token },
            { header: 'Score', cell: r => `${r.score} ${r.band}` },
            { header: 'Promise', cell: r => `${r.promise_id} ${r.promise_type}` },
            { header: 'Due', cell: r => stamp(r.due), className: 'whitespace-nowrap' },
            { header: 'Hours to due', cell: r => r.hours_to_due },
            { header: 'Made by', cell: r => r.made_by },
            { header: 'Description', cell: r => r.description },
          ]}
        />
      )}
    </Section>
  );
}

function QuietHelp() {
  const rows = useApi<QuietHelpCandidate[]>('/api/ledger/quiet-help');
  return (
    <Section
      title="3. Quiet Help list"
      caption="HIGH or CRITICAL, no open hardship case, and no Quiet Help push in the last 30 days. This is only a list: D recommends, and a person approves before anything is sent."
    >
      {rows.error && <ErrorAlert error={rows.error} />}
      {rows.data && rows.data.length === 0 && <Alert look="info">Nobody needs a Quiet Help nudge right now.</Alert>}
      {rows.data && rows.data.length > 0 && (
        <DataTable
          testId="quiet-help"
          caption="Quiet Help list"
          rows={rows.data}
          rowKey={r => r.customer_token}
          columns={[
            { header: 'Customer', cell: r => r.customer_token },
            { header: 'Score', cell: r => r.score },
            { header: 'Band', cell: r => <BandBadge band={r.band} /> },
            { header: 'Reasons', cell: r => r.reasons.join(', ') },
            { header: 'Last Quiet Help', cell: r => (r.last_quiet_help ? stamp(r.last_quiet_help) : 'never') },
          ]}
        />
      )}
    </Section>
  );
}

// ---------------------------------------------------------------------------
// 4. Customer lookup
// ---------------------------------------------------------------------------
function CustomerLookupSection() {
  const meta = useMeta();
  const customers = useApi<string[]>('/api/ledger/customers');
  const tokens = customers.data ?? [];
  const hero = meta.data?.hero ?? 'cust_af4200';
  const [picked, setPicked] = useState<string | null>(null);
  const token = picked && tokens.includes(picked) ? picked : tokens.includes(hero) ? hero : tokens[0] ?? null;
  const lookup = useApi<CustomerLookup>(token ? `/api/ledger/customers/${token}` : null);
  const d = lookup.data;

  return (
    <Section title="4. Customer lookup">
      <Field label="Customer" className="mb-2 max-w-xs">
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
            <Metric label="Open hardship case" value={d.open_case ? `due ${day(d.open_case.due)}` : 'no'} testId="open-case" />
          </Metrics>
          {d.score && d.score.reasons.length > 0 && <Caption>Reasons: {d.score.reasons.join(', ')}</Caption>}
          <div className="mt-2">
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
          </div>
        </>
      )}
    </Section>
  );
}

// ---------------------------------------------------------------------------
// 5. The full ledger
// ---------------------------------------------------------------------------
function FullLedger() {
  const all = useApi<Entries>('/api/ledger/entries');
  const [types, setTypes] = useState<Selection>(new Set());
  const [customers, setCustomers] = useState<Selection>(new Set());
  const typeList = asList(types, all.data?.types ?? []);
  const customerList = asList(customers, all.data?.customers ?? []);
  const shown = useApi<Entries>(`/api/ledger/entries${params({ type: typeList, customer: customerList })}`);
  const entries = shown.data?.entries ?? [];
  const bad = shown.data?.bad_entry ?? null;

  return (
    <Section
      title="5. The full ledger"
      caption="Append-only: entries are never edited or deleted. Each entry's prev hash is the hash of the entry above it, which is what makes any change detectable."
    >
      <div className="mb-2 grid gap-2 md:grid-cols-2">
        <Field label="Entry types">
          <MultiSelect
            items={(all.data?.types ?? []).map(t => ({ key: t, textValue: t }))}
            selectedKeys={types}
            onSelectionChange={k => setTypes(k as Selection)}
            placeholder="All entry types"
            width="full"
          >
            {item => <MultiSelectItem key={item.key} textValue={item.textValue}>{item.textValue}</MultiSelectItem>}
          </MultiSelect>
        </Field>
        <Field label="Customers">
          <MultiSelect
            items={(all.data?.customers ?? []).map(t => ({ key: t, textValue: t }))}
            selectedKeys={customers}
            onSelectionChange={k => setCustomers(k as Selection)}
            placeholder="All customers"
            width="full"
          >
            {item => <MultiSelectItem key={item.key} textValue={item.textValue}>{item.textValue}</MultiSelectItem>}
          </MultiSelect>
        </Field>
      </div>
      {shown.error && <ErrorAlert error={shown.error} />}
      {shown.data && entries.length === 0 && <Alert look="info">No entries match the filters.</Alert>}
      {entries.length > 0 && (
        <>
          {bad && <Caption>The highlighted row is where the chain breaks: {bad}.</Caption>}
          <DataTable
            testId="ledger-table"
            caption="The full ledger"
            rows={entries}
            rowKey={e => e.entry_id}
            highlighted={e => e.entry_id === bad}
            columns={[
              { header: 'Entry', cell: e => e.entry_id, className: 'whitespace-nowrap' },
              { header: 'Time', cell: e => when(e.created_at), className: 'whitespace-nowrap' },
              { header: 'Customer', cell: e => e.customer_token },
              { header: 'Type', cell: e => e.entry_type },
              { header: 'What', cell: e => e.what },
              { header: 'Prev hash', cell: e => <Code>{e.prev_hash.slice(0, 10)}…</Code> },
              { header: 'Hash', cell: e => <Code>{e.hash.slice(0, 10)}…</Code> },
            ]}
          />
          <div className="mt-2">
            <Accordion>
              <AccordionItem key="full" id="full" title="Show one entry in full">
                <EntryInFull entries={entries} />
              </AccordionItem>
            </Accordion>
          </div>
        </>
      )}
    </Section>
  );
}

function EntryInFull({ entries }: { entries: Entry[] }) {
  const [pick, setPick] = useState<string>('');
  const ids = useMemo(() => entries.map(e => e.entry_id), [entries]);
  useEffect(() => {
    if (!ids.includes(pick)) setPick(ids[0] ?? '');
  }, [ids, pick]);
  const entry = entries.find(e => e.entry_id === pick);
  return (
    <div className="flex flex-col gap-2">
      <Field label="Entry" className="max-w-xs">
        <Select value={pick} onChange={e => setPick(e.target.value)} width="full">
          {ids.map(id => (
            <option key={id} value={id}>
              {id}
            </option>
          ))}
        </Select>
      </Field>
      {entry && (
        <JsonView
          label={`Entry ${entry.entry_id}`}
          value={{
            entry_id: entry.entry_id,
            customer_token: entry.customer_token,
            entry_type: entry.entry_type,
            data: entry.data,
            created_at: entry.created_at,
            prev_hash: entry.prev_hash,
            hash: entry.hash,
          }}
        />
      )}
      <Caption>Call codes are hidden: they are only ever shown on the customer's phone.</Caption>
    </div>
  );
}
