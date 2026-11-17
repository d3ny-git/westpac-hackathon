// The customer app (/customer/): what a Westpac customer sees in their app. Phone-first.
//   Sign in (demo) · Home (accounts, recent transactions) · Messages (Quiet Help offers that work,
//   gentle money tips for customers who haven't reached out, a booked call's call code) · Get help
//   (hardship form, call-back request) · Our promises to you · Is this call really Westpac?
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
import { FormEvent, ReactNode, useEffect, useRef, useState } from 'react';

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
// A gentle tip (the customer hasn't reached out): generic, friendly, and nothing that implies they're struggling.
const MONEY_TIPS = [
  'Set up bill reminders so nothing sneaks up on you.',
  'Check your spending by category each month to see where your money goes.',
  'Put a little aside each payday, even a small amount, for the unexpected.',
  'Turn on balance alerts so you know before your account runs low.',
];

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
            {route === '/messages' && <Messages customerId={customerId} openHelp={openHelp} openGetHelp={() => go('/help')} />}
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
  // Only messages that are new (not opened yet) and still need something from the customer.
  const count = inbox.data?.filter(m => !m.seen && !m.answered).length ?? 0;
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
function Messages({
  customerId,
  openHelp,
  openGetHelp,
}: {
  customerId: string;
  openHelp: (mode: 'form' | 'callback') => void;
  openGetHelp: () => void;
}) {
  const inbox = useApi<CustomerMessage[]>(`/api/customer/messages?customer_id=${customerId}`);
  const messages = inbox.data ?? [];
  const markSeen = useAction((ids: string[]) => post('/api/customer/messages/seen', { customer_id: customerId, ids }));
  // Messages that were new while this screen was open keep their "New" label until you leave it.
  const fresh = useRef(new Set<string>());
  const [, redraw] = useState(0);
  const [showEarlier, setShowEarlier] = useState(false);
  const [tipsOpen, setTipsOpen] = useState<string | null>(null); // the tip whose money tips are showing
  const notNow = (id: string) => {
    // "Not now": the message is seen (no New label, no badge), and that's all.
    fresh.current.delete(id);
    setTipsOpen(null);
    redraw(n => n + 1);
    markSeen.mutate([id]);
  };

  useEffect(() => {
    const unseen = messages.filter(m => !m.seen && !fresh.current.has(m.id)).map(m => m.id);
    if (unseen.length === 0) return;
    unseen.forEach(id => fresh.current.add(id));
    redraw(n => n + 1);
    markSeen.mutate(unseen); // clears the badge
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inbox.data]);

  const current = messages.filter(m => !m.answered);
  const earlier = messages.filter(m => m.answered);
  const hasNew = current.some(m => fresh.current.has(m.id));
  return (
    <>
      <Heading size={6} tag="h1" className="mb-2">
        Messages
      </Heading>
      {inbox.error && <ErrorAlert error={inbox.error} />}
      {inbox.data && current.length === 0 && (
        <Alert look="info">{earlier.length ? "You're all caught up." : 'No messages yet.'}</Alert>
      )}
      {hasNew && (
        // The lock screen never shows details.
        <Alert look="info" heading="On your lock screen" className="mb-3" data-testid="lock-screen">
          {current[0].lock_screen}
        </Alert>
      )}
      {current.map(m =>
        m.kind === 'QUIET_HELP' && m.variant === 'TIP' ? (
          <TipCard
            key={m.id}
            message={m}
            isNew={fresh.current.has(m.id)}
            tipsOpen={tipsOpen === m.id}
            onSeeTips={() => setTipsOpen(m.id)}
            onNotNow={() => notNow(m.id)}
            openGetHelp={openGetHelp}
          />
        ) : (
          <Card key={m.id} testId={`message-${m.kind}`}>
            <p className="flex items-center gap-1 typography-body-9 font-bold text-text-heading">
              {m.in_app_title}
              {fresh.current.has(m.id) && (
                <Badge color="danger" type="pill" tag="span" data-testid="message-new">
                  New
                </Badge>
              )}
            </p>
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
        ),
      )}
      {earlier.length > 0 && (
        <div className="mt-3" data-testid="earlier-messages">
          <Button look="faint" soft size="small" onClick={() => setShowEarlier(v => !v)} aria-expanded={showEarlier}>
            {showEarlier ? 'Hide' : 'Show'} earlier messages ({earlier.length})
          </Button>
          {showEarlier &&
            earlier.map(m => (
              <Card key={m.id} testId={`earlier-${m.kind}`}>
                <p className="typography-body-9 font-bold text-text-muted">{m.in_app_title}</p>
                <p className="mt-1 typography-body-10 text-text-muted">
                  You asked for help on {m.answered_on}. We'll be in touch: see Our promises.
                </p>
              </Card>
            ))}
        </div>
      )}
    </>
  );
}

// A gentle tip: calmer and informational. No hardship wording and no "Apply for hardship help" button:
// this customer hasn't asked for help, so nothing suggests they're struggling. "See money tips" opens
// a few generic tips (with a quiet link to Get help); "Not now" just marks it seen.
function TipCard({
  message: m,
  isNew,
  tipsOpen,
  onSeeTips,
  onNotNow,
  openGetHelp,
}: {
  message: CustomerMessage;
  isNew: boolean;
  tipsOpen: boolean;
  onSeeTips: () => void;
  onNotNow: () => void;
  openGetHelp: () => void;
}) {
  return (
    <div className="mb-2 rounded-2xl border border-border-muted-soft bg-surface-info-faint p-3" data-testid="message-TIP">
      <p className="mb-1 typography-body-10 font-bold text-text-info">Money tip</p>
      <p className="flex items-center gap-1 typography-body-9 font-bold text-text-heading">
        {m.in_app_title}
        {isNew && (
          <Badge color="info" soft type="pill" tag="span" data-testid="message-new">
            New
          </Badge>
        )}
      </p>
      <p className="mt-1 typography-body-10 text-text-body">{m.in_app_body}</p>
      {tipsOpen ? (
        <div className="mt-2 rounded-xl bg-background-white p-2" data-testid="money-tips">
          <p className="mb-1 typography-body-10 font-bold text-text-heading">A few money tips</p>
          <ul className="list-disc pl-3 typography-body-10 text-text-body">
            {MONEY_TIPS.map(t => (
              <li key={t}>{t}</li>
            ))}
          </ul>
          <p className="mt-2 typography-body-10 text-text-muted">
            Need help?{' '}
            <Button look="link" size="small" className="p-0" onClick={openGetHelp}>
              Get help
            </Button>
          </p>
          <Button look="faint" soft size="small" className="mt-1" onClick={onNotNow}>
            Close
          </Button>
        </div>
      ) : (
        <div className="mt-2 grid grid-cols-2 gap-1">
          <Button look="primary" soft size="small" onClick={onSeeTips}>
            See money tips
          </Button>
          <Button look="faint" soft size="small" onClick={onNotNow}>
            Not now
          </Button>
        </div>
      )}
    </div>
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
