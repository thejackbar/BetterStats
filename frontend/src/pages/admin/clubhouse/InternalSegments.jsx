import { Link } from 'react-router-dom'
import { api } from '../../../lib/api'
import BetterClubhouseLayout from '../../../components/admin/BetterClubhouseLayout'
import {
  Button, Note, Badge, Empty, Toast, SectionHeading,
  TableWrap, TableHead, TableRow, Cell,
} from '../../../components/admin/ui'
import { DIRECTORY_FIELD_DEFS } from '../bettercomms/segmentFields'
import { CrudPanes, DetailPane, SaveRow } from './crudShell'
import { useSegments, RuleBuilder, SegmentListPane, SegmentTitleRow, CountBar, reachability } from './segmentEngine'

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

const COLS = 'minmax(180px,1fr) minmax(150px,1fr) 90px 110px 120px'
const MIN_W = 780

const TIER_TONE = { HOT: 'ok', WARM: 'warn', COLD: 'calm' }

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
            A segment is a rule over the Clubs Directory. For clubs picked by hand, use a list. Both can be
            chosen as the audience when you write an email:{' '}
            <Link to="/admin/clubhouse/internal/directory" className="underline" style={{ color: 'var(--pb-accent-ink)' }}>Directory</Link>
            {' · '}
            <Link to="/admin/comms/lists" className="underline" style={{ color: 'var(--pb-accent-ink)' }}>Lists</Link>
          </Note>
          <Note title="BetterCricket's own contacts" toneKey="calm">
            These conditions read the Clubs Directory. What a prospect club has done, its status and its
            engagement score. A club never sees these fields; their own Segments screen reads their members
            and nothing else.
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
                blurb="Every directory contact matching every condition below, worked out again each time you send."
                actions={s.draft.id && (
                  <Button size="sm" as="a" href={api.commsSegmentExportCsvUrl(s.draft.id)}
                    title="Download this segment's current contacts">Export CSV</Button>
                )}
              />

              <div className="mt-6">
                <RuleBuilder defs={DIRECTORY_FIELD_DEFS} rules={s.draft.rules} opts={s.opts}
                  label="Match prospect clubs where all of these are true"
                  setRules={fn => s.setDraft(d => ({ ...d, rules: typeof fn === 'function' ? fn(d.rules) : fn }))} />
              </div>

              <CountBar counting={s.counting} total={s.total} reachable={s.reachable} otherRoute={s.otherRoute}
                noun="contact" nounPlural="contacts" />

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
                  <Cell head first>Contact</Cell>
                  <Cell head>Club</Cell>
                  <Cell head>State</Cell>
                  <Cell head>Engagement</Cell>
                  <Cell head last>Reachable</Cell>
                </TableHead>
                {s.contacts.length === 0 ? (
                  <div style={{ minWidth: MIN_W }}><Empty>No contacts match these conditions yet.</Empty></div>
                ) : s.contacts.slice(0, 50).map(c => {
                  const r = reachability(c)
                  return (
                    <TableRow key={c.id || c.email} cols={COLS} minWidth={MIN_W}>
                      <Cell first>
                        <div className="truncate text-pb-text">{c.name || c.email}</div>
                        {c.name && c.email && <div className="font-mono text-[9.5px] text-pb-faint truncate">{c.email}</div>}
                      </Cell>
                      <Cell className="text-pb-dim">
                        <span className="truncate block">{c.club || '—'}</span>
                        {c.association && <span className="font-mono text-[9.5px] text-pb-faintest truncate block">{c.association}</span>}
                      </Cell>
                      <Cell className="text-pb-dim">{c.state || '—'}</Cell>
                      <Cell>
                        {c.club_engagement_score == null ? <span className="text-pb-faintest">—</span> : (
                          <Badge toneKey={TIER_TONE[c.club_engagement_tier] || 'calm'}>
                            {c.club_engagement_score}{c.club_engagement_tier ? ` · ${c.club_engagement_tier}` : ''}
                          </Badge>
                        )}
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
