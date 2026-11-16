// Home (plan E4): the A, B → C → D → E pipeline with live counts per node, and the SPEC's 10-step
// story as a guide that ticks itself as steps happen in the ledger (worked out by api/story.py).
// Staff still click Approve / Execute themselves: the guide only points the way.
import { Alert } from '@westpac/ui/alert';
import { Badge } from '@westpac/ui/badge';
import { Button } from '@westpac/ui/button';
import { ArrowRightIcon } from '@westpac/ui/icon';
import { ProgressBar } from '@westpac/ui/progress-bar';
import { ProgressRope } from '@westpac/ui/progress-rope';
import { ReactNode } from 'react';

import { Pipeline, Story, StoryStep, useApi, useMeta, useStory } from '../api';
import { Caption, ErrorAlert, Loading, PageTitle, Section, when } from '../components';
import { DemoControlsPanel } from '../DemoControls';

export function HomePage() {
  const meta = useMeta();
  return (
    <>
      <PageTitle title="Customer Guardian" subtitle="Spotting financial hardship early, and helping quietly">
        No PII anywhere: customers are only ever tokens. Nodes A–D are plain rules; the AI only follows runbooks and
        explains. A person approves every action. Demo time: {when(meta.data?.now)}
      </PageTitle>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <PipelineSection />
          <StorySection />
        </div>
        <div>
          <DemoControlsPanel />
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// The pipeline
// ---------------------------------------------------------------------------
function Node({ id, name, children, href }: { id: string; name: string; children: ReactNode; href?: string }) {
  return (
    <div className="flex-1 rounded-xl border border-border-muted-soft bg-background-white p-2" data-testid={`node-${id}`}>
      <div className="flex items-center gap-1">
        <Badge color="hero" tag="span">
          {id}
        </Badge>
        {href ? (
          <a href={href} className="typography-body-9 font-bold text-text-link underline">
            {name}
          </a>
        ) : (
          <span className="typography-body-9 font-bold text-text-heading">{name}</span>
        )}
      </div>
      <ul className="mt-1 typography-body-10 text-text-body">{children}</ul>
    </div>
  );
}

const Count = ({ n, label }: { n: number | string; label: string }) => (
  <li>
    <strong>{n}</strong> {label}
  </li>
);

function Arrow() {
  return (
    <div className="hidden items-center md:flex" aria-hidden="true">
      <ArrowRightIcon size="small" color="muted" />
    </div>
  );
}

function PipelineSection() {
  const p = useApi<Pipeline>('/api/demo/pipeline');
  const d = p.data;
  return (
    <Section title="The pipeline" caption="A → B → C → D → E, live from the clean data and the ledger. A and B both send scores to C; every action gets written back to C.">
      {p.error && <ErrorAlert error={p.error} />}
      {!d ? (
        <Loading />
      ) : (
        <div className="flex flex-col gap-2 md:flex-row">
          <Node id="A" name="Account" href="#/account">
            <Count n={d.A.clean_transactions ?? '–'} label="clean transactions" />
            <Count n={d.A.account_scores} label="account scores" />
          </Node>
          <Arrow />
          <Node id="B" name="Interactions" href="#/interactions">
            <Count n={d.B.clean_interactions ?? '–'} label="clean interactions" />
            <Count n={d.B.interaction_scores} label="interaction scores" />
            <Count n={d.B.promises} label="promises / requests" />
          </Node>
          <Arrow />
          <Node id="C" name="Ledger" href="#/ledger">
            <Count n={d.C.entries} label="entries" />
            <li>
              Chain{' '}
              {d.C.valid ? (
                <Badge color="success" soft tag="span">
                  verified
                </Badge>
              ) : (
                <Badge color="danger" tag="span">
                  tampered
                </Badge>
              )}
            </li>
            <Count n={d.C.open_promises} label="open promises" />
            <Count n={d.C.quiet_help} label="on Quiet Help list" />
          </Node>
          <Arrow />
          <Node id="D" name="Policy" href="#/policy">
            <Count n={d.D.recommendations} label="recommendations" />
            <Count n={d.D.deadline_alerts} label="deadline alerts (P1)" />
            <Count n={d.D.allowed} label="allowed" />
            <Count n={d.D.blocked} label="blocked" />
          </Node>
          <Arrow />
          <Node id="E" name="Actions" href="#/actions">
            <Count n={d.E.awaiting_approval} label="awaiting approval" />
            <Count n={d.E.approved} label="approved, to execute" />
            <Count n={d.E.done} label="done" />
            <Count n={d.E.messages_sent} label="messages to customers" />
          </Node>
        </div>
      )}
    </Section>
  );
}

// ---------------------------------------------------------------------------
// The 10-step story
// ---------------------------------------------------------------------------
function StepText({ step }: { step: StoryStep }) {
  return (
    <span className="flex flex-col items-start text-left" data-testid={`story-step-${step.n}`} data-done={step.done}>
      <span>
        {step.n}. <strong>{step.route}</strong> · {step.title}{' '}
        {step.done && (
          <Badge color="success" soft type="pill" tag="span">
            Done
          </Badge>
        )}
      </span>
      {step.detail && <span className="typography-body-10 text-text-muted">{step.detail}</span>}
    </span>
  );
}

function StorySection() {
  const story = useStory();
  const s: Story | undefined = story.data;
  return (
    <Section
      title="The story: one customer, start to finish"
      caption="The SPEC's 10 steps for hero (cust_af4200). Each one ticks itself when it shows up in the ledger; you still click Approve and Execute yourself."
    >
      {story.error && <ErrorAlert error={story.error} />}
      {!s ? (
        <Loading />
      ) : (
        <>
          <div className="mb-2" data-testid="story-progress" data-done-count={s.done_count}>
            <p className="mb-1 typography-body-9">
              <strong>
                {s.done_count} of {s.total}
              </strong>{' '}
              steps done
            </p>
            <ProgressBar value={Math.round((s.done_count / s.total) * 100)} aria-label="Story progress" noLabel />
          </div>
          {s.complete ? (
            <Alert look="success" heading="All 10 steps done" data-testid="story-next">
              The default notice was blocked by P2 and the scam call by P3. Reset the demo to play it again.
            </Alert>
          ) : (
            s.next && (
              <Alert look="info" heading={`Next: step ${s.current}`} data-testid="story-next">
                <p>
                  Go to <strong>{s.next.page}</strong> and do this: {s.next.text}
                </p>
                <Button tag="a" href={`#${s.next.path}`} look="primary" size="small" className="mt-1" iconAfter={ArrowRightIcon}>
                  Go to {s.next.page}
                </Button>
              </Alert>
            )
          )}
          <div className="mt-3 rounded-xl border border-border-muted-soft bg-background-white p-2">
            <ProgressRope
              key={s.current ?? 'complete'}
              aria-label="The 10-step story"
              current={s.current === null ? s.total : s.current - 1}
              data={s.steps.map(step => ({ text: <StepText step={step} /> }))}
            />
          </div>
          <Caption>Steps can tick out of order (for example, step 9 before step 8): each tick only says what the ledger shows.</Caption>
        </>
      )}
    </Section>
  );
}
