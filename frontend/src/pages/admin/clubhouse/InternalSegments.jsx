import { Link } from 'react-router-dom'
import { api } from '../../../lib/api'
import BetterClubhouseLayout from '../../../components/admin/BetterClubhouseLayout'
import {
  Button, Note, Badge, Empty, Toast,
} from '../../../components/admin/ui'
import { DIRECTORY_FIELD_DEFS } from '../bettercomms/segmentFields'
import { CrudPanes, DetailPane } from './crudShell'
import {
  useSegments, RuleBuilder, SegmentListPane, SegmentTitleRow, SegmentRefPicker, segmentKind,
  DefinitionSection,
} from './segmentEngine'
import {
  StaticMembersProvider, SegmentTiles, StaticPicker, SegmentContactLists,
} from './StaticMembers'

// BetterCricket's own outreach segments, against the Clubs Directory.
//
// This is the other mount of the segment builder. It targets PROSPECT clubs by
// what they have done — exported, emailed, opened, enquired, trialing, customer
// status, engagement score — which is BetterCricket's sales telemetry.
//
// It used to be a separate page outside the module entirely
// (/admin/super/directory-audiences, on the plain admin chrome), so choosing
// Segments in internal mode threw you out of BetterAdmin and into a screen
// that looked nothing like the one beside it. It is a Clubhouse screen now, on
// the same shell, the same builder and the same endpoints as the club mount —
// the server already resolves a segment against whichever organisation you are
// acting as, so nothing had to change on the back end to bring it in.
//
// ⚠ This file imports DIRECTORY_FIELD_DEFS and is the only screen that does.
// Reaching it requires acting as the outreach org: SegmentsRoute picks between
// this and ClubhouseSegments once, on `is_marketing_org`, and lazily, so a club
// session never even fetches this chunk. See
// docs/design_handoff_betterclubhouse/PROJECT_RULES.md.


export default function InternalSegments() {
  const s = useSegments({ defs: DIRECTORY_FIELD_DEFS })

  return (
    <BetterClubhouseLayout
      title="Segments"
      caption={`Prospect clubs · ${s.segments?.length || 0} saved`}
      actions={<Button variant="primary" onClick={() => s.startNew()}>New segment</Button>}
      bare
    >
      <CrudPanes>
        <SegmentListPane
          segments={s.segments} sizes={s.sizes} selId={s.selId} onSelect={s.setSelId}
          emptyText="No segments yet. Start one and it counts as you build it."
        >
          <Note toneKey="calm">
            A segment can be a live rule over the Clubs Directory, a hand-picked set of clubs, or both. Browse
            the directory in{' '}
            <Link to="/admin/clubhouse/internal/directory" className="underline" style={{ color: 'var(--pb-accent-ink)' }}>Directory</Link>.
          </Note>
          <Note title="BetterCricket's own contacts" toneKey="calm">
            These conditions read the Clubs Directory — what a prospect club has done, its status and its
            engagement score. A club never sees these fields; their own Segments screen reads their members
            and nothing else.
          </Note>
        </SegmentListPane>

        <DetailPane>
          {!s.draft ? (
            <Empty>Pick a segment, or start a new one.</Empty>
          ) : (
            <StaticMembersProvider
              segmentId={s.draft.id}
              audienceContacts={s.contacts} inCount={s.total} outCount={s.outCount}
              reachable={s.reachable} otherRoute={s.otherRoute} clubs={s.clubs}
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
                    blurb="A live rule over the directory, a hand-picked set, or both — the audience is everyone in either."
                    actions={<>
                      <Badge toneKey={kind.tone}>{kind.label}</Badge>
                      {s.draft.id && (
                        <Button size="sm" as="a" href={api.commsSegmentExportCsvUrl(s.draft.id)}
                          title="Download this segment's current contacts">Export CSV</Button>
                      )}
                    </>}
                  />
                )
              })()}

              {s.error && <Note toneKey="block" className="mt-4">{s.error}</Note>}

              <div className="mt-6"><SegmentTiles /></div>

              <DefinitionSection title="Active rules (live)" className="mt-5">
                <RuleBuilder defs={DIRECTORY_FIELD_DEFS} rules={s.draft.rules} opts={s.opts}
                  label="Match prospect clubs where these are true"
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

              <SegmentContactLists />
            </StaticMembersProvider>
          )}
        </DetailPane>
      </CrudPanes>
      <Toast toast={s.toast} onClose={() => s.setToast(null)} />
    </BetterClubhouseLayout>
  )
}
