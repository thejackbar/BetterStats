import { useState, useEffect, useCallback } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import { PbSpinner } from '../../lib/presskit'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import { Button, Badge, Note, StatCard, SectionHeading, TONES } from '../../components/admin/ui'
import { GROUPS, matchPageUrl, fmtDate } from '../../components/admin/cardReview/shared'

const ORDER = ['agree', 'small', 'differ', 'pairing', 'nocard']
const INK = { agree: TONES.ok.hex, small: '#7fb0ff', differ: TONES.warn.hex, pairing: TONES.block.hex, nocard: 'var(--pb-dim)' }
const NEXT = {
  agree: 'Show Cricket Australia where the scores agree',
  small: 'Skim and confirm',
  differ: 'Needs a decision',
  pairing: 'Check the pairing first',
  nocard: 'Stays as the club scorecard',
}

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
function BulkModal({ onClose, onDone }) {
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

  const agreeLeft = data.groups.agree
  return (
    <BetterStatsLayout
      {...header}
      actions={<Button as="a" href={api.cardReviewExportUrl()} data-testid="export-link">Download the spreadsheet</Button>}
    >
      <p className="max-w-[760px] text-[13.5px] text-pb-dim mb-5">
        These matches exist in two versions: the Cricket Australia scorecard and the club's own scorecard (imported from a file,
        typed in, or read from a photo). One is shown on the site. This page shows which, and helps you choose without opening every match.
      </p>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5 mb-6" data-testid="groups">
        {ORDER.map(g => (
          <div key={g} className="flex flex-col rounded-[10px] border border-pb-hairline bg-pb-surface px-4 py-3.5">
            <StatCard value={data.groups[g].toLocaleString()} label={GROUPS[g].label} ink={INK[g]} className="!p-0 !border-0 !bg-transparent" />
            <p className="mt-2 flex-1 text-[12px] leading-[1.45] text-pb-dim">{GROUPS[g].blurb}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Badge toneKey={GROUPS[g].tone}>{NEXT[g]}</Badge>
            </div>
            <div className="mt-3">
              {g === 'agree' && agreeLeft > 0
                ? <Button variant="primary" size="sm" onClick={() => setBulk(true)} data-testid="preview-switch">Preview the switch</Button>
                : <Button size="sm" disabled={data.groups[g] === 0 || g === 'nocard'} onClick={() => navigate(`/admin/card-review/${g}`)}>
                    {g === 'nocard' ? 'Nothing to do' : 'Open the list'}
                  </Button>}
            </div>
          </div>
        ))}
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
      {bulk && <BulkModal onClose={() => setBulk(false)} onDone={() => { setBulk(false); load() }} />}
    </BetterStatsLayout>
  )
}
