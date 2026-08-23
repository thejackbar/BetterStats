import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { scoutApi } from '../lib/scoutApi'
import ScoutModuleLayout from '../ScoutModuleLayout'
import { Btn, Chip, Search, Segmented } from '../../pages/admin/betterselect/ui'

const CAT_LABELS = { batting: 'BATTING', bowling: 'BOWLING', fielding: 'FIELDING', matches: 'MATCHES' }
const CAT_COLORS = {
  batting: 'text-blue-400 bg-blue-400/10 border-blue-400/20',
  bowling: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20',
  fielding: 'text-amber-400 bg-amber-400/10 border-amber-400/20',
  matches: 'text-purple-400 bg-purple-400/10 border-purple-400/20',
}

function milestoneLabel(type, value) {
  if (type === 'runs') return `${value.toLocaleString()} runs`
  if (type === 'wickets') return `${value} wickets`
  if (type === 'catches') return `${value} catches`
  if (type === 'matches') return `${value} matches`
  return `${value}`
}

// A "reached" row's value is a career-threshold crossed (500 runs, 5-fors
// carry no threshold so never appear here). A "recent performance" row's
// value means something different per dating tier: MATCH DATED is the
// actual runs/wickets from that one game; SEASON ONLY (no per-innings data
// to point at) can only be a COUNT of centuries/five-fors that season.
function performanceLabel(row) {
  if (row.dated === 'match') {
    return row.type === 'century' ? `${row.value} runs` : `${row.value} wickets`
  }
  const n = row.value
  if (row.type === 'century') return `${n} ${n === 1 ? 'century' : 'centuries'}`
  return `${n} five-wicket ${n === 1 ? 'haul' : 'hauls'}`
}

function fmtDate(iso) {
  if (!iso) return null
  return new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

function CatBadge({ cat }) {
  return (
    <span className={`inline-block font-mono text-[9px] tracking-wide3 px-1.5 py-0.5 rounded border ${CAT_COLORS[cat] || 'text-pb-faint bg-pb-surface2 border-pb-hairline'}`}>
      {CAT_LABELS[cat] || cat.toUpperCase()}
    </span>
  )
}

// The load-bearing two-tier honesty badge: green MATCH DATED for a player
// whose club is already an onboarded BetterCricket club (exact per-game
// data), neutral SEASON ONLY for everyone else (Cricket Australia's public
// season-aggregate feed only carries a season, not a date).
function DatedBadge({ row }) {
  if (row.dated === 'match') {
    return (
      <span className="inline-flex items-center gap-1 font-mono text-[9px] tracking-wide2 px-1.5 py-0.5 rounded border text-emerald-400 bg-emerald-400/10 border-emerald-400/20" title={row.achieved_at ? fmtDate(row.achieved_at) : undefined}>
        ● MATCH DATED
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 font-mono text-[9px] tracking-wide2 px-1.5 py-0.5 rounded border text-pb-faint bg-pb-surface2 border-pb-hairline" title="Cricket Australia's public feed is season-granular, not date-granular">
      SEASON ONLY
    </span>
  )
}

function ProgressBar({ current, target }) {
  const pct = Math.min(100, Math.round((100 * current) / target))
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-1.5 bg-pb-surface2 rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: 'var(--pb-accent)' }} />
      </div>
      <span className="font-mono text-[10px] text-pb-faint">{pct}%</span>
    </div>
  )
}

function StatReadout({ label, value }) {
  return (
    <div className="text-right">
      <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faint">{label}</div>
      <div className="font-mono text-lg font-bold">{value}</div>
    </div>
  )
}

