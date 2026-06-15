import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import { useClub } from '../../hooks/useClub'
import { normalizeGender } from '../../lib/playerAttributes'

const CAT_LABELS = {
  batting: 'BATTING',
  bowling: 'BOWLING',
  fielding: 'FIELDING',
  matches: 'MATCHES',
}

const CAT_COLORS = {
  batting: 'text-blue-400 bg-blue-400/10 border-blue-400/20',
  bowling: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20',
  fielding: 'text-amber-400 bg-amber-400/10 border-amber-400/20',
  matches: 'text-purple-400 bg-purple-400/10 border-purple-400/20',
}

function milestoneLabel(item, isUpcoming) {
  const { type, milestone_value, target, current, detail } = item
  const value = isUpcoming ? target : milestone_value
  if (type === 'grade_matches') return `${value} games — ${detail || ''}`
  if (type === 'runs') return `${value.toLocaleString()} runs`
  if (type === 'wickets') return `${value} wickets`
  if (type === 'catches') return `${value} catches`
  if (type === 'matches') return `${value} club games`
  return `${value}`
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

function ProgressBar({ current, target }) {
  const pct = Math.min(100, Math.round((current / target) * 100))
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-1.5 bg-pb-surface2 rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: 'var(--pb-accent)' }} />
      </div>
      <span className="font-mono text-[10px] text-pb-faint">{pct}%</span>
    </div>
  )
}

