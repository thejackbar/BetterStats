import { useState, useEffect, useCallback } from 'react'
import { useNavigate, useParams, useLocation, Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import { PbSpinner } from '../../lib/presskit'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import { Button, Badge, Note, TextArea, TONES } from '../../components/admin/ui'
import {
  CHOICE_NAME, GROUPS, ChoiceControl, DifferenceTable, GroupBadge, fmtDate, matchPageUrl,
} from '../../components/admin/cardReview/shared'
import { QUEUE_KEY } from './AdminCardReviewList'

const MARK = { background: 'rgba(245,181,66,0.16)', color: '#ffd88a', fontWeight: 700, borderRadius: 3, padding: '1px 6px' }
const dash = <span className="text-pb-faintest">—</span>

// One side of the comparison. Both cards draw from the same aligned rows, so a batter on one
// card only reads as a gap rather than silently vanishing, and a cell that differs is marked.
function Card({ side, m }) {
  const isCa = side === 'ca'
  const holds = isCa ? m.ca_holds : m.club_holds
  const tot = (m.totals?.[side] || []).filter(t => t.runs != null || t.extras != null)
  const bits = Object.entries(isCa
    ? { 'balls faced': holds.balls, 'dismissal credits': holds.credits, 'fall of wickets': holds.fow, partnerships: holds.partnerships, 'opposition batters': holds.opp_batters }
    : { 'balls faced': holds.balls, 'dismissal credits': holds.credits, 'fall of wickets': holds.fow, partnerships: holds.partnerships })
    .filter(([, v]) => v).map(([k, v]) => `${k} ${v}`)
  return (
    <section
      className="min-w-0 overflow-hidden rounded-xl border bg-pb-surface"
      style={{ borderColor: isCa ? 'rgba(22,199,132,0.45)' : 'rgba(245,181,66,0.45)' }}
      data-testid={`card-${side}`}
    >
      <header className="flex flex-wrap items-center gap-2.5 border-b border-pb-hairline px-4 py-3">
        <Badge toneKey={isCa ? 'ok' : 'warn'}>{isCa ? 'Cricket Australia' : 'Club scorecard'}</Badge>
        <span className="text-[13px] font-semibold text-pb-text">{isCa ? m.ca_opposition : m.club_opposition}</span>
        <span className="ml-auto font-mono text-[11px] text-pb-dim">{fmtDate(isCa ? m.ca_date : m.club_date)}</span>
      </header>
      <div className="border-b border-pb-hairline bg-pb-surface2 px-4 py-2 text-[11.5px] text-pb-faint">
        <span className="text-pb-dim">Source:</span>{' '}
        {isCa ? 'Cricket Australia, synced from the live scorecard' : (
          <>
            {m.source.label}{m.source.at ? ` · ${fmtDate(m.source.at)}` : ''}{m.source.by ? ` · by ${m.source.by}` : ''}
          </>
        )}
      </div>
      {m.innings.map(inn => (
        <div key={inn.number} className="overflow-x-auto">
          {m.innings.length > 1 && <div className="px-4 pt-3 font-mono text-[10px] uppercase tracking-[0.12em] text-pb-faint">Our innings {inn.number}</div>}
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="text-left font-mono text-[9.5px] uppercase tracking-[0.1em] text-pb-faint">
                <th className="px-4 py-2 font-normal">Batter</th>
                <th className="px-2 py-2 font-normal">How out</th>
                <th className="px-2 py-2 font-normal text-right">R</th>
                <th className="px-4 py-2 font-normal text-right">B</th>
              </tr>
            </thead>
            <tbody>
              {inn.batting.map(l => {
                const c = l[side]
                const other = l[isCa ? 'club' : 'ca']
                return (
                  <tr key={l.player_id} className="border-t border-pb-hairline">
                    <td className="px-4 py-1.5 text-pb-text">{l.name}</td>
                    {c ? (
                      <>
                        <td className="px-2 py-1.5 text-pb-dim">{c.not_out ? 'not out' : (c.how_out || dash)}</td>
                        <td className="px-2 py-1.5 text-right font-mono">{l.differs && other ? <span style={MARK}>{c.runs}</span> : c.runs}</td>
                        <td className="px-4 py-1.5 text-right font-mono text-pb-dim">{c.balls ?? dash}</td>
                      </>
                    ) : (
                      <td colSpan={3} className="px-2 py-1.5 text-right text-[11.5px] italic text-pb-faint">not on this card</td>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ))}
      {m.bowling.length > 0 && (
        <div className="overflow-x-auto border-t border-pb-hairline">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="text-left font-mono text-[9.5px] uppercase tracking-[0.1em] text-pb-faint">
                <th className="px-4 py-2 font-normal">Our bowlers</th>
                <th className="px-2 py-2 font-normal text-right">W</th>
                <th className="px-4 py-2 font-normal text-right">R</th>
              </tr>
            </thead>
            <tbody>
              {m.bowling.map(b => (
                <tr key={b.player_id} className="border-t border-pb-hairline">
                  <td className="px-4 py-1.5 text-pb-text">{b.name}</td>
                  {b[side] ? (
                    <>
                      <td className="px-2 py-1.5 text-right font-mono">{b.differs && b[isCa ? 'club' : 'ca'] ? <span style={MARK}>{b[side].wickets}</span> : b[side].wickets}</td>
                      <td className="px-4 py-1.5 text-right font-mono text-pb-dim">{b[side].runs}</td>
                    </>
                  ) : <td colSpan={2} className="px-4 py-1.5 text-right text-[11.5px] italic text-pb-faint">not on this card</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {tot.length > 0 && (
        <div className="border-t border-pb-hairline px-4 py-2 text-[12px] text-pb-dim">
          {tot.map(t => (
            <div key={t.innings}>Innings {t.innings}: {t.runs ?? '—'}{t.wickets != null ? `/${t.wickets}` : ''}{t.extras != null ? ` (extras ${t.extras})` : ''}</div>
          ))}
        </div>
      )}
      <footer className="border-t border-pb-hairline px-4 py-2.5 text-[11.5px] text-pb-dim">
        <span style={{ color: isCa ? TONES.ok.hex : TONES.warn.hex }}>{isCa ? 'Also in Cricket Australia:' : 'Also in the club scorecard:'}</span>{' '}
        {bits.length ? bits.join(', ') : 'nothing beyond the batting and bowling lines'}
      </footer>
    </section>
  )
}

function Choice({ title, tone, children, active, rec }) {
  return (
    <div className="rounded-xl border p-4" data-active={active ? 'true' : undefined}
      style={{ borderColor: rec ? 'rgba(59,130,246,.55)' : active ? tone : 'var(--pb-hairline2)', background: rec ? 'rgba(59,130,246,.06)' : 'var(--pb-surface)' }}>
      <div className="flex flex-wrap items-center gap-2 font-semibold text-[14px] text-pb-text">
        {title}
        {active && <Badge toneKey="accent">Showing now</Badge>}
      </div>
      {children}
    </div>
  )
}

function History({ rows, onUndo, busy }) {
  const undoable = rows.find(h => !h.undone_at && ['choice', 'pair_ok', 'relink', 'unlink'].includes(h.action))
  const word = h => {
    if (h.action === 'choice') return `Switched from ${CHOICE_NAME[h.from_choice] || '?'} to ${CHOICE_NAME[h.to_choice]}`
    if (h.action === 'undo') return `Undone: back to ${CHOICE_NAME[h.to_choice]}`
    if (h.action === 'refresh') return 'Refreshed the Cricket Australia detail'
    if (h.action === 'pair_ok') return 'Marked as the same match'
    if (h.action === 'relink') return 'Linked to a different Cricket Australia match'
    if (h.action === 'unlink') return 'Unlinked: two different matches'
    return h.action
  }
  return (
    <div className="rounded-xl border border-pb-hairline bg-pb-surface p-4" data-testid="history">
      <div className="mb-3 font-mono text-[10px] uppercase tracking-[0.12em] text-pb-faint">History for this match</div>
      {rows.length === 0 && <p className="text-[12.5px] text-pb-dim">No changes yet. The site shows what the import set up.</p>}
      <ol className="space-y-3 border-l-2 border-pb-hairline2 pl-4">
        {rows.map(h => (
          <li key={h.id} className={`text-[12.5px] ${h.undone_at ? 'opacity-50 line-through' : ''}`}>
            <div className="text-pb-text">{word(h)}</div>
            <div className="text-[11.5px] text-pb-dim">
              {h.username || 'Someone'}{h.source === 'bulk' ? ' (bulk switch)' : ''}, {fmtDate(h.created_at)} {h.created_at ? new Date(h.created_at).toLocaleTimeString('en-AU', { hour: 'numeric', minute: '2-digit' }) : ''}
              {h.note ? ` · "${h.note}"` : ''}
            </div>
          </li>
        ))}
      </ol>
      <div className="mt-3">
        <Button size="sm" disabled={!undoable || busy} onClick={onUndo} data-testid="undo">Undo the last change</Button>
      </div>
    </div>
  )
}

export default function AdminCardReviewMatch() {
  const { matchId } = useParams()
  const { hash } = useLocation()
  const navigate = useNavigate()
  const toast = useToast()
  const [m, setM] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [preview, setPreview] = useState(null)
  const [previewing, setPreviewing] = useState(false)
  const [showAll, setShowAll] = useState(false)

  const load = useCallback(() => {
    setM(null); setPreview(null); setError(null)
    api.cardReviewMatch(matchId).then(setM).catch(e => setError(e.message))
  }, [matchId])
  useEffect(() => { load() }, [load])

  const loadPreview = useCallback(async () => {
    setPreviewing(true)
    try { setPreview(await api.cardReviewPreview(matchId)) } catch (e) { toast.error(e.message) } finally { setPreviewing(false) }
  }, [matchId, toast])
  useEffect(() => { if (hash === '#hybrid' && m && !preview && !previewing) loadPreview() }, [hash, m]) // eslint-disable-line react-hooks/exhaustive-deps

  async function run(fn, ok) {
    setBusy(true)
    try {
      const res = await fn()
      if (res.match) setM(res.match)
      if (ok) toast.success(ok(res))
      setNote('')
      return res
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  const choose = key => run(() => api.cardReviewChoose(matchId, key, note), r => {
    const n = (r.left_out || []).length
    return `Now showing ${CHOICE_NAME[key]}${key === 'hybrid' && n ? `. ${n} item${n === 1 ? '' : 's'} left out` : ''}`
  })

  let queue = null
  try { queue = JSON.parse(sessionStorage.getItem(QUEUE_KEY) || 'null') } catch { queue = null }
  const at = queue ? queue.ids.indexOf(matchId) : -1
  const go = i => queue && queue.ids[i] && navigate(`/admin/card-review/match/${queue.ids[i]}`)

  if (error) return <BetterStatsLayout title="Card review"><Note toneKey="block">{error}</Note></BetterStatsLayout>
  if (!m) return <BetterStatsLayout title="Card review"><PbSpinner message="Opening both cards…" /></BetterStatsLayout>

  const inconsistent = m.group === 'nocard'
  const diffHeadline = m.items.length
    ? `${m.items.length} difference${m.items.length === 1 ? '' : 's'}: ${m.headline}${m.items.length > 1 ? ` and ${m.items.length - 1} more` : ''}.`
    : 'The two cards agree on every figure.'
  return (
    <BetterStatsLayout
      title={`${m.grade || 'Match'} v ${m.opposition || ''}`}
      caption={`${fmtDate(m.date)} · ${m.season || ''}`}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          {at >= 0 && <span className="font-mono text-[11px] text-pb-faint" data-testid="position">{at + 1} of {queue.ids.length}</span>}
          <Button size="sm" disabled={at <= 0} onClick={() => go(at - 1)}>‹ Previous</Button>
          <Button size="sm" disabled={at < 0 || at >= queue.ids.length - 1} onClick={() => go(at + 1)}>Next ›</Button>
          <Button size="sm" as={Link} to={`/admin/card-review/${m.group === 'agree' ? 'agree' : m.group}`}>Back to the list</Button>
        </div>
      }
    >
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <GroupBadge group={m.group} />
        <span className="text-[12.5px] text-pb-dim">{GROUPS[m.group].blurb}</span>
        <div className="ml-auto flex min-w-0 max-w-full flex-wrap items-center gap-2">
          <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-pb-faint">Showing on the site now</span>
          <ChoiceControl value={m.current} labelFor="label" disabled={busy || inconsistent}
            onChange={k => (k === 'hybrid' ? (loadPreview(), document.getElementById('hybrid-choice')?.scrollIntoView({ behavior: 'smooth' })) : k !== m.current && choose(k))} />
        </div>
      </div>

      <div className="mb-4 rounded-lg px-3.5 py-3 text-[13px]" style={{ background: 'rgba(245,181,66,0.07)', border: '1px solid rgba(245,181,66,0.3)', color: '#f2d493' }} data-testid="diff-note">
        <b>What differs:</b> {diffHeadline}
        {m.items.length > 1 && (
          <button type="button" className="ml-2 underline" onClick={() => setShowAll(s => !s)} data-testid="diff-toggle">{showAll ? 'Hide the list' : 'Show them all'}</button>
        )}
        {m.suggested && <> <b>Suggestion: {CHOICE_NAME[m.suggested]}.</b></>}
        {showAll && <div className="mt-3 rounded-lg border border-pb-hairline bg-pb-bg p-3 text-pb-dim"><DifferenceTable items={m.items} /></div>}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card side="ca" m={m} />
        <Card side="club" m={m} />
      </div>

      <h3 className="mt-6 mb-3 font-mono text-[10px] uppercase tracking-[0.12em] text-pb-faint">Choose what the site shows for this match</h3>
      <div className="grid gap-3 lg:grid-cols-3" data-testid="choices">
        <Choice title="Cricket Australia scorecard" tone={TONES.ok.hex} active={m.current === 'ca'}>
          <p className="mt-1.5 text-[12.5px] text-pb-dim">Everything from Cricket Australia, including any numbers that differ from the club's. Use this if you think Cricket Australia is right.</p>
          <div className="mt-3"><Button variant={m.current === 'ca' ? 'soft' : 'primary'} disabled={busy || m.current === 'ca'} onClick={() => choose('ca')} data-testid="choose-ca">Show this</Button></div>
        </Choice>
        <Choice title="Club scorecard" tone={TONES.warn.hex} active={m.current === 'club'}>
          <p className="mt-1.5 text-[12.5px] text-pb-dim">The club's numbers only, as recorded: no opposition card and no bowler or fielder names beyond what the card already has.</p>
          <div className="mt-3"><Button disabled={busy || m.current === 'club'} onClick={() => choose('club')} data-testid="choose-club">Show this</Button></div>
        </Choice>
        <div id="hybrid-choice">
          <Choice title="Club numbers with Cricket Australia detail" rec active={m.current === 'hybrid'}>
            <p className="mt-1.5 text-[12.5px] text-pb-dim">Runs, wickets and result stay as the club recorded them. Detail Cricket Australia holds is added wherever it fits; whatever does not fit is left out and listed.</p>
            {!preview && !previewing && <div className="mt-3"><Button size="sm" onClick={loadPreview} disabled={busy || inconsistent} data-testid="preview">Preview what would come over</Button></div>}
            {previewing && <p className="mt-3 text-[12.5px] text-pb-dim">Reading Cricket Australia's card…</p>}
            {preview && !preview.ok && <p className="mt-3 text-[12.5px]" style={{ color: TONES.block.ink }} data-testid="preview-reason">{preview.reason}</p>}
            {preview?.ok && (
              <div className="mt-3 grid gap-3" data-testid="preview-body">
                <div>
                  <div className="font-mono text-[10px] uppercase tracking-[0.1em]" style={{ color: TONES.ok.hex }}>Brought over</div>
                  {preview.brought.length ? <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[12.5px] text-pb-text" data-testid="brought">{preview.brought.map(b => <li key={b}>{b}</li>)}</ul>
                    : <p className="text-[12.5px] text-pb-dim">Nothing fits for this match.</p>}
                </div>
                <div>
                  <div className="font-mono text-[10px] uppercase tracking-[0.1em]" style={{ color: TONES.warn.hex }}>Left out, because the numbers differ or it is not available</div>
                  {preview.left_out.length ? <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[12.5px] text-pb-dim" data-testid="left-out">{preview.left_out.map(b => <li key={b}>{b}</li>)}</ul>
                    : <p className="text-[12.5px] text-pb-dim">Nothing is left out.</p>}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button variant="primary" disabled={busy || m.current === 'hybrid'} onClick={() => choose('hybrid')} data-testid="choose-hybrid">
                    {m.current === 'hybrid' ? 'Showing now' : 'Show this'}
                  </Button>
                  {m.current === 'hybrid' && <Button size="sm" disabled={busy} data-testid="refresh"
                    onClick={() => run(() => api.cardReviewRefresh(matchId), r => `Detail refreshed. ${r.left_out.length} left out`).then(loadPreview)}>
                    Refresh the detail from Cricket Australia</Button>}
                </div>
              </div>
            )}
          </Choice>
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <div className="rounded-xl border border-pb-hairline bg-pb-surface p-4">
          <label className="block font-mono text-[10px] uppercase tracking-[0.12em] text-pb-faint mb-1.5" htmlFor="review-note">Note for the record (optional)</label>
          <TextArea id="review-note" rows={2} value={note} maxLength={500} placeholder="e.g. Club scorecard correct: Pike made 35 and extras were 12." onChange={e => setNote(e.target.value)} />
          <p className="mt-2 text-[12px] text-pb-faint">
            The note is saved with your next choice. You can switch back at any time: both scorecards stay stored.
          </p>
          <div className="mt-3 flex flex-wrap gap-2 text-[12.5px]">
            <a className="text-pb-accent-ink hover:underline" href={matchPageUrl(m.game_id)} target="_blank" rel="noreferrer">Open the Cricket Australia page</a>
            <span className="text-pb-faintest">·</span>
            <a className="text-pb-accent-ink hover:underline" href={matchPageUrl(m.match_id)} target="_blank" rel="noreferrer">Open the club scorecard page</a>
          </div>
        </div>
        <History rows={m.history} busy={busy} onUndo={() => run(() => api.cardReviewUndo(matchId), r => `Put back: now showing ${CHOICE_NAME[r.to]}`)} />
      </div>
    </BetterStatsLayout>
  )
}
