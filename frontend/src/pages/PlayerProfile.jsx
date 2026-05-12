import { useParams, Link } from 'react-router-dom'
import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Legend,
  LineChart, Line, PieChart, Pie, Cell, ReferenceLine,
} from 'recharts'
import { api } from '../lib/api'
import { useAuth } from '../contexts/AuthContext'
import { useClubTheme } from '../hooks/useClubTheme'
import { getSubcategories, getAchievements } from '../lib/achievementOptions'
import { usePlayerStats } from '../hooks/usePlayerStats'
import StatCard from '../components/StatCard'
import TrendChart from '../components/TrendChart'
import RunsChart from '../components/RunsChart'
import LoadingSpinner from '../components/LoadingSpinner'
import { CATEGORY_ICON_SRC, MILESTONE_ICON_SRC, ThiingIcon, thiings } from '../assets/thiings'
import clsx from 'clsx'

const TABS = ['batting', 'bowling', 'fielding', 'analysis', 'milestones', 'achievements']

function formatSeasonShort(value, seasons) {
  if (!value) return null
  const match = seasons?.find(s => s.id === value)
  const name = match ? match.name : String(value)
  // Patterns: "2019_20", "2019/20", "Summer 2019/20", "Summer 2019_20"
  const m = name.match(/(\d{2})(\d{2})\s*[\/_-]\s*(\d{2})/)
  if (m) return `${m[2]}/${m[3]}`
  const single = name.match(/\b(\d{4})\b/)
  if (single) return single[1].slice(2)
  return name
}

function formatRange(inst, seasons) {
  const start = formatSeasonShort(inst.season, seasons)
  const end = formatSeasonShort(inst.season_end, seasons)
  if (start && end && start !== end) return `${start}–${end}`
  return start || end || null
}

function formatAchievementBadge(a, seasons) {
  const label = a.achievement || a.subcategory || a.category

  // Cap Number pills: the detail (e.g. "#32") is the headline number, not the season.
  if (a.category === 'Milestone' && a.subcategory === 'Cap Number' && a.detail) {
    return `${label} ${a.detail}`
  }

  // Deduped multi-instance pill (e.g. "3rd XI Captain 17/18, 21/22")
  if (a._instances && a._instances.length > 1) {
    const ranges = a._instances.map(i => formatRange(i, seasons)).filter(Boolean)
    if (ranges.length) return `${label} ${ranges.join(', ')}`
  }

  // Single instance
  const range = formatRange(a, seasons)
  return range ? `${label} (${range})` : label
}

// Exec-committee roles that carry weight beyond a typical year role.
const EXEC_RANK = { 'president': 1, 'vice president': 2, 'vice-president': 2, 'secretary': 3, 'treasurer': 3 }

function headerPriority(a) {
  if (a.category === 'Hall of Fame') return 0
  if (a.category === 'Life Membership') return 1.5
  if (a.category === 'Office Bearer' && a.subcategory === 'Executive Committee') {
    return EXEC_RANK[(a.achievement || '').toLowerCase()] ?? 3
  }
  if (a.category === 'Milestone') {
    if (a.subcategory === 'Cap Number') return 2.5
    if (a.subcategory === 'Games') {
      const n = parseInt((a.achievement || '').match(/(\d+)/)?.[1] || '0', 10)
      if (n >= 500) return 3
      if (n >= 300) return 4.5
      if (n >= 200) return 5
      return 9
    }
    return 9
  }
  if (a.category === 'Premiership') return 4
  if (a.category === 'Association Award') return 6
  if (a.category === 'Club Award') return 7
  if (a.category === 'Office Bearer') return 8  // captaincy + other roles
  return 99
}

function rankedHeaderAchievements(items) {
  // Group by (category, subcategory, achievement) so a multi-term role becomes
  // a single pill listing all its seasons.
  const map = new Map()
  for (const a of items || []) {
    const key = `${a.category}|${a.subcategory || ''}|${a.achievement}`
    const cur = map.get(key)
    if (!cur) {
      map.set(key, { ...a, _instances: [a] })
    } else {
      cur._instances.push(a)
      // Surface the newest instance's fields (season, detail) at the top level
      // so priority sorting and detail display work consistently.
      if ((a.season || '') > (cur.season || '')) {
        Object.assign(cur, a, { _instances: cur._instances })
      }
    }
  }
  // Sort instances within each group oldest → newest for "17/18, 21/22" reading order.
  for (const g of map.values()) {
    g._instances.sort((x, y) => (x.season || '').localeCompare(y.season || ''))
  }
  return [...map.values()].sort((a, b) => {
    const pa = headerPriority(a)
    const pb = headerPriority(b)
    if (pa !== pb) return pa - pb
    return (b.season || '').localeCompare(a.season || '')
  })
}

function useSortable(rows, defaultKey, defaultDir = 'desc') {
  const [sortKey, setSortKey] = useState(defaultKey)
  const [sortDir, setSortDir] = useState(defaultDir)

  const sorted = useMemo(() => {
    if (!Array.isArray(rows) || !sortKey) return rows
    const dir = sortDir === 'asc' ? 1 : -1
    return [...rows].sort((a, b) => {
      const av = a?.[sortKey]
      const bv = b?.[sortKey]
      if (av == null && bv == null) return 0
      if (av == null) return 1
      if (bv == null) return -1
      const an = typeof av === 'number' ? av : Number(av)
      const bn = typeof bv === 'number' ? bv : Number(bv)
      if (!Number.isNaN(an) && !Number.isNaN(bn) && (typeof av !== 'string' || /^-?\d+(\.\d+)?$/.test(av))) {
        return (an - bn) * dir
      }
      return String(av).localeCompare(String(bv)) * dir
    })
  }, [rows, sortKey, sortDir])

  function request(key, defaultDirForKey = 'desc') {
    if (key === sortKey) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir(defaultDirForKey)
    }
  }

  return { sorted, sortKey, sortDir, request }
}

