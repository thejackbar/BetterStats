import { useState } from 'react'
import { Link } from 'react-router-dom'
import BetterClubhouseLayout from '../../../components/admin/BetterClubhouseLayout'
import {
  Button, Note, Badge, Empty, Toast, SectionHeading, SearchInput,
  TableWrap, TableHead, TableRow, Cell,
} from '../../../components/admin/ui'
import { CLUB_FIELD_DEFS } from '../bettercomms/segmentFields'
import { CrudPanes, DetailPane, SaveRow } from './crudShell'
import { useSegments, RuleBuilder, SegmentListPane, SegmentTitleRow, CountBar, reachability } from './segmentEngine'
import ScreenIntro, { useScreenIntro, INTROS } from './intro'
import { money } from './data'

// Segments — a group of people described by a rule, not by a roll call.
//
// A segment is a set of conditions that resolves at send time and is never
// frozen: someone who joins tomorrow is in it tomorrow. That is the whole
// difference from a List, which is people picked by hand and stays as picked.
//
// Both are things an email can be addressed to. The composer calls that slot
// the AUDIENCE, and its dropdown offers the club's segments and its lists as
// the two kinds of thing an audience can be. So: an email has one audience;
// that audience is a segment or a list.
//
// ⚠ Club scope only. This file imports CLUB_FIELD_DEFS and nothing else, and
// it is the ONLY field set it can offer — `segmentEngine` takes `defs` as a
// prop and has no opinion about which. BetterCricket's own prospect fields
// (is_trialing, engagement_score, …) are sales telemetry and live in the other
// mount, InternalSegments, reached only while acting as the outreach org. See
// docs/design_handoff_betterclubhouse/PROJECT_RULES.md.

const COLS = 'minmax(180px,1fr) 160px 110px 120px'
const MIN_W = 700

// The segments Today can ask for by name when an officer follows an action.
// `audience` is still read as a fallback so a Today page served from a cached
// bundle, which still sends the old key, keeps working.
const PRESETS = {
  owing: { name: 'Owes money', rules: [{ field: 'owes_money', op: 'eq', value: 'yes' }] },
}
const presetFrom = (state) => state.segment || state.audience

export default function ClubhouseSegments() {
  // The stored key stays 'audiences' on purpose: it is what marks this screen's
  // introduction as seen, per person, and renaming it would re-show the
  // introduction to everyone who has already dismissed it.
  const intro = useScreenIntro('audiences')
  const s = useSegments({ defs: CLUB_FIELD_DEFS, presets: PRESETS, presetFrom })
  const [q, setQ] = useState('')

  if (intro.showing) {
    return (
      <BetterClubhouseLayout title="Segments"
        actions={<Button onClick={intro.dismiss}>Skip</Button>}>
        <ScreenIntro intro={INTROS.audiences} onContinue={intro.dismiss} onTurnOff={intro.turnOff} />
      </BetterClubhouseLayout>
    )
  }

  return (
    <BetterClubhouseLayout
      title="Segments"
      caption={`Resolved when you send · ${s.segments?.length || 0} saved`}
      onHelp={intro.reopen}
      twoRow
      filters={<SearchInput wide value={q} onChange={setQ} placeholder="Search segments…" />}
      actions={<Button variant="primary" onClick={() => s.startNew()}>New segment</Button>}
      bare
    >
      <CrudPanes>
        <SegmentListPane
          segments={s.segments} sizes={s.sizes} selId={s.selId} onSelect={s.setSelId} query={q}
          emptyText="No segments yet. Start one and it counts as you build it."
        >
          <Note toneKey="calm">
            A segment is a rule. For people picked by hand, use a list — both can be chosen as the audience
            when you write an email:{' '}
            <Link to="/admin/comms/contacts" className="underline" style={{ color: 'var(--pb-accent-ink)' }}>Contacts</Link>
            {' · '}
            <Link to="/admin/comms/lists" className="underline" style={{ color: 'var(--pb-accent-ink)' }}>Lists</Link>
          </Note>
          <Note title="Club scope only" toneKey="calm">
            These conditions read your own club's people — the directory, accounts, roster and email activity.
            Nothing here reaches outside the club.
          </Note>
        </SegmentListPane>

        <DetailPane>
          {!s.draft ? (
            <Empty>Pick a segment, or start a new one.</Empty>
          ) : (
            <>
              <SegmentTitleRow
                draft={s.draft} setDraft={s.setDraft} busy={s.busy} total={s.total}
                onDuplicate={s.duplicate} onEmail={s.emailThese}
                placeholder="Name this segment"
                blurb="Everyone who matches every condition below, worked out again each time you send."
              />

              <div className="mt-6">
                <RuleBuilder defs={CLUB_FIELD_DEFS} rules={s.draft.rules} opts={s.opts}
                  setRules={fn => s.setDraft(d => ({ ...d, rules: typeof fn === 'function' ? fn(d.rules) : fn }))} />
              </div>

              <CountBar counting={s.counting} total={s.total} reachable={s.reachable} otherRoute={s.otherRoute} />

              <SaveRow
                onSave={() => s.save('Segment')} busy={s.busy} error={s.error}
                saveLabel={s.busy ? 'Saving…' : s.draft.id ? 'Save changes' : 'Save segment'}
                onDelete={s.draft.id
                  ? () => s.remove(`Delete "${s.draft.name}"? Emails already sent to it are unaffected.`)
                  : null}
              />

              <SectionHeading className="mt-8 mb-2.5">Who this is, right now</SectionHeading>
              <TableWrap>
                <TableHead cols={COLS} minWidth={MIN_W}>
                  <Cell head first>Person</Cell>
                  <Cell head>In the directory as</Cell>
                  <Cell head num>Balance</Cell>
                  <Cell head last>Reachable</Cell>
                </TableHead>
                {s.contacts.length === 0 ? (
                  <div style={{ minWidth: MIN_W }}><Empty>Nobody matches these conditions yet.</Empty></div>
                ) : s.contacts.slice(0, 50).map(c => {
                  const r = reachability(c)
                  return (
                    <TableRow key={c.id || c.email} cols={COLS} minWidth={MIN_W}>
                      <Cell first>
                        <div className="truncate text-pb-text">{c.name || c.email}</div>
                        {c.name && c.email && <div className="font-mono text-[9.5px] text-pb-faint truncate">{c.email}</div>}
                      </Cell>
                      <Cell className="text-pb-dim capitalize">{c.source || '—'}</Cell>
                      <Cell num className={c.balance > 0 ? 'text-pb-amber' : 'text-pb-faintest'}>
                        {c.balance == null ? '—' : money(c.balance)}
                      </Cell>
                      <Cell last><Badge toneKey={r.tone}>{r.label}</Badge></Cell>
                    </TableRow>
                  )
                })}
              </TableWrap>
              {s.contacts.length > 50 && (
                <div className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faintest mt-2">
                  Showing the first 50 of {s.total}
                </div>
              )}
            </>
          )}
        </DetailPane>
      </CrudPanes>
      <Toast toast={s.toast} onClose={() => s.setToast(null)} />
    </BetterClubhouseLayout>
  )
}
