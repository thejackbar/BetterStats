import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import { Button, Badge } from '../ui'
import { fmtDate, matchPageUrl } from './shared'

const STRENGTH = {
  strong: { label: 'Strong match', tone: 'ok', why: 'Most of the smaller card is on the other card with the same scores.' },
  likely: { label: 'Likely match', tone: 'accent', why: 'The same day and opposition, and some batters have the same score. The two cards may name a player differently.' },
  possible: { label: 'Possible match', tone: 'warn', why: 'Only the date and the opposition fit. One of the cards has no batters to compare.' },
}

// One copy of a match: where it came from, what it holds, and a link to the real scorecard page.
export function SideBox({ side, label }) {
  if (!side) return null
  const isCa = side.kind === 'ca'
  return (
    <div className="min-w-0 rounded-lg border border-pb-hairline bg-pb-bg p-3.5" data-testid="side" data-side={side.kind} data-id={side.id}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge toneKey={isCa ? 'ok' : 'warn'}>{label || (isCa ? 'Cricket Australia' : 'Club scorecard')}</Badge>
        {side.linked && <Badge toneKey="calm">Linked to Cricket Australia</Badge>}
        {side.format && <Badge toneKey="calm">{side.format}</Badge>}
      </div>
      <div className="mt-2 text-[13.5px] font-semibold text-pb-text">{side.grade || 'No grade'} v {side.opposition || '—'}</div>
      <div className="font-mono text-[12px] text-pb-dim">{fmtDate(side.date)}{side.season ? ` · ${side.season}` : ''}</div>
      <div className="mt-1.5 text-[12px] text-pb-dim">
        {side.batters} batters · {side.bowlers} bowlers{side.result ? ` · our result ${side.result}` : ''}
      </div>
      <div className="mt-1 text-[11.5px] text-pb-faint">{side.source?.label}{side.source?.at ? ` · ${fmtDate(side.source.at)}` : ''}</div>
      <a className="mt-2 inline-block text-[12px] text-pb-accent-ink hover:underline" href={matchPageUrl(side.id)} target="_blank" rel="noreferrer">
        Open this scorecard
      </a>
    </div>
  )
}

export function Evidence({ row }) {
  const s = STRENGTH[row.strength]
  const smaller = Math.min(row.a?.batters ?? 0, row.b?.batters ?? 0)
  return (
    <div className="flex flex-wrap items-center gap-1.5" data-testid="evidence">
      {s && <span title={s.why}><Badge toneKey={s.tone}>{s.label}</Badge></span>}
      <Badge toneKey={row.shared ? 'ok' : 'calm'}>
        {row.both_cards ? `${row.shared} of ${smaller} batters in common` : 'One card has no batters to compare'}
      </Badge>
      <Badge toneKey="calm">{row.same_day ? 'Same day' : row.gap_days == null ? 'No date to compare' : `${row.gap_days} days apart`}</Badge>
      <Badge toneKey={row.opposition_agrees ? 'calm' : 'warn'}>{row.opposition_agrees ? 'Same opposition' : 'Opposition spelt differently'}</Badge>
      {row.formats_differ && <Badge toneKey="warn">Filed under different match types</Badge>}
    </div>
  )
}

// A possible double and what can be done about it. `onChanged` reloads the caller's list.
export default function DoubleCard({ row, onChanged, dismissed = false }) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const { a, b } = row

  async function run(fn, ok) {
    setBusy(true)
    try { const res = await fn(); toast.success(typeof ok === 'function' ? ok(res) : ok); onChanged() } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  const remove = side => {
    const what = side.source?.label?.toLowerCase() || 'club scorecard'
    if (!confirm(`Remove this copy (the ${what}, ${side.batters} batters)?\n\nThe other copy stays. A removed scorecard can be restored from Manual Entries, Audit and Undo.`)) return
    run(() => api.adminDeleteManualGame(side.id), 'Copy removed. It can be restored from Manual Entries.')
  }

  return (
    <div className="rounded-xl border border-pb-hairline bg-pb-surface p-4" data-testid="double-card" data-key={row.key} data-kind={row.kind}>
      <Evidence row={row} />
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <SideBox side={a} label={a.kind === 'club' && row.kind === 'club' ? 'Club scorecard (earlier)' : undefined} />
        <SideBox side={b} label={row.kind === 'relink' ? 'The right Cricket Australia match' : b.kind === 'club' && row.kind === 'club' ? 'Club scorecard (later)' : undefined} />
      </div>
      {row.current && (
        <p className="mt-2.5 text-[12.5px] text-pb-dim" data-testid="current-link">
          Linked now to <b className="text-pb-text">{row.current.grade || 'a game'} v {row.current.opposition || '—'}</b>, {fmtDate(row.current.date)}
          {row.current.format ? ` (${row.current.format})` : ''}, where {row.current.shared_with_club} of this card's {a.batters} batters appear with the same score.{' '}
          <a className="text-pb-accent-ink hover:underline" href={matchPageUrl(row.current.id)} target="_blank" rel="noreferrer">Open that game</a>
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {dismissed ? (
          <>
            <span className="text-[12px] text-pb-dim">Marked as different matches{row.dismissed_by ? ` by ${row.dismissed_by}` : ''}.</span>
            <Button size="sm" disabled={busy} onClick={() => run(() => api.cardReviewDoubleRestore(a.id, b.id, row.kind), 'Put back in the list')} data-testid="restore">
              Put back in the list
            </Button>
          </>
        ) : (
          <>
            {row.kind === 'ca' && (
              <Button size="sm" variant="primary" disabled={busy} data-testid="link"
                onClick={() => run(() => api.cardReviewDoubleLink(a.id, b.id),
                  r => `Linked. The site now shows the ${r.shows === 'club' ? 'club scorecard' : 'Cricket Australia scorecard'}.`)}>
                Same match: link them
              </Button>
            )}
            {row.kind === 'relink' && (
              <Button size="sm" variant="primary" disabled={busy} data-testid="relink"
                onClick={() => run(() => api.cardReviewRelink(a.id, b.id), 'Link moved to the right match. The game it left counts on its own again.')}>
                Move the link to the right match
              </Button>
            )}
            {row.kind === 'club' && (
              <>
                <Button size="sm" variant="danger" disabled={busy} onClick={() => remove(a)} data-testid="remove-a">Remove the earlier copy</Button>
                <Button size="sm" variant="danger" disabled={busy} onClick={() => remove(b)} data-testid="remove-b">Remove the later copy</Button>
              </>
            )}
            <Button size="sm" disabled={busy} data-testid="dismiss"
              onClick={() => run(() => api.cardReviewDoubleDismiss(a.id, b.id, row.kind), 'Marked as different matches. This can be put back.')}>
              Different matches
            </Button>
          </>
        )}
        {row.kind === 'relink' && !dismissed && (
          <span className="ml-auto text-[11.5px] text-pb-faint">Nothing is deleted. The link can be moved back from the match.</span>
        )}
        {row.kind === 'ca' && !dismissed && (
          <span className="ml-auto text-[11.5px] text-pb-faint">Nothing is deleted. Both cards stay, and the link can be undone from the match.</span>
        )}
        {row.kind === 'club' && !dismissed && (
          <span className="ml-auto text-[11.5px] text-pb-faint">Two club scorecards have no link between them, so the extra copy is removed. <Link className="underline" to="/admin/manual-entries#audit">Audit and Undo</Link> restores it.</span>
        )}
      </div>
    </div>
  )
}
