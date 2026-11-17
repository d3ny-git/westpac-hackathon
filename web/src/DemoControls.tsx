// The demo controls, in one shared panel (the Streamlit pages' sidebars, in one place):
//   - Reset demo (real pipeline): raw data -> sanitize -> Nodes A and B -> a fresh ledger (the default start)
//   - Start empty: sanitize + a fresh ledger, then run A and B yourself on their pages
//   - Load mock fixtures (stages start / full, straight from mock_input_output)
//   - Record a checkpoint, simulate an insider edit
// Hero's hardship form (SPEC step 6) is submitted on the Interactions (B) page's mock input form.
import { Alert } from '@westpac/ui/alert';
import { Button } from '@westpac/ui/button';
import { Collapsible } from '@westpac/ui/collapsible';
import { Field } from '@westpac/ui/field';
import { Panel, PanelBody } from '@westpac/ui/panel';
import { ProgressIndicator } from '@westpac/ui/progress-indicator';
import { Select } from '@westpac/ui/select';
import { useState } from 'react';

import { ResetReport, errorText, post, useAction, useMeta, useStatus } from './api';
import { Caption } from './components';

type Note = { look: 'success' | 'warning' | 'danger'; text: string };

export function DemoControlsBody() {
  const meta = useMeta();
  const status = useStatus();
  const [stage, setStage] = useState('start');
  const [note, setNote] = useState<Note | null>(null);
  const empty = (status.data?.count ?? 0) === 0;
  const submitted = status.data?.hero_form_submitted ?? false;

  const done = (look: Note['look'], text: string) => setNote({ look, text });
  const failed = (error: unknown) => done('danger', errorText(error));
  const reset = useAction((startEmpty: boolean) => post<ResetReport>('/api/demo/reset', { empty: startEmpty }));
  const load = useAction((s: string) => post<{ added: number }>('/api/demo/load', { stage: s }));
  const checkpoint = useAction(() => post('/api/ledger/checkpoint'));
  const tamper = useAction(() => post<{ changed: string }>('/api/demo/tamper'));
  const busy = reset.isPending || load.isPending || checkpoint.isPending || tamper.isPending;

  return (
    <div className="flex flex-col gap-2">
      <Button
        look="primary"
        block
        disabled={busy}
        onClick={() =>
          reset.mutate(false, {
            onSuccess: r =>
              done('success', `Demo reset: A and B scored everyone (${r.entries} ledger entries, ${r.promises} promises).`),
            onError: failed,
          })
        }
      >
        Reset demo (real pipeline)
      </Button>
      <Caption>Raw data → sanitize → Node A and Node B → a fresh ledger, with a PII self-check.</Caption>

      <Button
        look="hero"
        soft
        block
        disabled={busy}
        onClick={() =>
          reset.mutate(true, {
            onSuccess: () => done('success', 'Fresh ledger: now run Node A, then Node B.'),
            onError: failed,
          })
        }
      >
        Start empty (A and B not run yet)
      </Button>
      <Caption>Then: Account (A) → Run Node A's workflow; Interactions (B) → Run Node B for all customers.</Caption>
      {reset.isPending && (
        <div className="flex items-center gap-2" role="status">
          <ProgressIndicator size="small" label="Resetting the demo" />
          <span className="typography-body-10 text-text-muted">Running the pipeline…</span>
        </div>
      )}

      <Caption>
        {submitted
          ? "Hero's hardship form is in the ledger."
          : "SPEC step 6: hero submits a hardship form on the Interactions (B) page (Node B's mock input form)."}
      </Caption>

      <div className="mt-2 border-t border-border-muted-soft pt-2">
        <Field label="Or load mock fixtures" hintMessage="start = SPEC step 1 · full = after D's recommendations and E's actions (no A or B run)">
          <Select value={stage} onChange={e => setStage(e.target.value)} width="full" data-testid="stage-select">
            {(meta.data?.stages ?? ['start', 'full']).map(s => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </Field>
        <Button
          look="faint"
          soft
          block
          className="mt-2"
          disabled={busy}
          onClick={() =>
            load.mutate(stage, {
              onSuccess: r => done('success', `Loaded stage '${stage}' (${r.added} entries). The checkpoint was cleared.`),
              onError: failed,
            })
          }
        >
          Load mock fixtures
        </Button>
      </div>

      <div className="mt-2 flex flex-col gap-2 border-t border-border-muted-soft pt-2">
        <Button
          look="faint"
          soft
          block
          disabled={busy || empty}
          onClick={() => checkpoint.mutate(undefined, { onSuccess: () => done('success', 'Checkpoint recorded.'), onError: failed })}
        >
          Record checkpoint
        </Button>
        <Caption>Remembers the newest entry's hash, so cutting off or rebuilding history is caught later.</Caption>
        <Button
          look="faint"
          soft
          block
          disabled={busy || empty}
          onClick={() =>
            tamper.mutate(undefined, {
              onSuccess: r => done('warning', `${r.changed} was quietly edited. Reset the demo to undo.`),
              onError: failed,
            })
          }
        >
          Simulate insider edit
        </Button>
        <Caption>DEMO ONLY: removes the append-only protection and lowers the highest score.</Caption>
      </div>

      {note && (
        <Alert look={note.look} dismissible onClose={() => setNote(null)} role="status">
          {note.text}
        </Alert>
      )}
    </div>
  );
}

/** The full panel, for the Home page. */
export function DemoControlsPanel() {
  return (
    <Panel heading="Demo controls" headingTag="h2" look="faint">
      <PanelBody>
        <DemoControlsBody />
      </PanelBody>
    </Panel>
  );
}

/** The same controls, folded away at the top of the other pages. */
export function DemoControlsFold() {
  return (
    <div className="mb-4 rounded-xl border border-border-muted-soft bg-background-white p-2">
      <Collapsible text="Demo controls" size="medium">
        <div className="pt-2 md:max-w-xs">
          <DemoControlsBody />
        </div>
      </Collapsible>
    </div>
  );
}