export default function AdminMilestones() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [status, setStatus] = useState('upcoming')
  const [category, setCategory] = useState('all')
  const [gender, setGender] = useState('all')
  const [search, setSearch] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const { club } = useClub()
  const slug = club?.slug

  useEffect(() => {
    setLoading(true)
    api.adminGetMilestones()
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [])

  const { upcomingFiltered, achievedFiltered } = useMemo(() => {
    if (!data) return { upcomingFiltered: [], achievedFiltered: [] }
    const q = search.trim().toLowerCase()
    const catMatch = item => category === 'all' || item.category === category
    const nameMatch = item => !q || item.player_name.toLowerCase().includes(q)
    const genderMatch = item => gender === 'all' || normalizeGender(item.gender) === gender
    // Date filter only applies to achieved milestones (by the date achieved).
    // Items with no achieved_at fall out once a range is set.
    const dateMatch = item => {
      if (!dateFrom && !dateTo) return true
      if (!item.achieved_at) return false
      const d = item.achieved_at.slice(0, 10)
      if (dateFrom && d < dateFrom) return false
      if (dateTo && d > dateTo) return false
      return true
    }
    return {
      upcomingFiltered: data.upcoming.filter(i => catMatch(i) && nameMatch(i) && genderMatch(i)),
      achievedFiltered: data.achieved.filter(i => catMatch(i) && nameMatch(i) && genderMatch(i) && dateMatch(i)),
    }
  }, [data, category, search, gender, dateFrom, dateTo])

  const showUpcoming = status === 'upcoming' || status === 'all'
  const showAchieved = status === 'achieved' || status === 'all'

  return (
    <AdminLayout>
      <div className="max-w-5xl">
        <div className="mb-6">
          <h1 className="font-display font-bold text-2xl text-pb-text mb-1">Milestones</h1>
          <p className="text-pb-faint text-sm">Upcoming and achieved milestones across all club members.</p>
        </div>

        {/* Filter bar */}
        <div className="flex flex-wrap items-center gap-3 mb-6">
          {/* Status tabs */}
          <div className="flex border pb-hairline rounded overflow-hidden">
            {[['upcoming', 'Upcoming'], ['achieved', 'Achieved'], ['all', 'All']].map(([val, label]) => (
              <button
                key={val}
                onClick={() => setStatus(val)}
                className={`px-3 py-1.5 font-mono text-[10px] tracking-wide2 transition-colors ${
                  status === val
                    ? 'bg-pb-surface2 text-pb-text'
                    : 'text-pb-faint hover:text-pb-text'
                }`}
                style={status === val ? { color: 'var(--pb-accent)' } : {}}
              >
                {label.toUpperCase()}
              </button>
            ))}
          </div>

          {/* Category filter */}
          <div className="flex border pb-hairline rounded overflow-hidden">
            {[['all', 'All'], ['batting', 'Batting'], ['bowling', 'Bowling'], ['fielding', 'Fielding'], ['matches', 'Matches']].map(([val, label]) => (
              <button
                key={val}
                onClick={() => setCategory(val)}
                className={`px-3 py-1.5 font-mono text-[10px] tracking-wide2 transition-colors ${
                  category === val
                    ? 'bg-pb-surface2 text-pb-text'
                    : 'text-pb-faint hover:text-pb-text'
                }`}
                style={category === val ? { color: 'var(--pb-accent)' } : {}}
              >
                {label.toUpperCase()}
              </button>
            ))}
          </div>

          {/* Gender filter */}
          <div className="flex border pb-hairline rounded overflow-hidden">
            {[['all', 'All'], ['male', 'Men'], ['female', 'Women']].map(([val, label]) => (
              <button
                key={val}
                onClick={() => setGender(val)}
                className={`px-3 py-1.5 font-mono text-[10px] tracking-wide2 transition-colors ${
                  gender === val
                    ? 'bg-pb-surface2 text-pb-text'
                    : 'text-pb-faint hover:text-pb-text'
                }`}
                style={gender === val ? { color: 'var(--pb-accent)' } : {}}
              >
                {label.toUpperCase()}
              </button>
            ))}
          </div>

          {/* Player search */}
          <input
            type="text"
            placeholder="Search player..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="px-3 py-1.5 text-sm bg-pb-surface2 border pb-hairline rounded text-pb-text placeholder-pb-faintest focus:outline-none focus:border-pb-accent/50 min-w-[160px]"
          />

          {/* Achieved-date filter (only meaningful when achieved rows show) */}
          {showAchieved && (
            <div className="flex items-center gap-2">
              <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest uppercase">Achieved</span>
              <input
                type="date"
                value={dateFrom}
                onChange={e => setDateFrom(e.target.value)}
                aria-label="Achieved from date"
                className="px-2 py-1.5 text-sm bg-pb-surface2 border pb-hairline rounded text-pb-text focus:outline-none focus:border-pb-accent/50"
              />
              <span className="text-pb-faintest text-xs">to</span>
              <input
                type="date"
                value={dateTo}
                onChange={e => setDateTo(e.target.value)}
                aria-label="Achieved to date"
                className="px-2 py-1.5 text-sm bg-pb-surface2 border pb-hairline rounded text-pb-text focus:outline-none focus:border-pb-accent/50"
              />
              {(dateFrom || dateTo) && (
                <button
                  onClick={() => { setDateFrom(''); setDateTo('') }}
                  className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors"
                >
                  CLEAR
                </button>
              )}
            </div>
          )}

          {data && (
            <span className="text-pb-faintest font-mono text-[10px] ml-auto">
              {showUpcoming && `${upcomingFiltered.length} upcoming`}
              {showUpcoming && showAchieved && ' · '}
              {showAchieved && `${achievedFiltered.length} achieved`}
            </span>
          )}
        </div>

        {loading && (
          <div className="text-pb-faint text-sm">Loading milestones…</div>
        )}
        {error && (
          <div className="text-red-400 text-sm">{error}</div>
        )}

        {data && (
          <div className="space-y-8">
            {/* ---- Upcoming ---- */}
            {showUpcoming && (
              <section>
                <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">
                  Milestones In Reach
                  {upcomingFiltered.length > 0 && (
                    <span className="ml-2 text-pb-faintest">({upcomingFiltered.length})</span>
                  )}
                </p>
                {upcomingFiltered.length === 0 ? (
                  <div className="pb-card px-5 py-4 text-pb-faint text-sm">No upcoming milestones match the current filters.</div>
                ) : (
                  <div className="pb-card overflow-hidden">
                    <table className="w-full">
                      <thead>
                        <tr className="pb-hairline-b">
                          <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">Player</th>
                          <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase hidden sm:table-cell">Category</th>
                          <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">Milestone</th>
                          <th className="text-right px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">Progress</th>
                          <th className="text-right px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">To Go</th>
                        </tr>
                      </thead>
                      <tbody>
                        {upcomingFiltered.map((item, i) => (
                          <tr key={`${item.player_id}-${item.type}-${item.detail}-${item.target}`}
                            className={`${i > 0 ? 'pb-hairline-t' : ''} hover:bg-pb-surface2 transition-colors`}>
                            <td className="px-4 py-3">
                              {slug ? (
                                <Link
                                  to={`/players/${item.player_id}`}
                                  className="text-pb-text text-sm hover:underline"
                                  style={{ color: 'var(--pb-accent)' }}
                                >
                                  {item.player_name}
                                </Link>
                              ) : (
                                <span className="text-pb-text text-sm">{item.player_name}</span>
                              )}
                            </td>
                            <td className="px-4 py-3 hidden sm:table-cell">
                              <CatBadge cat={item.category} />
                            </td>
                            <td className="px-4 py-3">
                              <span className="text-pb-text text-sm">{milestoneLabel(item, true)}</span>
                              {item.detail && (
                                <span className="block text-pb-faintest font-mono text-[10px] mt-0.5">{item.detail}</span>
                              )}
                            </td>
                            <td className="px-4 py-3 text-right">
                              <div className="flex justify-end">
                                <ProgressBar current={item.current} target={item.target} />
                              </div>
                              <div className="text-pb-faintest font-mono text-[10px] mt-0.5 text-right">
                                {item.current.toLocaleString()} / {item.target.toLocaleString()}
                              </div>
                            </td>
                            <td className="px-4 py-3 text-right">
                              <span className="font-mono text-sm font-bold" style={{ color: 'var(--pb-accent)' }}>
                                {item.needed}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            )}

            {/* ---- Achieved ---- */}
            {showAchieved && (
              <section>
                <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">
                  Achieved
                  {achievedFiltered.length > 0 && (
                    <span className="ml-2 text-pb-faintest">({achievedFiltered.length})</span>
                  )}
                </p>
                {achievedFiltered.length === 0 ? (
                  <div className="pb-card px-5 py-4 text-pb-faint text-sm">No achieved milestones match the current filters.</div>
                ) : (
                  <div className="pb-card overflow-hidden">
                    <table className="w-full">
                      <thead>
                        <tr className="pb-hairline-b">
                          <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">Player</th>
                          <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase hidden sm:table-cell">Category</th>
                          <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">Milestone</th>
                          <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase hidden md:table-cell">Grade</th>
                          <th className="text-right px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">Date</th>
                        </tr>
                      </thead>
                      <tbody>
                        {achievedFiltered.map((item, i) => (
                          <tr key={`${item.player_id}-${item.type}-${item.milestone_value}-${item.detail}-${i}`}
                            className={`${i > 0 ? 'pb-hairline-t' : ''} hover:bg-pb-surface2 transition-colors`}>
                            <td className="px-4 py-3">
                              {slug ? (
                                <Link
                                  to={`/players/${item.player_id}`}
                                  className="text-sm hover:underline"
                                  style={{ color: 'var(--pb-accent)' }}
                                >
                                  {item.player_name}
                                </Link>
                              ) : (
                                <span className="text-pb-text text-sm">{item.player_name}</span>
                              )}
                            </td>
                            <td className="px-4 py-3 hidden sm:table-cell">
                              <CatBadge cat={item.category} />
                            </td>
                            <td className="px-4 py-3">
                              <span className="text-pb-text text-sm">{milestoneLabel(item, false)}</span>
                            </td>
                            <td className="px-4 py-3 hidden md:table-cell">
                              <span className="text-pb-faint text-sm">{item.detail || '—'}</span>
                            </td>
                            <td className="px-4 py-3 text-right font-mono text-[11px] text-pb-faint whitespace-nowrap">
                              {fmtDate(item.achieved_at) || '—'}
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
        )}
      </div>
    </AdminLayout>
  )
}
