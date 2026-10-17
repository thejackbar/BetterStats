// BetterSelect → Fines → Overview: the squad's fines at a glance.
//
// Tiles for the pot and what is still to collect, a bar for each recent session,
// and the two short lists people ask about first: who owes most, and who has been
// fined most. Everything is worked out from the squad payload the screen already
// holds, so it can never disagree with the tracker.
import { Btn } from './ui'
import { Card, money, shortDate } from './finesUi'

export function Kpi({ label, value, hint, tone, ...rest }) {
  return (
    <div className="pb-card rounded-xl px-4 py-3 min-w-0" {...rest}>
      <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">{label}</div>
      <div className="font-display font-bold text-[22px] leading-tight mt-1 truncate" style={tone ? { color: tone } : undefined}>{value}</div>
      {hint && <div className="text-[11.5px] text-pb-faint mt-0.5 truncate">{hint}</div>}
    </div>
  )
}

// What the tiles read, from the players on the squad payload.
export function summarise(data) {
  const owing = data.players.filter((p) => p.owing > 0)
  const toCollect = owing.reduce((a, p) => a + p.owing, 0)
  const dates = [...data.dates].reverse() // oldest to newest
  const perSession = dates.map((d) => ({ date: d, total: data.players.reduce((a, p) => a + (p.by_date[d] || 0), 0) }))
  return {
    toCollect: Math.round(toCollect * 100) / 100,
    owingCount: owing.length,
    perSession,
    mostOwing: [...owing].sort((a, b) => b.owing - a.owing).slice(0, 5),
    mostFined: [...data.players].filter((p) => p.fined > 0).sort((a, b) => b.fined - a.fined).slice(0, 5),
  }
}

function Bars({ items }) {
  const top = Math.max(1, ...items.map((i) => i.total))
  return (
    <div className="flex items-end gap-2 h-36" role="img" aria-label="Fines handed out each session" data-chart>
      {items.map((i) => (
        <div key={i.date} className="flex-1 min-w-0 flex flex-col items-center justify-end h-full" data-bar={i.date}>
          <div className="text-[11px] text-pb-dim mb-1 truncate max-w-full">{i.total ? money(i.total) : ''}</div>
          <div className="w-full rounded-t-md" style={{ height: `${Math.max(i.total ? 6 : 2, (i.total / top) * 100)}%`, background: 'var(--pb-accent)', opacity: i.total ? 1 : 0.25 }} />
          <div className="text-[10.5px] text-pb-faint mt-1.5 font-mono">{shortDate(i.date)}</div>
        </div>
      ))}
    </div>
  )
}

function Ranked({ rows, valueOf, empty, tone }) {
  if (rows.length === 0) return <div className="text-sm text-pb-faint">{empty}</div>
  return (
    <ol className="flex flex-col">
      {rows.map((p, i) => (
        <li key={p.player_id} className="flex items-center gap-3 py-1.5 border-t border-pb-hairline first:border-t-0 text-[13.5px]">
          <span className="w-5 text-pb-faint font-mono text-[11px]">{i + 1}</span>
          <span className="flex-1 min-w-0 truncate font-medium">{p.name}</span>
          <span className="font-bold" style={tone ? { color: tone } : undefined}>{money(valueOf(p))}</span>
        </li>
      ))}
    </ol>
  )
}

export default function FinesOverview({ data, onGoto }) {
  const s = summarise(data)
  const t = data.totals
  const empty = t.fined === 0 && t.paid === 0
  const collected = t.fined > 0 ? Math.min(100, Math.round((t.paid / t.fined) * 100)) : 0
  return (
    <div data-fines-overview>
      {empty ? (
        <Card title="No fines yet" sub="Once you add a session, the pot, who owes what and how each night went show up here.">
          <Btn variant="primary" onClick={() => onGoto('add')}>Add the first fines</Btn>
        </Card>
      ) : (
        <>
          <div className="grid lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] gap-4 mb-4">
            <Card title="Fines by session" sub={`The last ${s.perSession.length} session${s.perSession.length === 1 ? '' : 's'} with fines.`}>
              <Bars items={s.perSession} />
            </Card>
            <Card title="Collected so far">
              <div className="flex items-baseline justify-between gap-3">
                <span className="font-display font-bold text-[26px]" style={{ color: 'var(--pb-positive)' }}>{collected}%</span>
                <span className="text-[12.5px] text-pb-dim">{money(t.paid)} of {money(t.fined)}</span>
              </div>
              <div className="h-2.5 rounded-full mt-2 overflow-hidden" style={{ background: 'var(--pb-surface2)' }} data-collected-bar>
                <div className="h-full rounded-full" style={{ width: `${collected}%`, background: 'var(--pb-positive)' }} />
              </div>
              <div className="text-[12.5px] text-pb-dim mt-2">{s.owingCount} player{s.owingCount === 1 ? ' still owes' : 's still owe'} {money(s.toCollect)}.</div>
            </Card>
          </div>
          <div className="grid sm:grid-cols-2 gap-4">
            <Card title="Who owes most" right={<Btn sm onClick={() => onGoto('tracker')}>Tracker</Btn>}>
              <Ranked rows={s.mostOwing} valueOf={(p) => p.owing} empty="Nobody owes anything. All square." tone="var(--pb-amber)" />
            </Card>
            <Card title="Most fined" sub="Across every session.">
              <Ranked rows={s.mostFined} valueOf={(p) => p.fined} empty="No fines yet." />
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
