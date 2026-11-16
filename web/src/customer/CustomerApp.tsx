// The customer app (/customer/): what a Westpac customer sees in their app. Phone-first.
//   Sign in (demo) · Home (accounts, recent transactions) · Messages (Quiet Help offers that work,
//   a booked call's call code) · Get help (hardship form, call-back request) · Our promises to you ·
//   Is this call really Westpac?
// The customer never sees scores, bands, flags, tokens or policy names: the API doesn't send them.
import { Alert } from '@westpac/ui/alert';
import { Badge } from '@westpac/ui/badge';
import { Button } from '@westpac/ui/button';
import { Field } from '@westpac/ui/field';
import { Footer } from '@westpac/ui/footer';
import { Header } from '@westpac/ui/header';
import { Heading } from '@westpac/ui/heading';
import { PadlockIcon } from '@westpac/ui/icon';
import { Input } from '@westpac/ui/input';
import { Panel, PanelBody } from '@westpac/ui/panel';
import { PassCode } from '@westpac/ui/pass-code';
import { Select } from '@westpac/ui/select';
import { Textarea } from '@westpac/ui/textarea';
import { VisuallyHidden } from '@westpac/ui/visually-hidden';
import { FormEvent, ReactNode, useState } from 'react';

import { errorText, post, useAction, useApi, useMeta } from '../api';
import { ErrorAlert, Loading } from '../components';
import { friendly, greeting, money, useHashRoute, useRemembered } from '../live/shared';
import {
  CallVerdict,
  CustomerMessage,
  CustomerOverview,
  CustomerPromise,
  Received,
  SignInOption,
} from '../live/types';

const ROUTES = ['/home', '/messages', '/help', '/promises', '/verify'] as const;
const TABS: { route: (typeof ROUTES)[number]; label: string }[] = [
  { route: '/home', label: 'Home' },
  { route: '/messages', label: 'Messages' },
  { route: '/help', label: 'Get help' },
  { route: '/promises', label: 'Our promises' },
  { route: '/verify', label: 'Is this Westpac?' },
];
const OPTION_WORDS: Record<string, string> = {
  PAUSE_REPAYMENTS: 'Pause your repayments for a while',
  REDUCE_REPAYMENTS: 'Reduce your repayments',
  BOOK_CALL: 'Talk to someone who can help',
};

