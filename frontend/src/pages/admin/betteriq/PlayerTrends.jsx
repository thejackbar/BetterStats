import { useState, useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import IQLayout from '../../../components/admin/IQLayout'
import { api } from '../../../lib/api'
import { Icon, Btn, Tag, Empty, Search } from '../betterselect/ui'

const num = (v, dash = '—') => (v === null || v === undefined ? dash : v)
const TYPE_LABEL = { runs: 'runs', wickets: 'wickets', matches: 'games', catches: 'catches' }

function Card({ title, right, children, accent = false }) {
  return (
    <div className="pb-card p-4 md:p-5" style={accent ? { borderColor: 'color-mix(in srgb, var(--pb-accent) 30%, transparent)' } : undefined}>
      {(title || right) && (
        <div className="flex items-center justify-between gap-3 mb-3">
          <h3 className="font-display font-bold">{title}</h3>
          {right}
        </div>
      )}
      {children}
    </div>
  )
}

function VerdictTag({ v }) {
  if (!v) return null
  const map = { rising: ['Rising', 'var(--pb-brand)'], declining: ['Declining', 'var(--pb-red)'], steady: ['Steady', 'var(--pb-faint)'] }
  const [label, color] = map[v] || []
  if (!label) return null
  return <span className="font-mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: `color-mix(in srgb, ${color} 16%, transparent)`, color }}>{label}</span>
}

/* ── overview: milestones + movers ────────────────────────────────────────── */

function MilestoneList({ items }) {
  if (!items?.length) return <Empty>No milestones in reach right now.</Empty>
  return (
    <div className="space-y-2">
      {items.map((m, i) => (
        <div key={i} className="flex items-center justify-between gap-2">
          <span className="font-medium truncate">{m.name}</span>
          <span className="text-sm pb-num whitespace-nowrap">
            <b>{m.needed}</b> <span className="text-pb-faint">more {TYPE_LABEL[m.type] || m.type} → {m.target}</span>
          </span>
        </div>
      ))}
    </div>
  )
}

function Movers({ title, rows, kind, onPick }) {
  if (!rows?.length) return null
  const isBat = kind === 'bat'
  return (
    <div>
      <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-2">{title}</div>
      <div className="space-y-1.5">
        {rows.map(p => (
          <button key={p.player_id} onClick={() => onPick(p.player_id)} className="w-full flex items-center justify-between gap-2 text-left hover:text-pb-accent transition-colors">
            <span className="font-medium truncate">{p.name} <span className="text-pb-faintest text-[11px]">'{String(p.latest_year).slice(-2)}</span></span>
            <span className="text-sm pb-num whitespace-nowrap text-pb-faint">
              {isBat ? 'avg' : 'avg'} {p.baseline} <span style={{ color: 'var(--pb-accent)' }}>→ {p.latest}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}

/* ── player detail: trajectory ────────────────────────────────────────────── */

function RunsBar({ runs, max }) {
  const pct = max ? Math.round((runs / max) * 100) : 0
  return (
    <div className="h-1.5 rounded-full bg-pb-surface2 overflow-hidden w-full min-w-[40px]">
      <div className="h-full rounded-full" style={{ width: `${pct}%`, background: 'var(--pb-accent)' }} />
    </div>
  )
}

function Trajectory({ seasons }) {
  if (!seasons?.length) return <Empty>No season data.</Empty>
  const maxRuns = Math.max(1, ...seasons.map(s => s.total_runs || 0))
  return (
    <div className="overflow-x-auto -mx-1">
      <table className="w-full text-sm">
        <thead><tr className="text-pb-faint text-[11px] uppercase tracking-wide2 text-left">
          <th className="py-1 px-1 font-medium">Season</th>
          <th className="py-1 px-1 font-medium text-right">M</th>
          <th className="py-1 px-1 font-medium text-right">Runs</th>
          <th className="py-1 px-1 font-medium text-right">Avg</th>
          <th className="py-1 px-1 font-medium w-24">Trend</th>
          <th className="py-1 px-1 font-medium text-right">Wkts</th>
          <th className="py-1 px-1 font-medium text-right">Avg</th>
          <th className="py-1 px-1 font-medium text-right">Econ</th>
        </tr></thead>
        <tbody>
          {seasons.map((s, i) => (
            <tr key={i} className="border-t pb-hairline">
              <td className="py-1.5 px-1 whitespace-nowrap">{s.season_name}</td>
              <td className="py-1.5 px-1 text-right pb-num text-pb-faint">{num(s.matches, 0)}</td>
              <td className="py-1.5 px-1 text-right pb-num font-semibold">{num(s.total_runs, 0)}</td>
              <td className="py-1.5 px-1 text-right pb-num">{num(s.batting_average)}</td>
              <td className="py-1.5 px-1"><RunsBar runs={s.total_runs || 0} max={maxRuns} /></td>
              <td className="py-1.5 px-1 text-right pb-num font-semibold">{num(s.total_wickets, 0)}</td>
              <td className="py-1.5 px-1 text-right pb-num">{num(s.bowling_average)}</td>
              <td className="py-1.5 px-1 text-right pb-num text-pb-faint">{num(s.economy)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function CareerStrip({ career }) {
  const b = career?.batting || {}, bo = career?.bowling || {}, f = career?.fielding || {}
  const items = [
    ['Runs', num(b.total_runs, 0)], ['Bat avg', num(b.average)], ['100s/50s', `${num(b.hundreds, 0)}/${num(b.fifties, 0)}`],
    ['Wkts', num(bo.total_wickets, 0)], ['Bowl avg', num(bo.average)], ['Catches', num(f.total_catches, 0)],
  ]
  return (
    <div className="flex flex-wrap gap-x-6 gap-y-2">
      {items.map(([l, v]) => (
        <div key={l}><div className="font-display font-bold text-lg pb-num leading-none">{v}</div><div className="text-pb-faint text-[10px] uppercase tracking-wide2 mt-0.5">{l}</div></div>
      ))}
    </div>
  )
}

/* ── main ─────────────────────────────────────────────────────────────────── */

export default function PlayerTrends() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [overview, setOverview] = useState(null)
  const [players, setPlayers] = useState([])
  const [playerId, setPlayerId] = useState(searchParams.get('player') || null)
  const [detail, setDetail] = useState(null)
  const [q, setQ] = useState('')

  useEffect(() => {
    api.iqTrendsOverview().then(setOverview).catch(() => setOverview({ milestones: [], batting: {}, bowling: {} }))
    api.iqTrendsPlayers().then(setPlayers).catch(() => setPlayers([]))
  }, [])

  useEffect(() => {
    if (!playerId) { setDetail(null); return }
    let alive = true
    setDetail(null)
    api.iqTrendsPlayer(playerId).then(d => { if (alive) setDetail(d) }).catch(() => { if (alive) setDetail({ error: true }) })
    return () => { alive = false }
  }, [playerId])

  const pick = (id) => { setPlayerId(id); setSearchParams({ player: id }, { replace: true }) }
  const clear = () => { setPlayerId(null); setDetail(null); setSearchParams({}, { replace: true }) }

  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase()
    return t ? players.filter(p => p.name.toLowerCase().includes(t)) : players
  }, [q, players])

  // ── Detail view ──
  if (playerId) {
    return (
      <IQLayout title="Player trends" actions={<Btn variant="ghost" sm icon="back" onClick={clear}>All players</Btn>}>
        {detail === null && <div className="pb-card p-5 animate-pulse text-pb-faint text-sm">Loading trajectory…</div>}
        {detail?.error && <div className="pb-card p-5"><Empty>Couldn't load this player.</Empty></div>}
        {detail && !detail.error && (
          <>
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <h2 className="font-display font-bold text-2xl">{detail.player.name}</h2>
              <span className="flex items-center gap-1.5">
                {detail.verdict?.batting && <span title="Batting trend"><VerdictTag v={detail.verdict.batting} /></span>}
                {detail.verdict?.bowling && <span title="Bowling trend">🏏<VerdictTag v={detail.verdict.bowling} /></span>}
              </span>
            </div>

            <Card title="Career"><CareerStrip career={detail.career} /></Card>

            {detail.milestones?.length > 0 && (
              <div className="mt-4">
                <Card title="Closing in on" accent>
                  <div className="flex flex-wrap gap-x-6 gap-y-1.5">
                    {detail.milestones.map((m, i) => (
                      <span key={i} className="text-sm"><b className="pb-num">{m.needed}</b> <span className="text-pb-faint">more {TYPE_LABEL[m.type] || m.type} → {m.target}</span></span>
                    ))}
                  </div>
                </Card>
              </div>
            )}

            <div className="mt-4">
              <Card title="Season by season" right={<span className="text-pb-faint text-xs">oldest → newest</span>}>
                <Trajectory seasons={detail.seasons} />
              </Card>
            </div>
          </>
        )}
      </IQLayout>
    )
  }

  // ── Overview view ──
  return (
    <IQLayout title="Player trends">
      <p className="text-pb-faint text-sm mb-4 max-w-2xl">Who's trending up, who's tailing off, and who's closing in on a milestone — across your active squad.</p>

      <div className="grid gap-4 lg:grid-cols-2 mb-4">
        <Card title="Milestone watch" right={<Tag tone="accent">in reach</Tag>}>
          {overview === null ? <div className="animate-pulse text-pb-faint text-sm">Loading…</div> : <MilestoneList items={overview.milestones} />}
        </Card>
        <Card title="Form movers" right={<span className="text-pb-faint text-xs">latest season vs career</span>}>
          {overview === null ? <div className="animate-pulse text-pb-faint text-sm">Loading…</div> : (
            <div className="grid sm:grid-cols-2 gap-4">
              <Movers title="Batting — rising" rows={overview.batting?.risers} kind="bat" onPick={pick} />
              <Movers title="Batting — declining" rows={overview.batting?.fallers} kind="bat" onPick={pick} />
              <Movers title="Bowling — improving" rows={overview.bowling?.risers} kind="bowl" onPick={pick} />
              <Movers title="Bowling — slipping" rows={overview.bowling?.fallers} kind="bowl" onPick={pick} />
              {!overview.batting?.risers?.length && !overview.batting?.fallers?.length && !overview.bowling?.risers?.length && !overview.bowling?.fallers?.length && (
                <div className="sm:col-span-2"><Empty>Not enough multi-season history to spot movers yet.</Empty></div>
              )}
            </div>
          )}
        </Card>
      </div>

      <Card title={`Players (${players.length})`}>
        <Search value={q} onChange={setQ} placeholder="Search players…" className="mb-3 max-w-sm" />
        {filtered.length === 0 ? <Empty>No players.</Empty> : (
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map(p => (
              <button key={p.player_id} onClick={() => pick(p.player_id)}
                className="pb-card px-3 py-2 text-left hover:border-pb-accent/50 transition-colors flex items-center justify-between gap-2">
                <span className="font-medium truncate">{p.name}</span>
                <span className="text-pb-faintest text-[11px] pb-num whitespace-nowrap">{p.runs} runs · {p.wickets} wkts</span>
              </button>
            ))}
          </div>
        )}
      </Card>
    </IQLayout>
  )
}
