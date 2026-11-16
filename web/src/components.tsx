// Small building blocks shared by the pages, all made of GEL components and GEL tokens.
import { Alert } from '@westpac/ui/alert';
import { Badge } from '@westpac/ui/badge';
import { Heading } from '@westpac/ui/heading';
import {
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableHeaderRow,
  TableRow,
} from '@westpac/ui/table';
import { ReactNode } from 'react';

import { errorText } from './api';

// ---------------------------------------------------------------------------
// Formatting (times are the demo's fixed clock, shown as stored: no time zones)
// ---------------------------------------------------------------------------
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "2026-11-16T10:00:00" -> "16 Nov 10:00" (like strftime("%d %b %H:%M") on the Streamlit pages). */
export function when(iso: string | null | undefined): string {
  if (!iso) return '';
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso);
  return m ? `${m[3]} ${MONTHS[Number(m[2]) - 1]} ${m[4]}:${m[5]}` : iso;
}

/** "2026-11-16T10:00:00" -> "2026-11-16 10:00". */
export function stamp(iso: string | null | undefined): string {
  return iso ? iso.slice(0, 16).replace('T', ' ') : '';
}

/** "2026-12-01T17:00:00" -> "01 Dec". */
export function day(iso: string): string {
  const m = /^\d{4}-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${m[2]} ${MONTHS[Number(m[1]) - 1]}` : iso;
}

export const titleCase = (code: string) =>
  code
    .toLowerCase()
    .split('_')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------
export function PageTitle({ title, subtitle, children }: { title: string; subtitle: string; children?: ReactNode }) {
  return (
    <div className="mb-4">
      <Heading size={3} tag="h1" brandHeading>
        {title}
      </Heading>
      <p className="mt-1 typography-body-9 text-text-heading">{subtitle}</p>
      {children && <div className="mt-1 typography-body-10 text-text-muted">{children}</div>}
    </div>
  );
}

export function Section({
  title,
  caption,
  children,
  id,
}: {
  title: string;
  caption?: ReactNode;
  children: ReactNode;
  id?: string;
}) {
  return (
    <section className="mb-5" id={id} aria-label={title}>
      <Heading size={6} tag="h2">
        {title}
      </Heading>
      {caption && <p className="mt-1 mb-2 typography-body-10 text-text-muted">{caption}</p>}
      <div className="mt-2">{children}</div>
    </section>
  );
}

export function Caption({ children }: { children: ReactNode }) {
  return <p className="mt-1 typography-body-10 text-text-muted">{children}</p>;
}

/** A labelled number, like st.metric. */
export function Metric({ label, value, testId }: { label: string; value: ReactNode; testId?: string }) {
  return (
    <div className="rounded-xl border border-border-muted-soft bg-background-white p-2" data-testid={testId}>
      <div className="typography-body-10 text-text-muted">{label}</div>
      <div className="mt-1 typography-body-7 font-bold text-text-heading">{value}</div>
    </div>
  );
}

export function Metrics({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 gap-2 md:grid-cols-4">{children}</div>;
}

/** Pretty-printed JSON (like st.json). */
export function JsonView({ value, label }: { value: unknown; label?: string }) {
  return (
    <pre
      aria-label={label}
      className="max-h-96 overflow-auto rounded-xl border border-border-muted-soft bg-surface-muted-pale p-2 typography-body-10 text-text-body"
    >
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function Code({ children }: { children: ReactNode }) {
  return <code className="rounded-sm bg-surface-muted-pale px-1 typography-body-10">{children}</code>;
}

export function ErrorAlert({ error }: { error: unknown }) {
  return (
    <Alert look="danger" className="mb-2">
      {errorText(error)}
    </Alert>
  );
}

export function Loading() {
  return <p className="typography-body-10 text-text-muted">Loading…</p>;
}

// ---------------------------------------------------------------------------
// Tables
// ---------------------------------------------------------------------------
export type Column<T> = { header: string; cell: (row: T) => ReactNode; className?: string };

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  highlighted,
  caption,
  testId,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  highlighted?: (row: T) => boolean;
  caption?: string;
  testId?: string;
}) {
  return (
    <div data-testid={testId}>
      <Table striped aria-label={caption}>
        <TableHeader>
          <TableHeaderRow>
            {columns.map(c => (
              <TableHeaderCell key={c.header} scope="col">
                {c.header}
              </TableHeaderCell>
            ))}
          </TableHeaderRow>
        </TableHeader>
        <TableBody>
          {rows.map(row => {
            const bad = highlighted?.(row) ?? false;
            return (
              <TableRow key={rowKey(row)} highlighted={bad} data-highlighted={bad ? 'true' : undefined}>
                {columns.map((c, i) => (
                  <TableCell
                    key={c.header}
                    highlightStart={bad && i === 0}
                    className={[c.className, bad ? 'bg-surface-danger-faint text-text-danger' : ''].join(' ').trim()}
                  >
                    {c.cell(row)}
                  </TableCell>
                ))}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Badges for the fixed vocabularies
// ---------------------------------------------------------------------------
type BadgeColor = 'hero' | 'muted' | 'faint' | 'primary' | 'info' | 'success' | 'warning' | 'danger';

export function CodeBadge({ color, children }: { color: BadgeColor; children: ReactNode }) {
  return (
    <Badge color={color} soft type="pill" tag="span" className="whitespace-nowrap">
      {children}
    </Badge>
  );
}

const URGENCY: Record<string, [BadgeColor, string]> = {
  OVERDUE: ['danger', 'Overdue'],
  DUE_SOON: ['warning', 'Due soon'],
  UPCOMING: ['success', 'Upcoming'],
};
export const UrgencyBadge = ({ urgency }: { urgency: string }) => {
  const [color, text] = URGENCY[urgency] ?? ['muted', urgency];
  return <CodeBadge color={color}>{text}</CodeBadge>;
};

const LEVEL: Record<string, [BadgeColor, string]> = { ESCALATE: ['danger', 'Escalate'], ALERT: ['warning', 'Alert'] };
export const LevelBadge = ({ level }: { level: string }) => {
  const [color, text] = LEVEL[level] ?? ['muted', level];
  return <CodeBadge color={color}>{text}</CodeBadge>;
};

const STATUS: Record<string, [BadgeColor, string]> = {
  AWAITING_APPROVAL: ['warning', 'Awaiting approval'],
  APPROVED: ['info', 'Approved'],
  REJECTED: ['muted', 'Rejected'],
  DONE: ['success', 'Done'],
};
export const StatusBadge = ({ status }: { status: string }) => {
  const [color, text] = STATUS[status] ?? ['muted', status];
  return <CodeBadge color={color}>{text}</CodeBadge>;
};

const BAND: Record<string, BadgeColor> = { LOW: 'success', MODERATE: 'info', HIGH: 'warning', CRITICAL: 'danger' };
export const BandBadge = ({ band }: { band: string }) => <CodeBadge color={BAND[band] ?? 'muted'}>{band}</CodeBadge>;

export const DecisionBadge = ({ decision, policy }: { decision: string; policy: string | null }) =>
  decision === 'ALLOW' ? (
    <CodeBadge color="success">ALLOW</CodeBadge>
  ) : (
    <CodeBadge color="danger">BLOCK{policy ? ` (${policy})` : ''}</CodeBadge>
  );
