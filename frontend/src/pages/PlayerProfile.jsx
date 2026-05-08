import { useParams, Link } from 'react-router-dom'
import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { api } from '../lib/api'
import { getSubcategories, getAchievements } from '../lib/achievementOptions'
import { usePlayerStats } from '../hooks/usePlayerStats'
import StatCard from '../components/StatCard'
import TrendChart from '../components/TrendChart'
import RunsChart from '../components/RunsChart'
import LoadingSpinner from '../components/LoadingSpinner'
import clsx from 'clsx'

const TABS = ['batting', 'bowling', 'analysis', 'milestones', 'achievements']

const CATEGORY_ICONS = {
  'Club Award': '🏆',
  'Association Award': '🥇',
  'Office Bearer': '👔',
  'Premiership': '🏏',
  'Hall of Fame': '⭐',
  'Life Membership': '🎖',
  'Milestone': '📍',
}

const CATEGORIES = ['Club Award', 'Association Award', 'Office Bearer', 'Premiership', 'Hall of Fame', 'Life Membership', 'Milestone']

function AchievementsSection({ playerId, orgId, playerName }) {
  const [achievements, setAchievements] = useState(null)
  const [seasons, setSeasons] = useState([])
  const [adding, setAdding] = useState(false)
  const [editId, setEditId] = useState(null)
  const [form, setForm] = useState({ season: '', season_end: '', category: 'Club Award', subcategory: '', achievement: '', detail: '' })
  const [customSubcat, setCustomSubcat] = useState(false)
  const [customAchievement, setCustomAchievement] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!orgId) return
    api.listAchievements(orgId, { playerId }).then(setAchievements).catch(() => setAchievements([]))
    api.getOrgSeasons(orgId).then(data => setSeasons(data || [])).catch(() => {})
  }, [playerId, orgId])

  const subcatOptions = getSubcategories(form.category)
  const achievementOptions = getAchievements(form.category, form.subcategory)

  const openAdd = () => {
    setForm({ season: '', season_end: '', category: 'Club Award', subcategory: '', achievement: '', detail: '' })
    setCustomSubcat(false)
    setCustomAchievement(false)
    setEditId(null)
    setAdding(true)
  }

  const openEdit = (a) => {
    setForm({ season: a.season || '', season_end: a.season_end || '', category: a.category, subcategory: a.subcategory || '', achievement: a.achievement, detail: a.detail || '' })
    setCustomSubcat(false)
    setCustomAchievement(false)
    setEditId(a.id)
    setAdding(true)
  }

  const setCategory = (cat) => {
    setForm(f => ({ ...f, category: cat, subcategory: '', achievement: '' }))
    setCustomSubcat(false)
    setCustomAchievement(false)
  }

  const setSubcat = (val) => {
    if (val === '__other__') {
      setCustomSubcat(true)
      setForm(f => ({ ...f, subcategory: '', achievement: '' }))
    } else {
      setCustomSubcat(false)
      setForm(f => ({ ...f, subcategory: val, achievement: '' }))
      setCustomAchievement(false)
    }
  }

  const setAchievementVal = (val) => {
    if (val === '__other__') {
      setCustomAchievement(true)
      setForm(f => ({ ...f, achievement: '' }))
    } else {
      setCustomAchievement(false)
      setForm(f => ({ ...f, achievement: val }))
    }
  }

  const handleSave = async () => {
    if (!form.achievement.trim() || !form.category) return
    setSaving(true)
    setError(null)
    try {
      if (editId) {
        await api.updateAchievement(editId, form)
      } else {
        await api.createAchievement({ ...form, org_id: orgId, player_id: playerId, player_name: playerName || '' })
      }
      const updated = await api.listAchievements(orgId, { playerId })
      setAchievements(updated)
      setAdding(false)
      setEditId(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this achievement?')) return
    await api.deleteAchievement(id, orgId)
    setAchievements(prev => prev.filter(a => a.id !== id))
  }

  if (achievements === null) return <div className="p-5"><LoadingSpinner size="sm" /></div>

  const inputCls = 'w-full bg-navy-800 border border-navy-600 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent placeholder-slate-500'

  const seasonMap = Object.fromEntries(seasons.map(s => [s.id, s.name]))
  const seasonDisplay = (s) => !s || s === 'All Time' ? 'All Time' : (seasonMap[s] || s.replace(/_/g, '/'))

  // Group by season then category
  const grouped = {}
  for (const a of achievements) {
    const s = a.season || 'All Time'
    if (!grouped[s]) grouped[s] = {}
    if (!grouped[s][a.category]) grouped[s][a.category] = []
    grouped[s][a.category].push(a)
  }
  const groupedSeasons = Object.keys(grouped).sort((a, b) => {
    if (a === 'All Time') return 1
    if (b === 'All Time') return -1
    return b.localeCompare(a)
  })

  return (
    <div>
      <div className="px-5 py-4 border-b border-navy-700 flex items-center justify-between">
        <h3 className="display-heading text-lg text-white">ACHIEVEMENTS & HONOURS</h3>
        <button onClick={openAdd} className="btn-primary text-xs">+ Add</button>
      </div>

      {adding && (
        <div className="px-5 py-4 border-b border-navy-700 bg-navy-800/50">
          <h4 className="text-sm font-semibold text-white mb-3">{editId ? 'Edit Achievement' : 'Add Achievement'}</h4>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
            <div>
              <label className="section-label mb-1 block">Season {form.category === 'Office Bearer' ? 'Start' : ''}</label>
              <select className={inputCls} value={form.season} onChange={e => setForm(f => ({ ...f, season: e.target.value }))}>
                <option value="">— All Time —</option>
                {seasons.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            {form.category === 'Office Bearer' && (
              <div>
                <label className="section-label mb-1 block">Season End</label>
                <select className={inputCls} value={form.season_end} onChange={e => setForm(f => ({ ...f, season_end: e.target.value }))}>
                  <option value="">— Present —</option>
                  {seasons.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
            )}
            <div>
              <label className="section-label mb-1 block">Category *</label>
              <select className={inputCls} value={form.category} onChange={e => setCategory(e.target.value)}>
                {CATEGORIES.map(c => <option key={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="section-label mb-1 block">Subcategory / Grade</label>
              {!customSubcat && subcatOptions.length > 0 ? (
                <select className={inputCls} value={form.subcategory} onChange={e => setSubcat(e.target.value)}>
                  <option value="">— Select —</option>
                  {subcatOptions.map(s => <option key={s}>{s}</option>)}
                  <option value="__other__">Other…</option>
                </select>
              ) : (
                <div className="flex gap-1">
                  <input className={inputCls} placeholder="e.g. 1st XI, WASTCA" value={form.subcategory}
                    onChange={e => setForm(f => ({ ...f, subcategory: e.target.value, achievement: '' }))} />
                  {customSubcat && (
                    <button onClick={() => { setCustomSubcat(false); setForm(f => ({ ...f, subcategory: '' })) }} className="text-slate-500 hover:text-white px-1 text-lg">×</button>
                  )}
                </div>
              )}
            </div>
            <div className="md:col-span-2">
              <label className="section-label mb-1 block">Achievement *</label>
              {!customAchievement && achievementOptions.length > 0 ? (
                <select className={inputCls} value={form.achievement} onChange={e => setAchievementVal(e.target.value)}>
                  <option value="">— Select —</option>
                  {achievementOptions.map(a => <option key={a}>{a}</option>)}
                  <option value="__other__">Other…</option>
                </select>
              ) : (
                <div className="flex gap-1">
                  <input className={inputCls} placeholder="e.g. Best & Fairest, President" value={form.achievement}
                    onChange={e => setForm(f => ({ ...f, achievement: e.target.value }))} />
                  {customAchievement && (
                    <button onClick={() => { setCustomAchievement(false); setForm(f => ({ ...f, achievement: '' })) }} className="text-slate-500 hover:text-white px-1 text-lg">×</button>
                  )}
                </div>
              )}
            </div>
            <div>
              <label className="section-label mb-1 block">Detail</label>
              <input className={inputCls} placeholder="e.g. 436 runs at 39.64" value={form.detail}
                onChange={e => setForm(f => ({ ...f, detail: e.target.value }))} />
            </div>
          </div>
          {error && <p className="text-red-400 text-xs mb-2">{error}</p>}
          <div className="flex gap-2">
            <button onClick={handleSave} disabled={saving} className="btn-primary text-xs">
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button onClick={() => { setAdding(false); setEditId(null) }} className="btn-ghost text-xs">Cancel</button>
          </div>
        </div>
      )}

      {achievements.length === 0 && !adding && (
        <p className="text-slate-500 text-sm px-5 py-8 text-center">No achievements recorded yet.</p>
      )}

      {groupedSeasons.map(season => (
        <div key={season} className="border-b border-navy-700 last:border-0">
          <div className="px-5 py-3 bg-navy-800/30">
            <span className="text-accent font-mono font-bold text-sm">{seasonDisplay(season)}</span>
          </div>
          {Object.entries(grouped[season]).map(([cat, items]) => (
            <div key={cat} className="px-5 py-3">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-base">{CATEGORY_ICONS[cat] || '🏅'}</span>
                <span className="section-label text-xs">{cat.toUpperCase()}</span>
              </div>
              <div className="space-y-1.5">
                {items.map(a => (
                  <div key={a.id} className="flex items-start justify-between gap-2 group">
                    <div className="flex-1 min-w-0">
                      <span className="text-white text-sm font-medium">{a.achievement}</span>
                      {a.subcategory && <span className="text-slate-500 text-sm"> — {a.subcategory}</span>}
                      {a.season_end && (
                        <span className="text-xs text-slate-500 ml-2 font-mono">
                          {seasonDisplay(a.season)} — {seasonDisplay(a.season_end)}
                        </span>
                      )}
                      {a.detail && <span className="text-slate-400 text-xs ml-2">({a.detail})</span>}
                    </div>
                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                      <button onClick={() => openEdit(a)} className="text-xs text-slate-400 hover:text-white px-1.5 py-0.5 rounded hover:bg-navy-700">Edit</button>
                      <button onClick={() => handleDelete(a.id)} className="text-xs text-red-400 hover:text-red-300 px-1.5 py-0.5 rounded hover:bg-navy-700">✕</button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

function daysSince(dateStr) {
  if (!dateStr) return null
  const diff = Math.floor((new Date() - new Date(dateStr)) / (1000 * 60 * 60 * 24))
  return diff
}

function formatDaysSince(days) {
  if (days === null) return '—'
  if (days === 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 7) return `${days}d ago`
  if (days < 30) return `${Math.floor(days / 7)}w ago`
  if (days < 365) return `${Math.floor(days / 30)}mo ago`
  return `${Math.floor(days / 365)}y ago`
}

function ActivityBadge({ label, value, sub, accent = false }) {
  return (
    <div className={clsx(
      'bg-navy-800 border rounded-xl p-4 flex flex-col gap-1',
      accent ? 'border-accent/30' : 'border-navy-700'
    )}>
      <span className="section-label">{label}</span>
      <span className={clsx('stat-number font-bold text-lg leading-tight', accent ? 'text-accent' : 'text-white')}>
        {value ?? '—'}
      </span>
      {sub && <span className="text-xs text-slate-500">{sub}</span>}
    </div>
  )
}

function UpcomingMilestonesSection({ data }) {
  if (!data?.length) return null
  const ICONS = { runs: '🏏', wickets: '⚡', matches: '📅' }
  return (
    <div className="mb-8">
      <h3 className="display-heading text-lg text-white mb-4">CHASING</h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {data.map((m, i) => {
          const pct = Math.round((m.current / m.target) * 100)
          return (
            <div key={i} className="bg-navy-800 border border-navy-700 rounded-xl p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-slate-400 flex items-center gap-1.5">
                  <span>{ICONS[m.type] || '🎯'}</span>
                  {m.target.toLocaleString()} {m.type}
                </span>
                <span className="text-xs text-accent font-mono font-bold">{m.needed} to go</span>
              </div>
              <div className="h-2 bg-navy-700 rounded-full overflow-hidden mb-1">
                <div className="h-full bg-accent rounded-full" style={{ width: `${pct}%` }} />
              </div>
              <div className="flex justify-between">
                <span className="text-xs text-slate-600">{m.current.toLocaleString()}</span>
                <span className="text-xs text-slate-600">{pct}%</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function SeasonBattingTable({ data }) {
  if (!data?.length) return <p className="text-slate-500 text-sm px-5 py-4">No batting data.</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-navy-700">
            <th className="table-header">Season</th>
            <th className="table-header text-right">Mat</th>
            <th className="table-header text-right">Inn</th>
            <th className="table-header text-right">Runs</th>
            <th className="table-header text-right">Avg</th>
            <th className="table-header text-right">HS</th>
            <th className="table-header text-right">SR</th>
            <th className="table-header text-right">50s</th>
            <th className="table-header text-right">100s</th>
            <th className="table-header text-right">6s</th>
            <th className="table-header text-right">4s</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell text-white font-medium">{row.season_name}</td>
              <td className="table-cell stat-number text-right text-slate-400">{row.matches ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-400">{row.batting_innings ?? '—'}</td>
              <td className="table-cell text-right">
                <span className={clsx('stat-number font-bold',
                  row.total_runs >= 500 ? 'text-amber-cricket' : row.total_runs >= 200 ? 'text-accent' : 'text-white'
                )}>
                  {row.total_runs ?? '—'}
                </span>
              </td>
              <td className="table-cell stat-number text-right text-slate-300">
                {row.batting_average != null ? Number(row.batting_average).toFixed(1) : '—'}
              </td>
              <td className="table-cell stat-number text-right text-slate-300">{row.high_score ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-400">
                {row.strike_rate != null ? Number(row.strike_rate).toFixed(1) : '—'}
              </td>
              <td className="table-cell stat-number text-right text-slate-300">{row.fifties || '—'}</td>
              <td className="table-cell stat-number text-right">
                <span className={row.hundreds > 0 ? 'text-amber-cricket font-bold' : 'text-slate-300'}>
                  {row.hundreds || '—'}
                </span>
              </td>
              <td className="table-cell stat-number text-right text-slate-400">{row.total_sixes || '—'}</td>
              <td className="table-cell stat-number text-right text-slate-400">{row.total_fours || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SeasonBowlingTable({ data }) {
  const hasAnyWickets = data?.some(r => (r.total_wickets ?? 0) > 0)
  if (!hasAnyWickets) return <p className="text-slate-500 text-sm px-5 py-4">No bowling data.</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-navy-700">
            <th className="table-header">Season</th>
            <th className="table-header text-right">Mat</th>
            <th className="table-header text-right">O</th>
            <th className="table-header text-right">M</th>
            <th className="table-header text-right">R</th>
            <th className="table-header text-right">W</th>
            <th className="table-header text-right">Avg</th>
            <th className="table-header text-right">Econ</th>
            <th className="table-header text-right">Best</th>
            <th className="table-header text-right">5W</th>
          </tr>
        </thead>
        <tbody>
          {data.filter(r => (r.total_wickets ?? 0) > 0 || (r.total_overs ?? 0) > 0).map((row, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell text-white font-medium">{row.season_name}</td>
              <td className="table-cell stat-number text-right text-slate-400">{row.matches ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-400">{row.total_overs ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-400">{row.total_maidens ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-300">{row.total_runs ?? '—'}</td>
              <td className="table-cell text-right">
                <span className={clsx('stat-number font-bold',
                  row.total_wickets >= 50 ? 'text-amber-cricket' : row.total_wickets >= 20 ? 'text-accent' : 'text-white'
                )}>
                  {row.total_wickets ?? '—'}
                </span>
              </td>
              <td className="table-cell stat-number text-right text-slate-300">
                {row.bowling_average != null ? Number(row.bowling_average).toFixed(1) : '—'}
              </td>
              <td className="table-cell stat-number text-right text-slate-300">
                {row.economy != null ? Number(row.economy).toFixed(2) : '—'}
              </td>
              <td className="table-cell stat-number text-right text-slate-300">
                {row.best_bowling_figures || (row.best_bowling_wickets > 0 ? `${row.best_bowling_wickets}w` : '—')}
              </td>
              <td className="table-cell stat-number text-right">
                <span className={row.five_fors > 0 ? 'text-amber-cricket font-bold' : 'text-slate-400'}>
                  {row.five_fors || '—'}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SeasonChart({ data }) {
  if (!data?.length) return <p className="text-slate-500 text-sm">No season data</p>
  const chartData = [...data].reverse()
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis dataKey="season_name" tick={{ fill: '#64748b', fontSize: 11 }} />
        <YAxis yAxisId="left" tick={{ fill: '#64748b', fontSize: 11 }} />
        <YAxis yAxisId="right" orientation="right" tick={{ fill: '#64748b', fontSize: 11 }} />
        <Tooltip
          contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8 }}
          labelStyle={{ color: '#94a3b8' }}
          itemStyle={{ color: '#fff' }}
        />
        <Legend wrapperStyle={{ color: '#94a3b8', fontSize: 12 }} />
        <Bar yAxisId="left" dataKey="total_runs" name="Runs" fill="#16c784" radius={[3, 3, 0, 0]} />
        <Bar yAxisId="right" dataKey="total_wickets" name="Wickets" fill="#3b82f6" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

function MilestoneTimeline({ data }) {
  if (!data?.length) return <p className="text-slate-500 text-sm px-4 py-4">No milestones recorded yet.</p>

  const grouped = data.reduce((acc, m) => {
    const key = m.milestone_type
    if (!acc[key]) acc[key] = []
    acc[key].push(m)
    return acc
  }, {})

  const TYPE_ORDER = ['runs', 'wickets', 'matches', 'catches']
  const typeLabels = { runs: 'Runs', wickets: 'Wickets', matches: 'Matches', catches: 'Catches' }
  const orderedGroups = TYPE_ORDER.filter(t => grouped[t])
    .concat(Object.keys(grouped).filter(t => !TYPE_ORDER.includes(t)))
    .map(t => [t, [...grouped[t]].sort((a, b) => b.milestone_value - a.milestone_value)])

  return (
    <div className="px-4 py-4 space-y-6">
      {orderedGroups.map(([type, items]) => (
        <div key={type}>
          <h4 className="display-heading text-sm text-slate-400 mb-3 uppercase">
            {typeLabels[type] || type}
          </h4>
          <div className="flex flex-wrap gap-2">
            {items.map((m, i) => (
              <div key={i} className="flex items-center gap-2 bg-navy-800 border border-navy-700 rounded-lg px-3 py-2">
                <span className="text-accent stat-number font-bold text-lg">
                  {m.milestone_value.toLocaleString()}
                </span>
                <div className="text-xs text-slate-400">
                  {m.detail && <div>{m.detail}</div>}
                  {m.game_date && <div className="text-slate-600">{m.game_date}</div>}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function PlayerProfile() {
  const { playerId } = useParams()
  const [tab, setTab] = useState('batting')
  const [seasonId, setSeasonId] = useState(null)
  const [seasons, setSeasons] = useState([])
  const { data, loading, error } = usePlayerStats(playerId, { seasonId })

  const [activity, setActivity] = useState(null)
  const [upcomingMilestones, setUpcomingMilestones] = useState(null)
  const [milestones, setMilestones] = useState(null)
  const [seasonStats, setSeasonStats] = useState(null)
  const [achievementsLoaded, setAchievementsLoaded] = useState(false)
  const [headerAchievements, setHeaderAchievements] = useState([])

  // Load season stats and activity eagerly on mount
  useEffect(() => {
    if (!playerId) return
    api.getPlayerSeasons(playerId).then(setSeasonStats).catch(() => setSeasonStats([]))
    api.getPlayerActivity(playerId).then(setActivity).catch(() => setActivity({}))
    api.getPlayerUpcomingMilestones(playerId).then(setUpcomingMilestones).catch(() => setUpcomingMilestones([]))
  }, [playerId])

  useEffect(() => {
    if (!data?.player?.organisation_id) return
    api.getOrgSeasons(data.player.organisation_id).then(setSeasons).catch(() => {})
    sessionStorage.setItem('bs_last_org_id', data.player.organisation_id)
    window.dispatchEvent(new CustomEvent('bs_org_changed'))
    // Load achievements for header display
    api.listAchievements(data.player.organisation_id, { playerId })
      .then(list => setHeaderAchievements(list || []))
      .catch(() => {})
  }, [data?.player?.organisation_id, playerId])

  const handleTabChange = useCallback((t) => {
    setTab(t)
    if (t === 'milestones' && milestones === null) {
      api.getPlayerMilestones(playerId).then(setMilestones).catch(() => setMilestones([]))
    }
    if (t === 'achievements') setAchievementsLoaded(true)
  }, [playerId, milestones])

  // Hooks must run before any early returns — derive display stats for stat cards
  const rawData = data
  const cb = rawData?.career_batting
  const cbw = rawData?.career_bowling
  const cf = rawData?.career_fielding
  const player = rawData?.player

  const displayBatting = useMemo(() => {
    if (!seasonId || !seasonStats?.length) return cb
    const s = seasonStats.find(r => r.season_id === seasonId)
    if (!s) return cb
    return { matches: s.matches, innings: s.batting_innings, total_runs: s.total_runs, average: s.batting_average, high_score: s.high_score, strike_rate: s.strike_rate, hundreds: s.hundreds, fifties: s.fifties }
  }, [seasonId, seasonStats, cb])

  const displayBowling = useMemo(() => {
    if (!seasonId || !seasonStats?.length) return cbw
    const s = seasonStats.find(r => r.season_id === seasonId)
    if (!s) return cbw
    return { total_wickets: s.total_wickets, economy: s.economy, best_bowling_figures: s.best_bowling_figures, best_figures_wickets: s.best_bowling_wickets }
  }, [seasonId, seasonStats, cbw])

  if (loading) return <LoadingSpinner message="Loading player stats…" />
  if (error) return <div className="max-w-7xl mx-auto px-4 py-16 text-red-400">Error: {error}</div>
  if (!data) return null

  const { career_batting: _cb, career_bowling: _cbw, career_fielding: _cf } = data

  const badgeMilestones = []
  if (cb?.hundreds > 0) badgeMilestones.push(`${cb.hundreds} ${cb.hundreds === 1 ? 'century' : 'centuries'}`)
  if (cb?.fifties > 0) badgeMilestones.push(`${cb.fifties} ${cb.fifties === 1 ? 'fifty' : 'fifties'}`)
  if (cbw?.total_wickets >= 5) badgeMilestones.push(`${cbw.total_wickets} career wickets`)
  if (cbw?.best_figures_wickets >= 5) badgeMilestones.push(`${cbw.best_figures_wickets}-wicket haul`)

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {/* Player header */}
      <div className="mb-8">
        <div className="accent-bar mb-4" />
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="display-heading text-5xl md:text-6xl text-white leading-none">
              {(player.display_name || player.name).toUpperCase()}
            </h1>
            {badgeMilestones.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-3">
                {badgeMilestones.map(m => (
                  <span key={m} className="badge bg-accent/10 text-accent">{m}</span>
                ))}
              </div>
            )}
            {headerAchievements.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-2">
                {headerAchievements.slice(0, 6).map(a => (
                  <span key={a.id} className="badge bg-navy-700 text-slate-300 border border-navy-600">
                    {a.subcategory || a.category}{a.achievement ? ` — ${a.achievement}` : ''}{a.season_end ? ` (${a.season_end})` : a.season ? ` (${a.season})` : ''}
                  </span>
                ))}
              </div>
            )}
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            {seasons.length > 0 && (
              <select
                value={seasonId || ''}
                onChange={e => setSeasonId(e.target.value || null)}
                className="bg-navy-800 border border-navy-600 text-white text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-accent"
              >
                <option value="">Career</option>
                {seasons.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            )}
            <Link to={`/players/${playerId}/share`} className="btn-ghost border border-navy-600 text-xs">
              Share ↗
            </Link>
            {!player.claimed && (
              <button onClick={() => api.claimPlayer(playerId)} className="btn-primary text-xs">
                Claim Profile
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Upcoming milestones progress bars */}
      {upcomingMilestones !== null && upcomingMilestones.length > 0 && (
        <UpcomingMilestonesSection data={upcomingMilestones} />
      )}

      {/* Stat cards — season-aware */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3 mb-10">
        <StatCard label="Matches" value={seasonId ? (displayBatting?.matches ?? '—') : (cb?.games ?? '—')} />
        <StatCard label="Innings" value={displayBatting?.innings ?? '—'} />
        <StatCard label="Runs" value={displayBatting?.total_runs ?? '—'} accent />
        <StatCard label="Average" value={displayBatting?.average ?? '—'} />
        <StatCard label="High Score" value={displayBatting?.high_score != null ? displayBatting.high_score : '—'} />
        <StatCard label="Wickets" value={displayBowling?.total_wickets ?? '—'} />
        <StatCard label="Economy" value={displayBowling?.economy ?? '—'} />
        <StatCard label="Best Spell" value={displayBowling?.best_bowling_figures ?? cbw?.best_bowling_figures ?? '—'} />
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-1 mb-4 border-b border-navy-700">
        {TABS.map(t => (
          <button
            key={t}
            onClick={() => handleTabChange(t)}
            className={clsx(
              'px-4 py-2.5 text-sm font-semibold uppercase tracking-wider transition-colors border-b-2 -mb-px',
              tab === t
                ? 'text-accent border-accent'
                : 'text-slate-500 border-transparent hover:text-white'
            )}
          >
            {t}
          </button>
        ))}
        {cf && (
          <div className="ml-auto flex items-center gap-4 pb-2 text-sm text-slate-400">
            <span>Catches: <strong className="text-white stat-number">{cf.total_catches ?? 0}</strong></span>
            <span>Run outs: <strong className="text-white stat-number">{cf.total_run_outs ?? 0}</strong></span>
            {cf.total_stumpings > 0 && <span>Stumpings: <strong className="text-white stat-number">{cf.total_stumpings}</strong></span>}
          </div>
        )}
      </div>

      {/* Tab content */}
      <div className="card overflow-hidden">
        {tab === 'batting' && (
          <>
            <div className="px-5 py-4 border-b border-navy-700 flex items-center justify-between">
              <h3 className="display-heading text-lg text-white">BATTING BY SEASON</h3>
              <span className="section-label">{seasonStats?.length ?? 0} seasons</span>
            </div>
            {seasonStats === null
              ? <div className="p-5"><LoadingSpinner size="sm" /></div>
              : <SeasonBattingTable data={seasonStats} />
            }
            {/* Form charts if we have recent data */}
            {seasonStats !== null && seasonStats.length > 0 && (
              <div className="px-5 pt-4 pb-5 border-t border-navy-700">
                <h4 className="display-heading text-sm text-slate-400 mb-4">RUNS TREND</h4>
                <SeasonChart data={seasonStats} />
              </div>
            )}
          </>
        )}

        {tab === 'bowling' && (
          <>
            <div className="px-5 py-4 border-b border-navy-700 flex items-center justify-between">
              <h3 className="display-heading text-lg text-white">BOWLING BY SEASON</h3>
            </div>
            {seasonStats === null
              ? <div className="p-5"><LoadingSpinner size="sm" /></div>
              : <SeasonBowlingTable data={seasonStats} />
            }
          </>
        )}

        {tab === 'analysis' && (
          <div className="p-5 space-y-8">
            <div>
              <h3 className="display-heading text-lg text-white mb-4">SEASON BY SEASON</h3>
              {seasonStats === null
                ? <LoadingSpinner size="sm" />
                : <SeasonChart data={seasonStats} />
              }
            </div>
            {seasonStats !== null && seasonStats.length > 0 && (
              <div>
                <h3 className="display-heading text-lg text-white mb-4">FULL SEASON HISTORY</h3>
                <SeasonBattingTable data={seasonStats} />
              </div>
            )}
            <div className="rounded-lg border border-navy-700 p-4 text-center">
              <p className="text-slate-500 text-sm">
                Dismissal breakdown, by-position, and partnership analysis require game-level data which is not available at the current API tier.
              </p>
            </div>
          </div>
        )}

        {tab === 'milestones' && (
          <>
            <div className="px-5 py-4 border-b border-navy-700">
              <h3 className="display-heading text-lg text-white">CAREER MILESTONES</h3>
            </div>
            {milestones === null
              ? <p className="text-slate-500 text-sm px-5 py-4">Loading…</p>
              : <MilestoneTimeline data={milestones} />
            }
          </>
        )}

        {tab === 'achievements' && achievementsLoaded && (
          <AchievementsSection playerId={playerId} orgId={player.organisation_id} playerName={player.name} />
        )}
      </div>
    </div>
  )
}