export default function ScoutMilestones() {
  const [data, setData] = useState(undefined)
  const [error, setError] = useState(null)
  const [status, setStatus] = useState('in_reach')
  const [category, setCategory] = useState('all')
  const [search, setSearch] = useState('')
  const [marking, setMarking] = useState(null)
  const [seasonsWindow, setSeasonsWindow] = useState(2)

  const load = () => { scoutApi.getMilestones(seasonsWindow).then(setData).catch((err) => setError(err.message)) }
  useEffect(load, [seasonsWindow]) // eslint-disable-line react-hooks/exhaustive-deps

  const markSeen = async (row) => {
    setMarking(`${row.player_id}-${row.type}-${row.milestone_value}`)
    try {
      await scoutApi.markMilestoneSeen(row.player_id, row.type, row.milestone_value)
      await load()
    } finally {
      setMarking(null)
    }
  }

  const markAll = async () => {
    await scoutApi.markAllMilestonesSeen()
    await load()
  }

  const { inReach, reached, recentPerformances, unseenCount } = useMemo(() => {
    if (!data) return { inReach: [], reached: [], recentPerformances: [], unseenCount: 0 }
    const q = search.trim().toLowerCase()
    const catMatch = (r) => category === 'all' || r.category === category
    const nameMatch = (r) => !q || r.name.toLowerCase().includes(q)
    return {
      inReach: data.in_reach.filter((r) => catMatch(r) && nameMatch(r)),
      reached: data.reached.filter((r) => catMatch(r) && nameMatch(r)),
      recentPerformances: (data.recent_performances || []).filter((r) => catMatch(r) && nameMatch(r)),
      unseenCount: data.reached.filter((r) => !r.seen).length,
    }
  }, [data, category, search])

  if (error) return <ScoutModuleLayout title="Milestones"><p className="text-sm text-pb-red">{error}</p></ScoutModuleLayout>
  if (data === undefined) return <ScoutModuleLayout title="Milestones"><p className="text-sm text-pb-dim">Loading…</p></ScoutModuleLayout>

  const showInReach = status === 'in_reach' || status === 'all'
  const showReached = status === 'reached' || status === 'all'
  const showRecent = status === 'recent'
  const c = data.season_counters

  return (
    <ScoutModuleLayout
      title="Milestones"
      caption="A player three wickets from 150 is a reason to call, and a reason they'll remember it."
      stats={
        <div className="flex items-center gap-5">
          <StatReadout label="50s this season" value={c.fifties_this_season} />
          <StatReadout label="100s this season" value={c.hundreds_this_season} />
          <StatReadout label="5-fors this season" value={c.five_fors_this_season} />
        </div>
      }
      actions={unseenCount > 0 ? <Btn variant="primary" onClick={markAll}>Mark all as seen ({unseenCount})</Btn> : null}
      filters={
        <div className="flex items-center gap-2 flex-wrap">
          <Segmented
            value={status}
            onChange={setStatus}
            options={[
              { value: 'in_reach', label: `In reach (${data.in_reach.length})` },
              { value: 'reached', label: `Reached${unseenCount ? ` (${unseenCount} new)` : ''}` },
              { value: 'recent', label: `Recent form (${recentPerformances.length})` },
              { value: 'all', label: 'All' },
            ]}
          />
          {['all', 'batting', 'bowling', 'fielding', 'matches'].map((cat) => (
            <Chip key={cat} label={cat === 'all' ? 'All' : CAT_LABELS[cat]} active={category === cat} onClick={() => setCategory(cat)} />
          ))}
          {showRecent && (
            <Segmented
              value={seasonsWindow}
              onChange={setSeasonsWindow}
              sm
              options={[
                { value: 1, label: '1 SEASON' },
                { value: 2, label: '2 SEASONS' },
                { value: 5, label: '5 SEASONS' },
              ]}
            />
          )}
          <Search value={search} onChange={setSearch} placeholder="Search player…" className="w-44" />
        </div>
      }
    >
      <div className="pb-card px-4 py-2.5 mb-5 text-xs text-pb-faint">
        Only as current as each player's last refresh. A stale card can miss a milestone crossed since. See a player's profile for when their stats were last built.
      </div>

      <div className="space-y-8">
        {showInReach && (
          <section>
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">
              In reach{inReach.length > 0 && <span className="ml-2 text-pb-faintest">({inReach.length})</span>}
            </p>
            {inReach.length === 0 ? (
              <div className="pb-card px-5 py-4 text-pb-faint text-sm">No tracked player is close to a milestone right now.</div>
            ) : (
              <div className="pb-card overflow-hidden overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="pb-hairline-b">
                      <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">Player</th>
                      <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase hidden sm:table-cell">Category</th>
                      <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">Milestone</th>
                      <th className="text-right px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">Progress</th>
                      <th className="text-right px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">To go</th>
                    </tr>
                  </thead>
                  <tbody>
                    {inReach.map((r, i) => (
                      <tr key={`${r.player_id}-${r.type}-${r.target}`} className={`${i > 0 ? 'pb-hairline-t' : ''} hover:bg-pb-surface2 transition-colors`}>
                        <td className="px-4 py-3">
                          <Link to={`/betterscout/app/players/${r.player_id}`} className="text-sm hover:text-pb-accent" style={{ color: 'var(--pb-accent)' }}>{r.name}</Link>
                          <div className="text-[11px] text-pb-faintest truncate">{r.club_name}</div>
                        </td>
                        <td className="px-4 py-3 hidden sm:table-cell"><CatBadge cat={r.category} /></td>
                        <td className="px-4 py-3 text-sm">{milestoneLabel(r.type, r.target)}</td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex justify-end"><ProgressBar current={r.current} target={r.target} /></div>
                          <div className="text-pb-faintest font-mono text-[10px] mt-0.5 text-right">{r.current.toLocaleString()} / {r.target.toLocaleString()}</div>
                        </td>
                        <td className="px-4 py-3 text-right"><span className="font-mono text-sm font-bold" style={{ color: 'var(--pb-accent)' }}>{r.needed}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        {showReached && (
          <section>
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">
              Reached{reached.length > 0 && <span className="ml-2 text-pb-faintest">({reached.length})</span>}
            </p>
            {reached.length === 0 ? (
              <div className="pb-card px-5 py-4 text-pb-faint text-sm">Nobody you track has crossed a milestone yet.</div>
            ) : (
              <div className="pb-card overflow-hidden overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="pb-hairline-b">
                      <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">Player</th>
                      <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase hidden sm:table-cell">Category</th>
                      <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">Milestone</th>
                      <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase hidden md:table-cell">Dating</th>
                      <th className="text-right px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">When</th>
                      <th className="px-4 py-2.5"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {reached.map((r, i) => {
                      const key = `${r.player_id}-${r.type}-${r.milestone_value}`
                      return (
                        <tr key={key} className={`${i > 0 ? 'pb-hairline-t' : ''} hover:bg-pb-surface2 transition-colors ${!r.seen ? 'bg-pb-surface2/40' : ''}`}>
                          <td className="px-4 py-3">
                            <Link to={`/betterscout/app/players/${r.player_id}`} className="text-sm hover:text-pb-accent" style={{ color: 'var(--pb-accent)' }}>{r.name}</Link>
                            <div className="text-[11px] text-pb-faintest truncate">{r.club_name}</div>
                          </td>
                          <td className="px-4 py-3 hidden sm:table-cell"><CatBadge cat={r.category} /></td>
                          <td className="px-4 py-3 text-sm">
                            {milestoneLabel(r.type, r.milestone_value)}
                            {r.grade_name && <span className="block text-pb-faintest font-mono text-[10px] mt-0.5">{r.grade_name}</span>}
                          </td>
                          <td className="px-4 py-3 hidden md:table-cell"><DatedBadge row={r} /></td>
                          <td className="px-4 py-3 text-right font-mono text-[11px] text-pb-faint whitespace-nowrap">
                            {r.dated === 'match' ? (fmtDate(r.achieved_at) || '—') : (r.season_year || '—')}
                          </td>
                          <td className="px-4 py-3 text-right">
                            {!r.seen && (
                              <button
                                onClick={() => markSeen(r)}
                                disabled={marking === key}
                                className="text-xs px-2 py-1 rounded border border-pb-hairline2 text-pb-faint hover:text-pb-text disabled:opacity-50 whitespace-nowrap"
                              >
                                {marking === key ? '…' : 'Mark seen'}
                              </button>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        {showRecent && (
          <section>
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">
              Recent notable performances{recentPerformances.length > 0 && <span className="ml-2 text-pb-faintest">({recentPerformances.length})</span>}
            </p>
            <p className="text-xs text-pb-faint mb-3">
              100+ runs or 5+ wickets across the last {seasonsWindow} season{seasonsWindow === 1 ? '' : 's'} any tracked player has played.
            </p>
            {recentPerformances.length === 0 ? (
              <div className="pb-card px-5 py-4 text-pb-faint text-sm">Nobody you track has a century or a five-wicket haul in this window.</div>
            ) : (
              <div className="pb-card overflow-hidden overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="pb-hairline-b">
                      <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">Player</th>
                      <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase hidden sm:table-cell">Category</th>
                      <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">Performance</th>
                      <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase hidden md:table-cell">Dating</th>
                      <th className="text-right px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">When</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentPerformances.map((r, i) => (
                      <tr key={`${r.player_id}-${r.type}-${r.season_year}-${r.achieved_at || ''}-${i}`} className={`${i > 0 ? 'pb-hairline-t' : ''} hover:bg-pb-surface2 transition-colors`}>
                        <td className="px-4 py-3">
                          <Link to={`/betterscout/app/players/${r.player_id}`} className="text-sm hover:text-pb-accent" style={{ color: 'var(--pb-accent)' }}>{r.name}</Link>
                          <div className="text-[11px] text-pb-faintest truncate">{r.club_name}</div>
                        </td>
                        <td className="px-4 py-3 hidden sm:table-cell"><CatBadge cat={r.category} /></td>
                        <td className="px-4 py-3 text-sm">
                          {performanceLabel(r)}
                          {r.grade_name && <span className="block text-pb-faintest font-mono text-[10px] mt-0.5">{r.grade_name}</span>}
                        </td>
                        <td className="px-4 py-3 hidden md:table-cell"><DatedBadge row={r} /></td>
                        <td className="px-4 py-3 text-right font-mono text-[11px] text-pb-faint whitespace-nowrap">
                          {r.dated === 'match' ? (fmtDate(r.achieved_at) || '—') : (r.season_year || '—')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}
      </div>
    </ScoutModuleLayout>
  )
}
