import { useState, useEffect, useCallback } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import { PbSpinner } from '../../lib/presskit'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import { Button, Badge, Note, StatCard, SectionHeading, TONES } from '../../components/admin/ui'
import { GROUPS, matchPageUrl, fmtDate } from '../../components/admin/cardReview/shared'

// The review goes in this order. A wrong pairing makes the comparison meaningless and, once
// fixed, moves matches into the other groups, so it is first. The matches the bulk switch can take
// come next, then the small differences, then the ones that need a real decision. The order is
// guidance: nothing is locked, and a later step can be opened at any time.
const STEPS = [
  { group: 'pairing', title: 'Check the pairings', ink: TONES.block.hex, button: 'Open the list',
    why: 'The two cards may not be the same match. Fix a wrong link first: a match moved to the right Cricket Australia game joins the groups below.' },
  { group: 'agree', title: 'Switch the matches that agree', ink: TONES.ok.hex, button: 'Preview the switch',
    why: 'Same runs, wickets and result on both. One click moves them to Cricket Australia, which usually holds the bowler and fielder names, balls faced and the opposition innings. A sample is shown first and it can be undone.' },
  { group: 'small', title: 'Skim the small differences', ink: '#7fb0ff', button: 'Open the list',
    why: 'The batting agrees. The date, extras, a bowling figure or how a batter was out differ slightly. Most are one number, and the suggestion is Cricket Australia.' },
  { group: 'differ', title: 'Decide the real differences', ink: TONES.warn.hex, button: 'Open the list',
    why: 'A batter or the winner is different. These come last because they take the longest, and the list is shorter by now.' },
]

function SeasonSplit({ s }) {
  const t = s.matches || 1
  return (
    <div className="flex h-2 w-full overflow-hidden rounded bg-pb-hairline" title={`${s.ca} Cricket Australia, ${s.club} club scorecard, ${s.hybrid} combined`}>
      <div style={{ width: `${(s.ca / t) * 100}%`, background: TONES.ok.hex }} />
      <div style={{ width: `${(s.hybrid / t) * 100}%`, background: '#3b82f6' }} />
      <div style={{ width: `${(s.club / t) * 100}%`, background: '#7a5a1a' }} />
    </div>
  )
}