export function CustomerApp() {
  const [customerId, setCustomerId] = useRemembered('guardian.customer');
  const [route, go] = useHashRoute(ROUTES, '/home');
  const [helpMode, setHelpMode] = useState<'form' | 'callback'>('form');
  const signOut = () => {
    setCustomerId(null);
    go('/home');
  };
  const openHelp = (mode: 'form' | 'callback') => {
    setHelpMode(mode);
    go('/help');
  };

  return (
    <div className="flex min-h-screen flex-col bg-background-pale">
      <Header brand="wbc" logoLink="#/home" logoAssistiveText="Westpac app home" skipToContentId="#main">
        {customerId && (
          <Button look="link" size="small" onClick={signOut}>
            Sign out
          </Button>
        )}
      </Header>
      <main id="main" className="mx-auto w-full max-w-xs flex-1 px-2 py-3">
        {!customerId ? (
          <SignIn onSignIn={setCustomerId} />
        ) : (
          <>
            <Tabs route={route} customerId={customerId} />
            {route === '/home' && <Home customerId={customerId} />}
            {route === '/messages' && <Messages customerId={customerId} openHelp={openHelp} />}
            {route === '/help' && <GetHelp customerId={customerId} mode={helpMode} setMode={setHelpMode} />}
            {route === '/promises' && <Promises customerId={customerId} />}
            {route === '/verify' && <VerifyCall customerId={customerId} />}
          </>
        )}
      </main>
      <Footer brand="wbc" logoAssistiveText="Westpac">
        <p className="typography-body-10">Westpac app · demo for the Customer Guardian prototype · fake customers only</p>
      </Footer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sign in and navigation
// ---------------------------------------------------------------------------
function SignIn({ onSignIn }: { onSignIn: (id: string) => void }) {
  const options = useApi<SignInOption[]>('/api/customer/sign-in-options', { refetch: false });
  const [pick, setPick] = useState('');
  const chosen = pick || options.data?.[0]?.customer_id || '';
  return (
    <Panel heading="Sign in" headingTag="h1">
      <PanelBody>
        <p className="mb-2 typography-body-9">Welcome to the Westpac app.</p>
        <Alert look="info" className="mb-3">
          Demo sign-in: no passwords. Pick one of the fake customers.
        </Alert>
        {options.error && <ErrorAlert error={options.error} />}
        <form
          aria-label="Sign in"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            if (chosen) onSignIn(chosen);
          }}
        >
          <Field label="Customer">
            <Select value={chosen} onChange={e => setPick(e.target.value)} width="full" data-testid="sign-in-customer">
              {(options.data ?? []).map(o => (
                <option key={o.customer_id} value={o.customer_id}>
                  {o.full_name}
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
  );
}

function Tabs({ route, customerId }: { route: string; customerId: string }) {
  const inbox = useApi<CustomerMessage[]>(`/api/customer/messages?customer_id=${customerId}`);
  const count = inbox.data?.length ?? 0;
  return (
    <nav aria-label="App" className="mb-3 flex flex-wrap gap-1">
      {TABS.map(t => (
        <Button
          key={t.route}
          tag="a"
          href={`#${t.route}`}
          size="small"
          look={route === t.route ? 'primary' : 'faint'}
          soft={route !== t.route}
          aria-current={route === t.route ? 'page' : undefined}
        >
          {t.label}
          {t.route === '/messages' && count > 0 && (
            <Badge color="danger" type="pill" tag="span" className="ml-1" data-testid="message-count">
              {count}
            </Badge>
          )}
        </Button>
      ))}
    </nav>
  );
}

function Card({ children, testId }: { children: ReactNode; testId?: string }) {
  return (
    <div className="mb-2 rounded-2xl border border-border-muted-soft bg-background-white p-3" data-testid={testId}>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Home: accounts and recent transactions (the customer's own data)
// ---------------------------------------------------------------------------
function Home({ customerId }: { customerId: string }) {
  const meta = useMeta();
  const overview = useApi<CustomerOverview>(`/api/customer/overview?customer_id=${customerId}`, { refetch: false });
  const o = overview.data;
  if (overview.error) return <ErrorAlert error={overview.error} />;
  if (!o) return <Loading />;
  return (
    <>
      <Heading size={6} tag="h1" className="mb-2" data-testid="greeting">
        {greeting(meta.data?.now)}, {o.first_name}
      </Heading>
      <p className="mb-1 typography-body-9 font-bold">Your accounts</p>
      {o.accounts.map(a => (
        <Card key={a.account_type} testId={`account-${a.account_type}`}>
          <div className="flex items-baseline justify-between gap-2">
            <span className="typography-body-9 font-bold text-text-heading">{a.name}</span>
            <span className={`typography-body-8 font-bold ${a.balance < 0 ? 'text-text-danger' : 'text-text-heading'}`}>
              {money(a.balance)}
            </span>
          </div>
          <p className="typography-body-10 text-text-muted">
            BSB {a.bsb} · {a.number}
          </p>
        </Card>
      ))}
      <p className="mt-3 mb-1 typography-body-9 font-bold">Recent transactions</p>
      <div className="rounded-2xl border border-border-muted-soft bg-background-white" data-testid="transactions">
        {o.transactions.map((t, i) => (
          <div key={i} className="flex items-start justify-between gap-2 border-b border-border-muted-soft px-3 py-2 last:border-b-0">
            <div className="min-w-0">
              <p className="typography-body-10 break-words text-text-body">{t.description}</p>
              <p className="typography-body-10 text-text-muted">
                {friendly(t.date)} · {t.account}
              </p>
            </div>
            <span className={`shrink-0 typography-body-10 font-bold ${t.amount < 0 ? 'text-text-body' : 'text-text-success'}`}>
              {t.amount > 0 ? '+' : ''}
              {money(t.amount)}
            </span>
          </div>
        ))}
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Messages: the inbox
// ---------------------------------------------------------------------------
function Messages({ customerId, openHelp }: { customerId: string; openHelp: (mode: 'form' | 'callback') => void }) {
  const inbox = useApi<CustomerMessage[]>(`/api/customer/messages?customer_id=${customerId}`);
  const messages = inbox.data ?? [];
  return (
    <>
      <Heading size={6} tag="h1" className="mb-2">
        Messages
      </Heading>
      {inbox.error && <ErrorAlert error={inbox.error} />}
      {inbox.data && messages.length === 0 && <Alert look="info">No messages yet.</Alert>}
      {messages.length > 0 && (
        // The lock screen never shows details.
        <Alert look="info" heading="On your lock screen" className="mb-3" data-testid="lock-screen">
          {messages[0].lock_screen}
        </Alert>
      )}
      {messages.map(m => (
        <Card key={m.n} testId={`message-${m.kind}`}>
          <p className="typography-body-9 font-bold text-text-heading">{m.in_app_title}</p>
          <p className="mt-1 typography-body-10 text-text-body">{m.in_app_body}</p>
          {m.kind === 'QUIET_HELP' ? (
            <>
              <ul className="mt-2 list-disc pl-3 typography-body-10 text-text-body">
                {(m.options ?? []).map(o => (
                  <li key={o}>{OPTION_WORDS[o] ?? o}</li>
                ))}
              </ul>
              <div className="mt-2 flex flex-col gap-1">
                <Button look="primary" block onClick={() => openHelp('form')}>
                  Apply for hardship help
                </Button>
                <Button look="faint" soft block onClick={() => openHelp('callback')}>
                  Talk to someone
                </Button>
              </div>
            </>
          ) : (
            <div className="mt-2">
              <p className="typography-body-10">Your call is booked for {friendly(m.meeting_time)}.</p>
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
              <p className="mt-2 typography-body-10 text-text-muted">
                We'll say this code when we call. If a caller can't, hang up.
              </p>
            </div>
          )}
        </Card>
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// Get help: the hardship form and a call-back request
// ---------------------------------------------------------------------------
function GetHelp({
  customerId,
  mode,
  setMode,
}: {
  customerId: string;
  mode: 'form' | 'callback';
  setMode: (mode: 'form' | 'callback') => void;
}) {
  return (
    <>
      <Heading size={6} tag="h1" className="mb-2">
        Get help
      </Heading>
      <p className="mb-3 typography-body-10 text-text-muted">
        If things are tight, we can help: pausing or reducing repayments, or a call with a hardship specialist.
      </p>
      <div className="mb-3 grid grid-cols-2 gap-1">
        <Button look={mode === 'form' ? 'primary' : 'faint'} soft={mode !== 'form'} size="small" onClick={() => setMode('form')}>
          Hardship help
        </Button>
        <Button
          look={mode === 'callback' ? 'primary' : 'faint'}
          soft={mode !== 'callback'}
          size="small"
          onClick={() => setMode('callback')}
        >
          Request a call back
        </Button>
      </div>
      {mode === 'form' ? <HardshipForm customerId={customerId} /> : <CallbackForm customerId={customerId} />}
    </>
  );
}

function HardshipForm({ customerId }: { customerId: string }) {
  const [text, setText] = useState('');
  const [result, setResult] = useState<{ look: 'success' | 'danger'; text: string } | null>(null);
  const send = useAction((body: object) => post<Received>('/api/customer/hardship', body));
  return (
    <Card>
      <form
        aria-label="Apply for hardship help"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          send.mutate(
            { customer_id: customerId, text },
            {
              onSuccess: r => {
                setResult({ look: 'success', text: r.message });
                setText('');
              },
              onError: err => setResult({ look: 'danger', text: errorText(err) }),
            },
          );
        }}
      >
        <p className="mb-2 typography-body-9 font-bold text-text-heading">Apply for hardship help</p>
        <Field label="Tell us what's happening" hintMessage="For example: lost your job, reduced hours, illness, a family change.">
          <Textarea value={text} onChange={e => setText(e.target.value)} rows={5} maxLength={2000} />
        </Field>
        <p className="mt-2 typography-body-10 text-text-muted">
          We'll use the name and contact details we already have for you.
        </p>
        <Button type="submit" look="primary" block className="mt-2" disabled={send.isPending}>
          Submit my request
        </Button>
      </form>
      {result && (
        <Alert look={result.look} className="mt-2" data-testid="help-result">
          {result.text}
        </Alert>
      )}
    </Card>
  );
}

function CallbackForm({ customerId }: { customerId: string }) {
  const meta = useMeta();
  const today = (meta.data?.now ?? '2026-11-16T10:00:00').slice(0, 10);
  const inTwoDays = new Date(`${today}T12:00:00Z`);
  inTwoDays.setUTCDate(inTwoDays.getUTCDate() + 2);
  const [day, setDay] = useState<string | null>(null);
  const [time, setTime] = useState('14:00');
  const [text, setText] = useState('');
  const [result, setResult] = useState<{ look: 'success' | 'danger'; text: string } | null>(null);
  const send = useAction((body: object) => post<Received>('/api/customer/callback', body));
  const chosenDay = day ?? inTwoDays.toISOString().slice(0, 10);
  return (
    <Card>
      <form
        aria-label="Request a call back"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          send.mutate(
            { customer_id: customerId, day: chosenDay, time, text },
            {
              onSuccess: r => setResult({ look: 'success', text: r.message }),
              onError: err => setResult({ look: 'danger', text: errorText(err) }),
            },
          );
        }}
      >
        <p className="mb-2 typography-body-9 font-bold text-text-heading">Request a call back</p>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Day">
            <Input type="date" value={chosenDay} min={today} onChange={e => setDay(e.target.value)} />
          </Field>
          <Field label="Time">
            <Select value={time} onChange={e => setTime(e.target.value)} width="full">
              {['09:00', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '16:00', '17:00'].map(t => (
                <option key={t} value={t}>
                  {friendly(`2026-01-01T${t}`).split(', ')[1]}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Anything we should know? (optional)" className="mt-2">
          <Textarea value={text} onChange={e => setText(e.target.value)} rows={3} maxLength={2000} />
        </Field>
        <Button type="submit" look="primary" block className="mt-2" disabled={send.isPending}>
          Request the call
        </Button>
      </form>
      {result && (
        <Alert look={result.look} className="mt-2" data-testid="help-result">
          {result.text}
        </Alert>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Our promises to you
// ---------------------------------------------------------------------------
function Promises({ customerId }: { customerId: string }) {
  const promises = useApi<CustomerPromise[]>(`/api/customer/promises?customer_id=${customerId}`);
  return (
    <>
      <Heading size={6} tag="h1" className="mb-2">
        Our promises to you
      </Heading>
      <p className="mb-3 typography-body-10 text-text-muted">What we've told you we'll do, and by when.</p>
      {promises.error && <ErrorAlert error={promises.error} />}
      {promises.data && promises.data.length === 0 && <Alert look="info">Nothing outstanding right now.</Alert>}
      {(promises.data ?? []).map(p => (
        <Card key={`${p.kind}-${p.due}`} testId="promise">
          <p className="typography-body-9 text-text-heading">{p.text}</p>
        </Card>
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// Is this call really Westpac?
// ---------------------------------------------------------------------------
function VerifyCall({ customerId }: { customerId: string }) {
  const [code, setCode] = useState('');
  const [verdict, setVerdict] = useState<CallVerdict | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const check = useAction((body: object) => post<CallVerdict>('/api/customer/verify-call', body));
  return (
    <>
      <Heading size={6} tag="h1" className="mb-2">
        Is this call really Westpac?
      </Heading>
      <p className="mb-3 typography-body-10 text-text-muted">
        Someone says they're calling from Westpac? Ask them for your call code and type what they say.
      </p>
      <Card>
        <form
          aria-label="Check a caller"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            setVerdict(null);
            if (!code.trim()) {
              setProblem('Type the code the caller says first.');
              return;
            }
            check.mutate(
              { customer_id: customerId, code },
              {
                onSuccess: r => {
                  setVerdict(r);
                  setProblem(null);
                },
                onError: err => setProblem(errorText(err)),
              },
            );
          }}
        >
          <Field label="The code the caller says">
            <Input value={code} onChange={e => setCode(e.target.value)} maxLength={12} autoComplete="off" />
          </Field>
          <Button type="submit" look="primary" block className="mt-2" disabled={check.isPending}>
            Check
          </Button>
        </form>
      </Card>
      {problem && <Alert look="warning">{problem}</Alert>}
      {verdict && (
        <Alert
          look={verdict.genuine ? 'success' : 'danger'}
          heading={verdict.genuine ? "It's really Westpac" : "Hang up: this isn't Westpac"}
          data-testid="call-verdict"
        >
          {verdict.message}
        </Alert>
      )}
    </>
  );
}
