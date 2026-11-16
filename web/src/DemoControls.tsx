// The demo controls, in one shared panel: load a story stage, hero's hardship form (the same as
// Node B's form B5), record a checkpoint, simulate an insider edit. Same buttons as the Streamlit
// sidebars on ui/pages/C.py and D.py.
import { Alert } from '@westpac/ui/alert';
import { Button } from '@westpac/ui/button';
import { Collapsible } from '@westpac/ui/collapsible';
import { Field } from '@westpac/ui/field';
import { Panel, PanelBody } from '@westpac/ui/panel';
import { Select } from '@westpac/ui/select';
import { useState } from 'react';

import { errorText, post, useAction, useMeta, useStatus } from './api';
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
  const load = useAction((s: string) => post<{ added: number }>('/api/demo/load', { stage: s }));
  const heroForm = useAction(() => post('/api/demo/hero-form'));
  const checkpoint = useAction(() => post('/api/ledger/checkpoint'));
  const tamper = useAction(() => post<{ changed: string }>('/api/demo/tamper'));
  const busy = load.isPending || heroForm.isPending || checkpoint.isPending || tamper.isPending;

  return (
    <div className="flex flex-col gap-2">
      <Field
        label="Story stage"
        hintMessage="start = before hero's hardship form · full = after D's recommendations and E's actions"
      >
        <Select value={stage} onChange={e => setStage(e.target.value)} width="full" data-testid="stage-select">
          {(meta.data?.stages ?? ['start', 'full']).map(s => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </Select>
      </Field>
      <Button
        look="primary"
        block
        disabled={busy}
        onClick={() =>
          load.mutate(stage, {
            onSuccess: r => done('success', `Loaded stage '${stage}' (${r.added} entries). The checkpoint was cleared.`),
            onError: failed,
          })
        }
      >
        Load demo data
      </Button>
      <Caption>Wipes the demo ledger and loads the chosen stage.</Caption>

      <Button
        look="hero"
        soft
        block
        disabled={busy || empty || submitted}
        onClick={() =>
          heroForm.mutate(undefined, { onSuccess: () => done('success', 'Hero submitted the hardship form.'), onError: failed })
        }
      >
        Simulate: hero submits hardship form
      </Button>
      <Caption>
        {submitted
          ? "Hero's form is in the ledger."
          : "The same as hero filling in Node B's mock input form (the B page): Node B scores the form 50 and adds a 21-day hardship response promise (SPEC steps 6–7)."}
      </Caption>

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
            onSuccess: r => done('warning', `${r.changed} was quietly edited. Load demo data to undo.`),
            onError: failed,
          })
        }
      >
        Simulate insider edit
      </Button>
      <Caption>DEMO ONLY: removes the append-only protection and lowers the highest score.</Caption>

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