function SortHeader({ label, sortKey, currentKey, currentDir, onSort, defaultDir = 'desc', align = 'left', className = '' }) {
  const active = sortKey === currentKey
  const arrow = active ? (currentDir === 'asc' ? ' ↑' : ' ↓') : ''
  return (
    <th
      onClick={() => onSort(sortKey, defaultDir)}
      className={clsx(
        'table-header cursor-pointer select-none hover:text-white transition-colors',
        align === 'right' && 'text-right',
        className,
      )}
    >
      {label}
      <span className="text-accent text-xs">{arrow}</span>
    </th>
  )
}

function PartnershipsTable({ partnerships }) {
  const { sorted, sortKey, sortDir, request } = useSortable(partnerships, 'total_runs', 'desc')
  return (
    <div>
      <h3 className="display-heading text-lg text-white mb-4">TOP PARTNERSHIPS</h3>
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-navy-700">
              <SortHeader label="Partner" sortKey="partner_name" currentKey={sortKey} currentDir={sortDir} onSort={request} defaultDir="asc" />
              <SortHeader label="Best" sortKey="best_runs" currentKey={sortKey} currentDir={sortDir} onSort={request} align="right" />
              <SortHeader label="Total" sortKey="total_runs" currentKey={sortKey} currentDir={sortDir} onSort={request} align="right" />
              <SortHeader label="Times" sortKey="partnership_count" currentKey={sortKey} currentDir={sortDir} onSort={request} align="right" className="hidden sm:table-cell" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((p, i) => (
              <tr key={i} className="table-row">
                <td className="table-cell">
                  {p.partner_id
                    ? <Link to={`/players/${p.partner_id}`} className="text-white hover:text-accent transition-colors">{p.partner_name ?? '—'}</Link>
                    : <span className="text-slate-400">{p.partner_name ?? '—'}</span>}
                </td>
                <td className="table-cell stat-number text-right font-bold text-accent">{p.best_runs ?? '—'}</td>
                <td className="table-cell stat-number text-right text-slate-300">{p.total_runs ?? '—'}</td>
                <td className="table-cell stat-number text-right text-slate-500 hidden sm:table-cell">{p.partnership_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ByGradeTable({ rows }) {
  const { sorted, sortKey, sortDir, request } = useSortable(rows, 'runs', 'desc')
  return (
    <div>
      <h3 className="display-heading text-lg text-white mb-4">BATTING BY GRADE</h3>
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-navy-700">
              <SortHeader label="Grade" sortKey="grade_name" currentKey={sortKey} currentDir={sortDir} onSort={request} defaultDir="asc" />
              <SortHeader label="Inn" sortKey="innings" currentKey={sortKey} currentDir={sortDir} onSort={request} align="right" />
              <SortHeader label="Runs" sortKey="runs" currentKey={sortKey} currentDir={sortDir} onSort={request} align="right" />
              <SortHeader label="Avg" sortKey="average" currentKey={sortKey} currentDir={sortDir} onSort={request} align="right" />
              <SortHeader label="HS" sortKey="high_score" currentKey={sortKey} currentDir={sortDir} onSort={request} align="right" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((r, i) => (
              <tr key={i} className="table-row">
                <td className="table-cell text-white">{r.grade_name}</td>
                <td className="table-cell stat-number text-right text-slate-400">{r.innings}</td>
                <td className="table-cell stat-number text-right text-accent font-bold">{r.runs}</td>
                <td className="table-cell stat-number text-right text-slate-300">{r.average ?? '—'}</td>
                <td className="table-cell stat-number text-right text-slate-300">{r.high_score ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ByPositionTable({ rows }) {
  const { sorted, sortKey, sortDir, request } = useSortable(rows, 'batting_position', 'asc')
  return (
    <div>
      <h3 className="display-heading text-lg text-white mb-4">BATTING BY POSITION</h3>
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-navy-700">
              <SortHeader label="Position" sortKey="batting_position" currentKey={sortKey} currentDir={sortDir} onSort={request} defaultDir="asc" />
              <SortHeader label="Inn" sortKey="innings" currentKey={sortKey} currentDir={sortDir} onSort={request} align="right" />
              <SortHeader label="Runs" sortKey="runs" currentKey={sortKey} currentDir={sortDir} onSort={request} align="right" />
              <SortHeader label="Avg" sortKey="average" currentKey={sortKey} currentDir={sortDir} onSort={request} align="right" />
              <SortHeader label="HS" sortKey="high_score" currentKey={sortKey} currentDir={sortDir} onSort={request} align="right" />
              <SortHeader label="SR" sortKey="avg_strike_rate" currentKey={sortKey} currentDir={sortDir} onSort={request} align="right" className="hidden sm:table-cell" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((r, i) => (
              <tr key={i} className="table-row">
                <td className="table-cell stat-number text-white">#{r.batting_position}</td>
                <td className="table-cell stat-number text-right text-slate-400">{r.innings}</td>
                <td className="table-cell stat-number text-right text-accent font-bold">{r.runs}</td>
                <td className="table-cell stat-number text-right text-slate-300">{r.average ?? '—'}</td>
                <td className="table-cell stat-number text-right text-slate-300">{r.high_score ?? '—'}</td>
                <td className="table-cell stat-number text-right text-slate-500 hidden sm:table-cell">{r.avg_strike_rate ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const CATEGORIES = ['Club Award', 'Association Award', 'Office Bearer', 'Premiership', 'Hall of Fame', 'Life Membership', 'Milestone']

function AchievementsSection({ playerId, orgId, playerName }) {
  const { user } = useAuth()
  const canEdit = !!user
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

  // Partition achievements into four buckets based on type rather than season,
  // so the player's permanent honours sit above their year-by-year roles.
  const honours = []      // HoF, Life Membership, Premiership, Cap Number
  const roles = []        // Office Bearer
  const awards = []       // Club Award + Association Award
  const milestones = []   // Other Milestones (Games, Runs, Wickets, etc.)
  for (const a of achievements) {
    if (a.category === 'Hall of Fame' || a.category === 'Life Membership' || a.category === 'Premiership') {
      honours.push(a)
    } else if (a.category === 'Milestone' && a.subcategory === 'Cap Number') {
      honours.push(a)
    } else if (a.category === 'Office Bearer') {
      roles.push(a)
    } else if (a.category === 'Club Award' || a.category === 'Association Award') {
      awards.push(a)
    } else if (a.category === 'Milestone') {
      milestones.push(a)
    } else {
      awards.push(a) // safety net for any unknown category
    }
  }

  // Sort awards / milestones newest-first
  const bySeasonDesc = (a, b) => (b.season || '').localeCompare(a.season || '')
  honours.sort((a, b) => {
    const pa = headerPriority(a); const pb = headerPriority(b)
    if (pa !== pb) return pa - pb
    return bySeasonDesc(a, b)
  })
  awards.sort(bySeasonDesc)
  milestones.sort(bySeasonDesc)

  // Group roles by (subcategory, achievement) so a 3-time captain becomes one card.
  const rolesGrouped = new Map()
  for (const r of roles) {
    const key = `${r.subcategory || ''}|${r.achievement}`
    if (!rolesGrouped.has(key)) {
      rolesGrouped.set(key, { subcategory: r.subcategory, achievement: r.achievement, instances: [] })
    }
    rolesGrouped.get(key).instances.push(r)
  }
  for (const g of rolesGrouped.values()) g.instances.sort(bySeasonDesc)
  const rolesList = [...rolesGrouped.values()].sort((a, b) => {
    const sa = a.instances[0]?.season || ''
    const sb = b.instances[0]?.season || ''
    return sb.localeCompare(sa)
  })

  const seasonRange = (a) => {
    const s = seasonDisplay(a.season)
    if (a.season_end && a.season_end !== a.season) return `${s} — ${seasonDisplay(a.season_end)}`
    return s
  }

  const categoryIcon = (a) => CATEGORY_ICON_SRC[a.category] || thiings.goldMedal

  return (
    <div>
      <div className="px-5 py-4 border-b border-navy-700 flex items-center justify-between">
        <h3 className="display-heading text-lg text-white">ACHIEVEMENTS & HONOURS</h3>
        {canEdit && <button onClick={openAdd} className="btn-primary text-xs">+ Add</button>}
      </div>

      {adding && canEdit && (
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

      <div className="p-5 space-y-6">
        {honours.length > 0 && (
          <section>
            <h4 className="section-label text-xs mb-3 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" />
              Honours
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
              {honours.map(a => (
                <div
                  key={a.id}
                  className="rounded-lg border border-l-2 border-amber-400/40 border-navy-700 bg-gradient-to-br from-navy-800 to-navy-900 p-3 group relative"
                  style={{ borderLeftColor: '#f59e0b60' }}
                >
                  <div className="flex items-start gap-2.5">
                    <ThiingIcon src={categoryIcon(a)} alt="" className="w-8 h-8 shrink-0 mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <div className="text-[10px] uppercase tracking-wider text-amber-600/80 font-mono">{a.category}</div>
                      <div className="text-white text-sm font-semibold leading-tight">{a.achievement}</div>
                      <div className="text-xs text-slate-400 mt-0.5 leading-tight">
                        {[a.subcategory, seasonRange(a)].filter(Boolean).join(' · ')}
                        {a.detail && <span className="text-accent ml-1 font-mono">{a.detail}</span>}
                      </div>
                    </div>
                  </div>
                  {canEdit && (
                    <div className="absolute top-1.5 right-1.5 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button onClick={() => openEdit(a)} className="text-xs text-slate-400 hover:text-white px-1.5 py-0.5 rounded hover:bg-navy-700">Edit</button>
                      <button onClick={() => handleDelete(a.id)} className="text-xs text-red-400 hover:text-red-300 px-1.5 py-0.5 rounded hover:bg-navy-700">✕</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {rolesList.length > 0 && (
          <section>
            <h4 className="section-label text-xs mb-3 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-accent inline-block" />
              Roles
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              {rolesList.map((g, i) => (
                <div key={i} className="rounded-lg border border-l-2 border-navy-700 bg-navy-800/40 p-3" style={{ borderLeftColor: '#16c78440' }}>
                  <div className="flex items-center gap-2 mb-2">
                    <ThiingIcon src={CATEGORY_ICON_SRC['Office Bearer'] || thiings.goldMedal} alt="" className="w-5 h-5 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="text-white text-sm font-semibold leading-tight truncate">{g.achievement}</div>
                      {g.subcategory && <div className="text-xs text-slate-500">{g.subcategory}</div>}
                    </div>
                    <span className="text-xs text-slate-600 font-mono shrink-0">{g.instances.length}×</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {g.instances.map(inst => (
                      <span key={inst.id} className="group/chip relative inline-flex items-center gap-1 text-xs font-mono bg-navy-700/60 text-accent border border-accent/20 px-2 py-0.5 rounded-md">
                        {canEdit ? (
                          <button onClick={() => openEdit(inst)} className="hover:text-white" title="Edit">
                            {seasonRange(inst)}
                          </button>
                        ) : (
                          <span>{seasonRange(inst)}</span>
                        )}
                        {inst.detail && <span className="text-slate-400">· {inst.detail}</span>}
                        {canEdit && (
                          <button onClick={() => handleDelete(inst.id)} className="ml-0.5 text-slate-500 hover:text-red-400 opacity-0 group-hover/chip:opacity-100 transition-opacity" title="Delete">×</button>
                        )}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {awards.length > 0 && (
          <section>
            <h4 className="section-label text-xs mb-3 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-blue-400 inline-block" />
              Awards
            </h4>
            <div className="rounded-lg border border-navy-700 overflow-hidden divide-y divide-navy-700/40">
              {awards.map(a => (
                <div key={a.id} className="px-4 py-2.5 flex items-center gap-3 group hover:bg-navy-800/50 transition-colors">
                  <ThiingIcon src={categoryIcon(a)} alt="" className="w-5 h-5 shrink-0 opacity-70" />
                  <div className="flex-1 min-w-0">
                    <span className="text-white text-sm font-medium">{a.achievement}</span>
                    {a.subcategory && <span className="text-slate-500 text-xs ml-1.5">· {a.subcategory}</span>}
                    {a.detail && <span className="text-accent text-xs font-mono ml-1.5">{a.detail}</span>}
                  </div>
                  <span className="text-xs font-mono text-slate-400 shrink-0 bg-navy-700/60 px-2 py-0.5 rounded">{seasonRange(a)}</span>
                  {canEdit && (
                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                      <button onClick={() => openEdit(a)} className="text-xs text-slate-400 hover:text-white px-1.5 py-0.5 rounded hover:bg-navy-700">Edit</button>
                      <button onClick={() => handleDelete(a.id)} className="text-xs text-red-400 hover:text-red-300 px-1.5 py-0.5 rounded hover:bg-navy-700">✕</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {milestones.length > 0 && (
          <section>
            <h4 className="section-label text-xs mb-3 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-purple-400 inline-block" />
              Milestones
            </h4>
            <div className="rounded-lg border border-navy-700 overflow-hidden divide-y divide-navy-700/40">
              {milestones.map(a => (
                <div key={a.id} className="px-4 py-2.5 flex items-center gap-3 group hover:bg-navy-800/50 transition-colors">
                  <ThiingIcon src={MILESTONE_ICON_SRC[a.subcategory] || categoryIcon(a)} alt="" className="w-5 h-5 shrink-0 opacity-70" />
                  <div className="flex-1 min-w-0">
                    <span className="text-white text-sm font-medium">{a.achievement}</span>
                    {a.subcategory && <span className="text-slate-500 text-xs ml-1.5">· {a.subcategory}</span>}
                    {a.detail && <span className="text-accent text-xs font-mono ml-1.5">{a.detail}</span>}
                  </div>
                  <span className="text-xs font-mono text-slate-400 shrink-0 bg-navy-700/60 px-2 py-0.5 rounded">{seasonRange(a)}</span>
                  {canEdit && (
                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                      <button onClick={() => openEdit(a)} className="text-xs text-slate-400 hover:text-white px-1.5 py-0.5 rounded hover:bg-navy-700">Edit</button>
                      <button onClick={() => handleDelete(a.id)} className="text-xs text-red-400 hover:text-red-300 px-1.5 py-0.5 rounded hover:bg-navy-700">✕</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
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
                  <ThiingIcon src={MILESTONE_ICON_SRC[m.type] || thiings.target} alt="" className="w-5 h-5" />
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

function computeRankSets(rows, key, direction = 'desc') {
  if (!rows?.length) return { topIdx: new Set(), botIdx: new Set() }
  const valid = rows.map((r, i) => ({ i, v: r[key] })).filter(x => x.v != null && !Number.isNaN(Number(x.v)))
  if (valid.length < 2) return { topIdx: new Set(), botIdx: new Set() }
  const sorted = [...valid].sort((a, b) => direction === 'desc' ? b.v - a.v : a.v - b.v)
  const topN = Math.min(3, sorted.length - 1)
  const topIdx = new Set(sorted.slice(0, topN).map(x => x.i))
  const botIdx = new Set([sorted[sorted.length - 1]].filter(x => !topIdx.has(x.i)).map(x => x.i))
  return { topIdx, botIdx }
}

function rankCls(i, topIdx, botIdx, defaultCls = 'text-slate-300') {
  if (topIdx.has(i)) return 'text-green-400 font-bold'
  if (botIdx.has(i)) return 'text-red-400'
  return defaultCls
}

function SeasonBattingTable({ data }) {
  if (!data?.length) return <p className="text-slate-500 text-sm px-5 py-4">No batting data.</p>
  const rnRuns = computeRankSets(data, 'total_runs')
  const rnAvg  = computeRankSets(data, 'batting_average')
  const rnHS   = computeRankSets(data, 'high_score')
  const rnSR   = computeRankSets(data, 'strike_rate')
  const rnFif  = computeRankSets(data, 'fifties')
  const rnHun  = computeRankSets(data, 'hundreds')
  const rnSix  = computeRankSets(data, 'total_sixes')
  const rnFour = computeRankSets(data, 'total_fours')
  const rnDuck = computeRankSets(data, 'ducks', 'asc')
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
            <th className="table-header text-right">0s</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell text-white font-medium">{row.season_name}</td>
              <td className="table-cell stat-number text-right text-slate-400">{row.matches ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-400">{row.batting_innings ?? '—'}</td>
              <td className={clsx('table-cell stat-number text-right', rankCls(i, rnRuns.topIdx, rnRuns.botIdx, 'text-white'))}>
                {row.total_runs ?? '—'}
              </td>
              <td className={clsx('table-cell stat-number text-right', rankCls(i, rnAvg.topIdx, rnAvg.botIdx))}>
                {row.batting_average != null ? Number(row.batting_average).toFixed(1) : '—'}
              </td>
              <td className={clsx('table-cell stat-number text-right', rankCls(i, rnHS.topIdx, rnHS.botIdx))}>
                {row.high_score ?? '—'}
              </td>
              <td className={clsx('table-cell stat-number text-right', rankCls(i, rnSR.topIdx, rnSR.botIdx, 'text-slate-400'))}>
                {row.strike_rate != null ? Number(row.strike_rate).toFixed(1) : '—'}
              </td>
              <td className={clsx('table-cell stat-number text-right', rankCls(i, rnFif.topIdx, rnFif.botIdx))}>
                {row.fifties || '—'}
              </td>
              <td className={clsx('table-cell stat-number text-right', rankCls(i, rnHun.topIdx, rnHun.botIdx, row.hundreds > 0 ? 'text-amber-cricket font-bold' : 'text-slate-300'))}>
                {row.hundreds || '—'}
              </td>
              <td className={clsx('table-cell stat-number text-right', rankCls(i, rnSix.topIdx, rnSix.botIdx, 'text-slate-400'))}>
                {row.total_sixes || '—'}
              </td>
              <td className={clsx('table-cell stat-number text-right', rankCls(i, rnFour.topIdx, rnFour.botIdx, 'text-slate-400'))}>
                {row.total_fours || '—'}
              </td>
              <td className={clsx('table-cell stat-number text-right', rankCls(i, rnDuck.topIdx, rnDuck.botIdx, 'text-slate-500'))}>
                {row.ducks || '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SeasonBowlingTable({ data }) {
  const bowlingRows = data?.filter(r => (r.total_wickets ?? 0) > 0 || (r.total_overs ?? 0) > 0) ?? []
  if (!bowlingRows.length) return <p className="text-slate-500 text-sm px-5 py-4">No bowling data.</p>
  const rnW    = computeRankSets(bowlingRows, 'total_wickets')
  const rnO    = computeRankSets(bowlingRows, 'total_overs')
  const rnM    = computeRankSets(bowlingRows, 'total_maidens')
  const rnR    = computeRankSets(bowlingRows, 'bowling_runs_conceded', 'asc')
  const rnAvg  = computeRankSets(bowlingRows, 'bowling_average', 'asc')
  const rnEcon = computeRankSets(bowlingRows, 'economy', 'asc')
  const rnFW   = computeRankSets(bowlingRows, 'five_fors')
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
          {bowlingRows.map((row, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell text-white font-medium">{row.season_name}</td>
              <td className="table-cell stat-number text-right text-slate-400">{row.matches ?? '—'}</td>
              <td className={clsx('table-cell stat-number text-right', rankCls(i, rnO.topIdx, rnO.botIdx, 'text-slate-400'))}>
                {row.total_overs ?? '—'}
              </td>
              <td className={clsx('table-cell stat-number text-right', rankCls(i, rnM.topIdx, rnM.botIdx, 'text-slate-400'))}>
                {row.total_maidens ?? '—'}
              </td>
              <td className={clsx('table-cell stat-number text-right', rankCls(i, rnR.topIdx, rnR.botIdx))}>
                {row.bowling_runs_conceded ?? '—'}
              </td>
              <td className={clsx('table-cell stat-number text-right', rankCls(i, rnW.topIdx, rnW.botIdx, 'text-white font-bold'))}>
                {row.total_wickets ?? '—'}
              </td>
              <td className={clsx('table-cell stat-number text-right', rankCls(i, rnAvg.topIdx, rnAvg.botIdx))}>
                {row.bowling_average != null ? Number(row.bowling_average).toFixed(1) : '—'}
              </td>
              <td className={clsx('table-cell stat-number text-right', rankCls(i, rnEcon.topIdx, rnEcon.botIdx))}>
                {row.economy != null ? Number(row.economy).toFixed(2) : '—'}
              </td>
              <td className="table-cell stat-number text-right text-slate-300">
                {row.best_bowling_figures || (row.best_bowling_wickets > 0 ? `${row.best_bowling_wickets}w` : '—')}
              </td>
              <td className={clsx('table-cell stat-number text-right', rankCls(i, rnFW.topIdx, rnFW.botIdx, row.five_fors > 0 ? 'text-amber-cricket font-bold' : 'text-slate-400'))}>
                {row.five_fors || '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SeasonFieldingTable({ data }) {
  const fieldingRows = data?.filter(r =>
    (r.total_catches ?? 0) > 0 || (r.total_run_outs ?? 0) > 0 || (r.total_stumpings ?? 0) > 0 || (r.total_catches_wk ?? 0) > 0
  ) ?? []
  if (!fieldingRows.length) return <p className="text-slate-500 text-sm px-5 py-4">No fielding data.</p>
  const rnCt  = computeRankSets(fieldingRows, 'total_catches')
  const rnRO  = computeRankSets(fieldingRows, 'total_run_outs')
  const rnWK  = computeRankSets(fieldingRows, 'total_catches_wk')
  const rnSt  = computeRankSets(fieldingRows, 'total_stumpings')
  const hasWK = fieldingRows.some(r => (r.total_catches_wk ?? 0) > 0)
  const hasSt = fieldingRows.some(r => (r.total_stumpings ?? 0) > 0)
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-navy-700">
            <th className="table-header">Season</th>
            <th className="table-header text-right">Mat</th>
            <th className="table-header text-right">Catches</th>
            {hasWK && <th className="table-header text-right">WK Ct</th>}
            <th className="table-header text-right">Run Outs</th>
            {hasSt && <th className="table-header text-right">Stumpings</th>}
          </tr>
        </thead>
        <tbody>
          {fieldingRows.map((row, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell text-white font-medium">{row.season_name}</td>
              <td className="table-cell stat-number text-right text-slate-400">{row.matches ?? '—'}</td>
              <td className={clsx('table-cell stat-number text-right', rankCls(i, rnCt.topIdx, rnCt.botIdx, 'text-slate-300'))}>
                {row.total_catches || '—'}
              </td>
              {hasWK && (
                <td className={clsx('table-cell stat-number text-right', rankCls(i, rnWK.topIdx, rnWK.botIdx, 'text-slate-300'))}>
                  {row.total_catches_wk || '—'}
                </td>
              )}
              <td className={clsx('table-cell stat-number text-right', rankCls(i, rnRO.topIdx, rnRO.botIdx, 'text-slate-300'))}>
                {row.total_run_outs || '—'}
              </td>
              {hasSt && (
                <td className={clsx('table-cell stat-number text-right', rankCls(i, rnSt.topIdx, rnSt.botIdx, 'text-slate-300'))}>
                  {row.total_stumpings || '—'}
                </td>
              )}
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

const MILESTONE_TYPE_META = {
  runs:    { label: 'Runs Milestones',    color: 'text-accent',        border: 'border-accent/30',    bg: 'bg-accent/5' },
  wickets: { label: 'Wicket Milestones',  color: 'text-blue-400',      border: 'border-blue-400/30',  bg: 'bg-blue-400/5' },
  matches: { label: 'Match Milestones',   color: 'text-amber-cricket', border: 'border-amber-400/30', bg: 'bg-amber-400/5' },
  catches: { label: 'Fielding Milestones',color: 'text-purple-400',    border: 'border-purple-400/30',bg: 'bg-purple-400/5' },
}

function MilestoneTimeline({ data }) {
  if (!data?.length) return (
    <div className="px-6 py-12 text-center">
      <div className="text-4xl mb-3 opacity-30">🏆</div>
      <p className="text-slate-500 text-sm">No milestones recorded yet.</p>
    </div>
  )

  const grouped = data.reduce((acc, m) => {
    const key = m.milestone_type
    if (!acc[key]) acc[key] = []
    acc[key].push(m)
    return acc
  }, {})

  const TYPE_ORDER = ['runs', 'wickets', 'matches', 'catches']
  const orderedGroups = TYPE_ORDER.filter(t => grouped[t])
    .concat(Object.keys(grouped).filter(t => !TYPE_ORDER.includes(t)))
    .map(t => [t, [...grouped[t]].sort((a, b) => b.milestone_value - a.milestone_value)])

  return (
    <div className="p-5 space-y-8">
      {orderedGroups.map(([type, items]) => {
        const meta = MILESTONE_TYPE_META[type] || { label: type, color: 'text-slate-300', border: 'border-navy-600', bg: 'bg-navy-800/30' }
        return (
          <div key={type}>
            <div className="flex items-center gap-2 mb-4">
              <ThiingIcon src={MILESTONE_ICON_SRC[type] || thiings.target} alt="" className="w-5 h-5" />
              <h4 className={clsx('display-heading text-sm uppercase', meta.color)}>{meta.label}</h4>
              <span className="text-xs text-slate-600 font-mono">{items.length} achieved</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
              {items.map((m, i) => (
                <div key={i} className={clsx(
                  'rounded-xl border p-3 flex flex-col gap-1 transition-colors hover:bg-navy-700/30',
                  meta.border, meta.bg
                )}>
                  <span className={clsx('stat-number font-bold text-2xl leading-none', meta.color)}>
                    {m.milestone_value.toLocaleString()}
                  </span>
                  {m.detail && (
                    <span className="text-xs text-slate-400 leading-tight">{m.detail}</span>
                  )}
                  {m.game_date && (
                    <span className="text-xs text-slate-600">{m.game_date}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

const PIE_COLORS = ['#16c784', '#3b82f6', '#f59e0b', '#a855f7', '#ef4444', '#06b6d4', '#84cc16', '#f97316']

function DismissalDonut({ dismissals }) {
  if (!dismissals?.length) return null
  const total = dismissals.reduce((s, d) => s + Number(d.count), 0)
  const pieData = dismissals.map(d => ({ name: d.dismissal_type, value: Number(d.count) }))
  return (
    <div className="flex flex-col md:flex-row items-center gap-6">
      <div className="w-48 h-48 shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} dataKey="value" paddingAngle={2}>
              {pieData.map((_, idx) => <Cell key={idx} fill={PIE_COLORS[idx % PIE_COLORS.length]} />)}
            </Pie>
            <Tooltip
              contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 12 }}
              formatter={(v) => [`${v} (${Math.round(v/total*100)}%)`, '']}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="flex flex-col gap-1.5 flex-1 min-w-0">
        {dismissals.map((d, i) => (
          <div key={i} className="flex items-center gap-2 text-sm">
            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
            <span className="capitalize text-slate-300 flex-1 truncate">{d.dismissal_type}</span>
            <span className="stat-number text-white font-bold">{d.count}</span>
            <span className="text-slate-500 text-xs w-9 text-right">{Math.round(Number(d.count)/total*100)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function CumulativeRunsChart({ seasonStats }) {
  if (!seasonStats?.length) return null
  let cumulative = 0
  const chartData = [...seasonStats].reverse().map(s => {
    cumulative += (s.total_runs ?? 0)
    return { season: s.season_name?.replace('Summer ', '') ?? '', total: cumulative, season_runs: s.total_runs ?? 0 }
  })
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis dataKey="season" tick={{ fill: '#64748b', fontSize: 10 }} interval="preserveStartEnd" />
        <YAxis tick={{ fill: '#64748b', fontSize: 11 }} />
        <Tooltip
          contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8 }}
          labelStyle={{ color: '#94a3b8' }}
          formatter={(v, name) => [v.toLocaleString(), name === 'total' ? 'Career total' : 'Season runs']}
        />
        <Bar dataKey="season_runs" name="season_runs" fill="#16c78440" radius={[2,2,0,0]} />
        <Line type="monotone" dataKey="total" name="total" stroke="#16c784" strokeWidth={2} dot={false} />
      </BarChart>
    </ResponsiveContainer>
  )
}

function AveragesChart({ seasonStats }) {
  if (!seasonStats?.length) return null
  const chartData = [...seasonStats].reverse()
    .filter(s => s.batting_average != null || s.bowling_average != null)
    .map(s => ({
      season: s.season_name?.replace('Summer ', '') ?? '',
      bat_avg: s.batting_average != null ? Number(Number(s.batting_average).toFixed(1)) : null,
      bowl_avg: s.bowling_average != null ? Number(Number(s.bowling_average).toFixed(1)) : null,
    }))
  if (!chartData.length) return null
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis dataKey="season" tick={{ fill: '#64748b', fontSize: 10 }} interval="preserveStartEnd" />
        <YAxis tick={{ fill: '#64748b', fontSize: 11 }} />
        <Tooltip
          contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8 }}
          labelStyle={{ color: '#94a3b8' }}
          itemStyle={{ color: '#fff' }}
        />
        <Legend wrapperStyle={{ color: '#94a3b8', fontSize: 12 }} />
        <Line type="monotone" dataKey="bat_avg" name="Batting Avg" stroke="#16c784" strokeWidth={2} dot={{ r: 3 }} connectNulls />
        <Line type="monotone" dataKey="bowl_avg" name="Bowling Avg" stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} connectNulls />
      </LineChart>
    </ResponsiveContainer>
  )
}

function RunsByGradeChart({ byGrade }) {
  if (!byGrade?.length) return null
  const sorted = [...byGrade].sort((a, b) => b.runs - a.runs).slice(0, 10)
  return (
    <ResponsiveContainer width="100%" height={Math.max(180, sorted.length * 36)}>
      <BarChart data={sorted} layout="vertical" margin={{ top: 5, right: 60, left: 8, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
        <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} />
        <YAxis type="category" dataKey="grade_name" width={130} tick={{ fill: '#94a3b8', fontSize: 11 }} />
        <Tooltip
          contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8 }}
          labelStyle={{ color: '#94a3b8' }}
          formatter={(v, _, props) => [`${v} runs (${props.payload.innings} inn, avg ${props.payload.average ?? '—'})`, '']}
        />
        <Bar dataKey="runs" fill="#16c784" radius={[0,3,3,0]} label={{ position: 'right', fill: '#64748b', fontSize: 11 }} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export default function PlayerProfile() {
  const { playerId } = useParams()
  const [tab, setTab] = useState('batting')
  const [seasonId, setSeasonId] = useState(null)
  const [seasons, setSeasons] = useState([])
  const [org, setOrg] = useState(null)
  const { data, loading, error } = usePlayerStats(playerId, { seasonId })
  useClubTheme(org)

  const [activity, setActivity] = useState(null)
  const [upcomingMilestones, setUpcomingMilestones] = useState(null)
  const [milestones, setMilestones] = useState(null)
  const [seasonStats, setSeasonStats] = useState(null)
  const [achievementsLoaded, setAchievementsLoaded] = useState(false)
  const [headerAchievements, setHeaderAchievements] = useState([])
  const [partnerships, setPartnerships] = useState(null)
  const [dismissals, setDismissals] = useState(null)
  const [byGrade, setByGrade] = useState(null)
  const [byPosition, setByPosition] = useState(null)
  const [syncRequested, setSyncRequested] = useState(false)
  const [syncRequestLoading, setSyncRequestLoading] = useState(false)

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
    api.getOrg(data.player.organisation_id).then(setOrg).catch(() => {})
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
    if (t === 'analysis' && partnerships === null) {
      api.getPlayerPartnerships(playerId).then(setPartnerships).catch(() => setPartnerships([]))
      api.getPlayerDismissals(playerId).then(setDismissals).catch(() => setDismissals([]))
      api.getPlayerByGrade(playerId).then(setByGrade).catch(() => setByGrade([]))
      api.getPlayerByPosition(playerId).then(setByPosition).catch(() => setByPosition([]))
    }
  }, [playerId, milestones, partnerships])

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
    return {
      total_wickets: s.total_wickets,
      economy: s.economy,
      best_bowling_figures: s.best_bowling_figures,
      best_figures_wickets: s.best_bowling_wickets,
      bowling_average: s.bowling_average,
      total_overs: s.total_overs,
      total_maidens: s.total_maidens,
      total_runs: s.bowling_runs_conceded,
      five_fors: s.five_fors,
    }
  }, [seasonId, seasonStats, cbw])

  const displayFielding = useMemo(() => {
    if (!seasonId || !seasonStats?.length) return cf
    const s = seasonStats.find(r => r.season_id === seasonId)
    if (!s) return cf
    return {
      total_catches: s.total_catches,
      total_catches_wk: s.total_catches_wk,
      total_run_outs: s.total_run_outs,
      total_stumpings: s.total_stumpings,
    }
  }, [seasonId, seasonStats, cf])

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
                {rankedHeaderAchievements(headerAchievements).slice(0, 6).map(a => (
                  <span key={a.id} className="badge bg-navy-700 text-slate-300 border border-navy-600">
                    {formatAchievementBadge(a, seasons)}
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
          </div>
        </div>
      </div>

      {/* Upcoming milestones progress bars */}
      {upcomingMilestones !== null && upcomingMilestones.length > 0 && (
        <UpcomingMilestonesSection data={upcomingMilestones} />
      )}

      {/* Stat cards — season-aware, stacked rows */}
      <div className="space-y-3 mb-10">
        {/* Matches */}
        <div className="flex items-stretch gap-3">
          <div className="bg-navy-800 border border-navy-700 rounded-xl px-6 py-3 text-center min-w-[100px]">
            <div className="section-label mb-1">Matches</div>
            <div className="stat-number font-bold text-2xl text-white leading-none">
              {seasonId ? (displayBatting?.matches ?? '—') : (cb?.games ?? '—')}
            </div>
          </div>
        </div>

        {/* Batting */}
        <div>
          <div className="section-label text-slate-500 mb-1.5 ml-1">Batting</div>
          <div className="grid grid-cols-4 sm:grid-cols-4 md:grid-cols-7 gap-2">
            <StatCard label="Innings"   value={displayBatting?.innings ?? '—'} />
            <StatCard label="Runs"      value={displayBatting?.total_runs ?? '—'} accent />
            <StatCard label="Average"   value={displayBatting?.average ?? '—'} />
            <StatCard label="High Score" value={displayBatting?.high_score != null ? displayBatting.high_score : '—'} />
            <StatCard label="Centuries" value={displayBatting?.hundreds ?? '—'} />
            <StatCard label="Fifties"   value={displayBatting?.fifties ?? '—'} />
            <StatCard label="Ducks"     value={seasonId ? (seasonStats?.find(s => s.season_id === seasonId)?.ducks ?? '—') : (cb?.ducks ?? '—')} />
          </div>
        </div>

        {/* Bowling */}
        <div>
          <div className="section-label text-slate-500 mb-1.5 ml-1">Bowling</div>
          <div className="grid grid-cols-4 sm:grid-cols-4 md:grid-cols-7 gap-2">
            <StatCard label="Overs"      value={displayBowling?.total_overs ?? '—'} />
            <StatCard label="Maidens"    value={displayBowling?.total_maidens ?? '—'} />
            <StatCard label="Wickets"    value={displayBowling?.total_wickets ?? '—'} accent />
            <StatCard label="Runs"       value={displayBowling?.total_runs ?? '—'} />
            <StatCard label="Average"    value={displayBowling?.bowling_average != null ? Number(displayBowling.bowling_average).toFixed(1) : '—'} />
            <StatCard label="Economy"    value={displayBowling?.economy ?? '—'} />
            <StatCard label="Best"       value={displayBowling?.best_bowling_figures ?? cbw?.best_bowling_figures ?? '—'} />
          </div>
        </div>

        {/* Fielding */}
        {(displayFielding?.total_catches > 0 || displayFielding?.total_run_outs > 0 || displayFielding?.total_stumpings > 0) && (
          <div>
            <div className="section-label text-slate-500 mb-1.5 ml-1">Fielding</div>
            <div className="flex flex-wrap gap-2">
              <StatCard label="Catches"  value={displayFielding?.total_catches ?? '—'} />
              <StatCard label="Run Outs" value={displayFielding?.total_run_outs ?? '—'} />
              {(displayFielding?.total_catches_wk ?? 0) > 0 && <StatCard label="WK Catches" value={displayFielding.total_catches_wk} />}
              {(displayFielding?.total_stumpings ?? 0) > 0 && <StatCard label="Stumpings"  value={displayFielding.total_stumpings} />}
            </div>
          </div>
        )}
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

        {tab === 'fielding' && (
          <>
            <div className="px-5 py-4 border-b border-navy-700 flex items-center justify-between">
              <h3 className="display-heading text-lg text-white">FIELDING BY SEASON</h3>
            </div>
            {seasonStats === null
              ? <div className="p-5"><LoadingSpinner size="sm" /></div>
              : <SeasonFieldingTable data={seasonStats} />
            }
          </>
        )}

        {tab === 'analysis' && (
          <div className="p-5 space-y-10">

            {/* Season-by-season overview */}
            <div>
              <h3 className="display-heading text-lg text-white mb-4">RUNS &amp; WICKETS BY SEASON</h3>
              {seasonStats === null
                ? <LoadingSpinner size="sm" />
                : <SeasonChart data={seasonStats} />
              }
            </div>

            {/* Cumulative career runs */}
            {seasonStats !== null && seasonStats.some(s => (s.total_runs ?? 0) > 0) && (
              <div>
                <h3 className="display-heading text-lg text-white mb-1">CAREER RUNS ACCUMULATION</h3>
                <p className="text-slate-500 text-xs mb-4">Running total of career batting runs, season by season.</p>
                <CumulativeRunsChart seasonStats={seasonStats} />
              </div>
            )}

            {/* Season averages trend */}
            {seasonStats !== null && (
              <div>
                <h3 className="display-heading text-lg text-white mb-1">AVERAGES OVER TIME</h3>
                <p className="text-slate-500 text-xs mb-4">Batting and bowling averages season by season.</p>
                <AveragesChart seasonStats={seasonStats} />
              </div>
            )}

            {/* Dismissal donut */}
            {dismissals !== null && dismissals.length > 0 && (
              <div>
                <h3 className="display-heading text-lg text-white mb-4">HOW I GET OUT</h3>
                <div className="card p-5">
                  <DismissalDonut dismissals={dismissals} />
                </div>
                {cb?.innings > 0 && (() => {
                  const synced = dismissals.reduce((s, d) => s + Number(d.count), 0)
                  const total = Number(cb.innings) || 0
                  if (total <= 0 || synced / total >= 0.5) return null
                  return (
                    <div className="mt-3 bg-navy-800/50 border border-navy-700 rounded p-4 flex flex-wrap items-center justify-between gap-3">
                      <p className="text-slate-400 text-sm">
                        Only <span className="text-white font-mono">{synced}</span> of <span className="text-white font-mono">{total}</span> innings have game-level data.
                      </p>
                      {syncRequested
                        ? <span className="text-accent text-sm font-medium">Sync requested ✓</span>
                        : <button onClick={async () => { setSyncRequestLoading(true); try { await api.requestPlayerSync(playerId) } catch {} setSyncRequested(true); setSyncRequestLoading(false) }} disabled={syncRequestLoading} className="btn-primary text-sm disabled:opacity-50 shrink-0">{syncRequestLoading ? 'Submitting…' : 'Request Full Sync'}</button>
                      }
                    </div>
                  )
                })()}
              </div>
            )}

            {/* Runs by grade */}
            {byGrade !== null && byGrade.length > 1 && (
              <div>
                <h3 className="display-heading text-lg text-white mb-1">RUNS BY GRADE</h3>
                <p className="text-slate-500 text-xs mb-4">Career batting runs broken down by grade.</p>
                <div className="card p-5">
                  <RunsByGradeChart byGrade={byGrade} />
                </div>
              </div>
            )}

            {/* No game-level data prompt */}
            {dismissals !== null && byGrade !== null && byPosition !== null &&
              dismissals.length === 0 && byGrade.length === 0 && byPosition.length === 0 && (
              <div className="card p-5">
                <p className="text-slate-400 text-sm mb-3">
                  Game-level data (dismissals, position, grade splits) hasn't been synced for this player yet.
                </p>
                {player && !player.playhq_id && (
                  <p className="text-amber-500 text-xs mb-3">
                    PlayHQ ID not yet linked — this player needs to appear in a recently synced game first.
                  </p>
                )}
                {syncRequested ? (
                  <p className="text-accent text-sm font-medium">Sync request submitted — an admin will review it shortly.</p>
                ) : (
                  <button onClick={async () => { setSyncRequestLoading(true); try { await api.requestPlayerSync(playerId); setSyncRequested(true) } catch { setSyncRequested(true) } finally { setSyncRequestLoading(false) } }} disabled={syncRequestLoading} className="btn-primary text-sm disabled:opacity-50">
                    {syncRequestLoading ? 'Submitting…' : 'Request Full Stats Sync'}
                  </button>
                )}
              </div>
            )}

            {/* Partnerships */}
            {partnerships === null ? <LoadingSpinner size="sm" /> : partnerships.length > 0 && <PartnershipsTable partnerships={partnerships} />}

            {/* By grade detail table */}
            {byGrade !== null && byGrade.length > 1 && <ByGradeTable rows={byGrade} />}

            {/* By batting position */}
            {byPosition !== null && byPosition.length > 0 && <ByPositionTable rows={byPosition} />}
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
