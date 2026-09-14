import { useState } from 'react'
import { Link } from 'react-router-dom'
import BetterClubhouseLayout from '../../../components/admin/BetterClubhouseLayout'
import {
  Button, Note, Badge, Empty, Toast, SearchInput,
} from '../../../components/admin/ui'
import { CLUB_FIELD_DEFS } from '../bettercomms/segmentFields'
import { CrudPanes, DetailPane } from './crudShell'
import {
  useSegments, RuleBuilder, SegmentListPane, SegmentTitleRow, SegmentRefPicker, segmentKind,
  DefinitionSection,
} from './segmentEngine'
import {
  StaticMembersProvider, SegmentTiles, StaticPicker, SegmentContactLists,
} from './StaticMembers'
import ScreenIntro, { useScreenIntro, INTROS } from './intro'

// Segments — a group of people an email is addressed to. There is one concept
// now, not two: a segment carries an ACTIVE part (a live rule, re-worked every
// time you send, so someone who joins tomorrow is in it tomorrow) and a STATIC
// part (a frozen roll call of contacts you picked by hand, which stays exactly
// as picked). The old "Lists" feature is the static part, moved in here.
//
// A segment can be either or both, and the final audience is the union of the
// two. The composer calls that slot the AUDIENCE; an email has one audience,
// and that audience is a segment.
//
// ⚠ Club scope only. This file imports CLUB_FIELD_DEFS and nothing else, and
// it is the ONLY field set it can offer — `segmentEngine` takes `defs` as a
// prop and has no opinion about which. BetterCricket's own prospect fields
// (is_trialing, engagement_score, …) are sales telemetry and live in the other
// mount, InternalSegments, reached only while acting as the outreach org. See
// docs/design_handoff_betterclubhouse/PROJECT_RULES.md.

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
            A segment can be a live rule, a hand-picked set, or both. Edit a person's own details in{' '}
            <Link to="/admin/comms/contacts" className="underline" style={{ color: 'var(--pb-accent-ink)' }}>Contacts</Link>.
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
            <StaticMembersProvider
              segmentId={s.draft.id}
              audienceContacts={s.contacts} inCount={s.total} outCount={s.outCount}
              reachable={s.reachable}
              onChanged={() => { s.reloadStaticMembers(s.draft.id); s.reload() }}
            >
              {(() => {
                const kind = segmentKind(s.definition.rules.length, s.staticMembers.length)
                return (
                  <SegmentTitleRow
                    draft={s.draft} setDraft={s.setDraft} busy={s.busy} total={s.total}
                    onSave={() => s.save('Segment')}
                    saveLabel={s.busy ? 'Saving…' : s.draft.id ? 'Save changes' : 'Save segment'}
                    onDelete={() => s.remove(`Delete "${s.draft.name}"? Emails already sent to it are unaffected.`)}
                    onDuplicate={s.duplicate} onEmail={s.emailThese}
                    placeholder="Name this segment"
                    blurb="A live rule, a hand-picked set, or both — the audience is everyone in either."
                    actions={<Badge toneKey={kind.tone}>{kind.label}</Badge>}
                  />
                )
              })()}

              {s.error && <Note toneKey="block" className="mt-4">{s.error}</Note>}

              {/* The two count tiles sit above the definition; each toggles its
                  own contact list at the bottom of the pane. */}
              <div className="mt-6"><SegmentTiles /></div>

              {/* Three distinct definition areas: the live rule, the frozen
                  hand-picked set, and the segments this one folds in. */}
              <DefinitionSection title="Active rules (live)" className="mt-5">
                <RuleBuilder defs={CLUB_FIELD_DEFS} rules={s.draft.rules} opts={s.opts}
                  setRules={fn => s.setDraft(d => ({ ...d, rules: typeof fn === 'function' ? fn(d.rules) : fn }))} />
              </DefinitionSection>

              <DefinitionSection title="Static members (fixed)" className="mt-4">
                <StaticPicker />
              </DefinitionSection>

              <DefinitionSection title="Include or exclude other segments" className="mt-4">
                <SegmentRefPicker
                  segments={s.segments} currentId={s.draft.id} sizes={s.sizes}
                  includes={s.draft.includes || []} excludes={s.draft.excludes || []}
                  onChange={({ includes, excludes }) => s.setDraft(d => ({ ...d, includes, excludes }))}
                />
              </DefinitionSection>

              {/* The contact lists a tile reveals, below every definition area. */}
              <SegmentContactLists />
            </StaticMembersProvider>
          )}
        </DetailPane>
      </CrudPanes>
      <Toast toast={s.toast} onClose={() => s.setToast(null)} />
    </BetterClubhouseLayout>
  )
}