// The confirmation before switching every match whose two cards agree.
function BulkModal({ onClose, onDone, pairingLeft = 0 }) {
  const toast = useToast()
  const [preview, setPreview] = useState(null)
  const [ack, setAck] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => { api.cardReviewBulkPreview().then(setPreview).catch(e => setError(e.message)) }, [])

  async function apply() {
    setBusy(true)
    try {
      const res = await api.cardReviewBulkApply()
      toast.success(`${res.switched} matches now show the Cricket Australia scorecard`)
      onDone()
    } catch (e) {
      setError(e.message)
    } finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/65 p-4 sm:pt-16" role="dialog" aria-modal="true" aria-label="Switch matches to Cricket Australia" data-testid="bulk-modal">
      <div className="w-full max-w-[860px] rounded-xl border border-pb-hairline2 bg-pb-surface p-5 sm:p-6 shadow-2xl">
        {!preview && !error && <PbSpinner message="Counting the matches…" />}
        {error && <Note toneKey="block">{error}</Note>}
        {preview && (
          <>
            <h2 className="font-display text-[20px] font-semibold text-pb-text">
              Show the Cricket Australia scorecard for {preview.matches.toLocaleString()} matches?
            </h2>
            <p className="mt-1.5 text-[13px] text-pb-dim">
              In these matches both cards have the same scores and result. Switching only changes which card the site shows.
            </p>
            {pairingLeft > 0 && (
              <div className="mt-3" data-testid="bulk-pairing-note">
                <Note toneKey="warn">
                  {pairingLeft.toLocaleString()} pairings are still unchecked. Fixing those first can add matches to this switch.
                </Note>
              </div>
            )}
            {preview.held_back > 0 && (
              <p className="mt-2 text-[12.5px] text-pb-dim" data-testid="bulk-held-back">
                {preview.held_back.toLocaleString()} more agree but are left out, because the club card holds something Cricket Australia's lacks (such as balls faced). Those need a person to choose.
              </p>
            )}
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-pb-hairline bg-pb-surface2 p-4">
                <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-pb-faint mb-2">What the site gains</div>
                <ul className="space-y-1.5 text-[13px] text-pb-text list-disc pl-4">
                  <li>Who bowled and who caught, on dismissals</li>
                  <li>Balls faced for every batter</li>
                  <li>The opposition innings and their players</li>
                  <li>Fall of wickets and partnerships as recorded live</li>
                </ul>
              </div>
              <div className="rounded-lg border border-pb-hairline bg-pb-surface2 p-4">
                <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-pb-faint mb-2">What does not change</div>
                <ul className="space-y-1.5 text-[13px] text-pb-text list-disc pl-4">
                  <li>Runs, wickets, totals and the result</li>
                  <li>The club scorecard. It stays stored and can be shown again at any time.</li>
                  <li>Any match someone has already chosen by hand</li>
                </ul>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-1.5" data-testid="bulk-seasons">
              {preview.by_season.map(s => <Badge key={s.season} toneKey="ok">{s.season} · {s.matches}</Badge>)}
            </div>
            {preview.sample.length > 0 && (
              <div className="mt-4">
                <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-pb-faint mb-1.5">
                  Spot check: {preview.sample.length} matches picked at random
                </div>
                <div className="overflow-x-auto rounded-lg border border-pb-hairline">
                  <table className="w-full text-[12.5px]">
                    <tbody>
                      {preview.sample.map(m => (
                        <tr key={m.match_id} className="border-b border-pb-hairline last:border-0">
                          <td className="px-3 py-2 whitespace-nowrap">{fmtDate(m.date)}</td>
                          <td className="px-3 py-2">{m.grade}</td>
                          <td className="px-3 py-2">v {m.opposition}</td>
                          <td className="px-3 py-2 text-right whitespace-nowrap">
                            <a className="text-pb-accent-ink hover:underline mr-3" href={matchPageUrl(m.game_id)} target="_blank" rel="noreferrer">Open Cricket Australia</a>
                            <a className="text-pb-accent-ink hover:underline" href={matchPageUrl(m.match_id)} target="_blank" rel="noreferrer">Open club card</a>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            <label className="mt-4 flex items-start gap-2 text-[13px] text-pb-text">
              <input type="checkbox" className="mt-0.5" checked={ack} onChange={e => setAck(e.target.checked)} data-testid="bulk-ack" />
              <span>I have looked at a few of the matches above. The switch is recorded as one batch, and each match in it can still be switched back on its own.</span>
            </label>
            <div className="mt-5 flex flex-wrap items-center justify-end gap-2">
              <Button onClick={onClose}>Cancel</Button>
              <Button variant="primary" disabled={!ack || busy || preview.matches === 0} onClick={apply} data-testid="bulk-apply">
                {busy ? 'Switching…' : `Switch ${preview.matches.toLocaleString()} matches to Cricket Australia`}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function Batches({ batches, onUndo, busy }) {
  if (!batches?.length) return null
  return (
    <section className="mt-8" data-testid="batches">
      <SectionHeading>Bulk switches</SectionHeading>
      <p className="text-[12.5px] text-pb-dim mt-1 mb-3">
        Each bulk switch can be undone as a batch. A match someone has changed since is left exactly as they set it.
      </p>
      <div className="rounded-xl border border-pb-hairline bg-pb-surface overflow-hidden">
        {batches.map(b => (
          <div key={b.batch_id} className="flex flex-wrap items-center gap-3 border-b border-pb-hairline px-4 py-3 last:border-0">
            <div className="min-w-0 flex-1 text-[13px] text-pb-text">
              {fmtDate(b.created_at)}: {b.matches} matches switched to Cricket Australia
              <span className="text-pb-dim"> · {b.still_switched} still switched</span>
            </div>
            <Button size="sm" disabled={busy || b.still_switched === 0} onClick={() => onUndo(b.batch_id)}>Undo this batch</Button>
          </div>
        ))}
      </div>
    </section>
  )
}

export default function AdminCardReview() {
  const navigate = useNavigate()
  const toast = useToast()
  const [data, setData] = useState(null)
  const [batches, setBatches] = useState([])
  const [error, setError] = useState(null)
  const [bulk, setBulk] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api.cardReviewOverview().then(setData).catch(e => setError(e.message))
    api.cardReviewBatches().then(r => setBatches(r.batches || [])).catch(() => {})
  }, [])
  useEffect(() => { load() }, [load])

  async function undoBatch(id) {
    if (!confirm('Put every match in this batch back as it was? A match someone has changed since is left alone.')) return
    setBusy(true)
    try {
      const r = await api.cardReviewBulkUndo(id)
      toast.success(`${r.undone} matches put back${r.left_alone?.length ? `, ${r.left_alone.length} left as someone set them` : ''}`)
      load()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  const header = {
    title: 'Card review',
    caption: data ? `${data.total.toLocaleString()} matches stored twice` : undefined,
  }
  if (error) return <BetterStatsLayout {...header}><Note toneKey="block">{error}</Note></BetterStatsLayout>
  if (!data) return <BetterStatsLayout {...header}><PbSpinner message="Comparing the two cards of every match…" /></BetterStatsLayout>

  const todo = g => data.todo?.[g] ?? data.groups[g]
  const reviewable = data.total - data.groups.nocard
  const left = STEPS.reduce((n, st) => n + todo(st.group), 0)
  const reviewed = Math.max(0, reviewable - left)
  const first = STEPS.find(st => todo(st.group) > 0)
  const go = g => (g === 'agree' ? setBulk(true) : navigate(`/admin/card-review/${g}`))
  return (
    <BetterStatsLayout
      {...header}
      actions={<Button as="a" href={api.cardReviewExportUrl()} data-testid="export-link">Download the spreadsheet</Button>}
    >
      <p className="max-w-[760px] text-[13.5px] text-pb-dim mb-5">
        These matches exist in two versions: the Cricket Australia scorecard and the club's own scorecard (imported from a file,
        typed in, or read from a photo). One is shown on the site. Work through the four steps in order and each match ends up showing the card you chose.
      </p>

      <div className="mb-5 rounded-[10px] border border-pb-hairline bg-pb-surface px-4 py-3.5" data-testid="progress">
        <div className="flex flex-wrap items-center gap-3">
          <div className="text-[13px] text-pb-text">
            <b>{reviewed.toLocaleString()}</b> of {reviewable.toLocaleString()} matches reviewed
          </div>
          {first
            ? <Button className="ml-auto" variant="primary" size="sm" onClick={() => go(first.group)} data-testid="start-here">
                Start here: {first.title.toLowerCase()}
              </Button>
            : <span className="ml-auto"><Badge toneKey="ok">All steps done</Badge></span>}
        </div>
        <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-pb-surface2" role="progressbar" aria-valuemin={0} aria-valuemax={reviewable} aria-valuenow={reviewed}>
          <div className="h-full rounded-full" style={{ width: `${reviewable ? Math.round((reviewed / reviewable) * 100) : 100}%`, background: TONES.ok.hex }} />
        </div>
      </div>

      <div data-testid="groups" className="mb-6">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {STEPS.map((st, i) => {
            const n = todo(st.group)
            const here = first && first.group === st.group
            return (
              <div key={st.group} data-testid={`step-${st.group}`} data-state={n === 0 ? 'done' : here ? 'next' : 'later'}
                className="flex flex-col rounded-[10px] border bg-pb-surface px-4 py-3.5"
                style={{ borderColor: here ? st.ink : 'var(--pb-hairline)', opacity: n === 0 ? 0.75 : 1 }}>
                <div className="mb-1 flex items-center gap-2">
                  <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-pb-faint">Step {i + 1} of {STEPS.length}</span>
                  {n === 0 ? <Badge toneKey="ok">Done</Badge> : here ? <Badge toneKey={GROUPS[st.group].tone}>Start here</Badge> : null}
                </div>
                <div className="font-display text-[15px] font-semibold text-pb-text">{st.title}</div>
                <StatCard value={data.groups[st.group].toLocaleString()} label={GROUPS[st.group].label} ink={st.ink} className="!p-0 !border-0 !bg-transparent mt-2" />
                <p className="mt-2 flex-1 text-[12px] leading-[1.45] text-pb-dim">{st.why}</p>
                {st.group === 'agree' && data.agree_club_richer > 0 && (
                  <p className="mt-2 text-[12px] leading-[1.45] text-pb-dim" data-testid="richer-note">
                    {data.agree_club_richer.toLocaleString()} of these hold something on the club card that Cricket Australia's lacks, so the switch leaves them out.{' '}
                    <Link className="underline" to="/admin/card-review/agree?richer=yes" data-testid="richer-link">Look at them</Link>
                  </p>
                )}
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Badge toneKey={n === 0 ? 'ok' : 'calm'}>{n === 0 ? 'Nothing left' : `${n.toLocaleString()} to go`}</Badge>
                </div>
                <div className="mt-3">
                  {st.group === 'agree'
                    ? <Button variant={here ? 'primary' : 'secondary'} size="sm" disabled={(data.bulk_left ?? data.groups.agree) === 0} onClick={() => setBulk(true)} data-testid="preview-switch">{st.button}</Button>
                    : <Button size="sm" variant={here ? 'primary' : 'secondary'} disabled={data.groups[st.group] === 0} onClick={() => go(st.group)}>{st.button}</Button>}
                </div>
              </div>
            )
          })}
        </div>
        <p className="mt-3 text-[12px] text-pb-dim" data-testid="nocard-note">
          {GROUPS.nocard.label}: {data.groups.nocard.toLocaleString()} matches. {GROUPS.nocard.blurb} They stay as the club scorecard and need nothing from you.
        </p>
      </div>

      <div className="mb-2 flex flex-wrap items-center gap-3">
        <SectionHeading>Progress by season</SectionHeading>
        <div className="ml-auto flex flex-wrap gap-1.5">
          <Badge toneKey="ok">Showing Cricket Australia</Badge>
          <Badge toneKey="accent">Club + CA detail</Badge>
          <Badge toneKey="warn">Showing club scorecard</Badge>
        </div>
      </div>
      <div className="overflow-x-auto rounded-xl border border-pb-hairline bg-pb-surface">
        <table className="w-full text-[13px]" data-testid="seasons">
          <thead>
            <tr className="text-left font-mono text-[10px] uppercase tracking-[0.1em] text-pb-faint">
              <th className="px-4 py-2.5 font-normal">Season</th>
              <th className="px-3 py-2.5 font-normal text-right">Matches</th>
              <th className="px-3 py-2.5 font-normal text-right">Cricket Australia</th>
              <th className="px-3 py-2.5 font-normal text-right">Club + detail</th>
              <th className="px-3 py-2.5 font-normal text-right">Club card</th>
              <th className="px-3 py-2.5 font-normal text-right">Needs a decision</th>
              <th className="px-4 py-2.5 font-normal w-[28%]">Split</th>
            </tr>
          </thead>
          <tbody>
            {data.seasons.map(s => (
              <tr key={s.season} className="border-t border-pb-hairline">
                <td className="px-4 py-2.5 text-pb-text">{s.season}</td>
                <td className="px-3 py-2.5 text-right font-mono">{s.matches}</td>
                <td className="px-3 py-2.5 text-right font-mono" style={{ color: TONES.ok.hex }}>{s.ca}</td>
                <td className="px-3 py-2.5 text-right font-mono" style={{ color: '#7fb0ff' }}>{s.hybrid}</td>
                <td className="px-3 py-2.5 text-right font-mono" style={{ color: TONES.warn.hex }}>{s.club}</td>
                <td className="px-3 py-2.5 text-right font-mono">{s.needs_decision}</td>
                <td className="px-4 py-2.5"><SeasonSplit s={s} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-[12px] text-pb-faint">
        Nothing is deleted when a version is hidden. Every match can be switched back from the list, from its own page, or from the match page itself.
        {data.decided_by_hand > 0 && <> {data.decided_by_hand} matches have been chosen by hand and are never changed by a bulk switch.</>}
      </p>

      <Batches batches={batches} onUndo={undoBatch} busy={busy} />
      {bulk && <BulkModal pairingLeft={todo('pairing')} onClose={() => setBulk(false)} onDone={() => { setBulk(false); load() }} />}
    </BetterStatsLayout>
  )
}
