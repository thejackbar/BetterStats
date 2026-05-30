import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { nameMatchesSearch } from '../../../lib/nameFormat'
import { PbSpinner } from '../../../lib/presskit'
import { AVAILABILITY, AVAIL_STATUSES } from '../../../lib/availability'

// Click-to-cycle order; per-status glyph/colour comes from the shared module.
const CYCLE = ['NO_RESPONSE', 'AVAILABLE', 'UNAVAILABLE', 'MAYBE']
const META = Object.fromEntries(
  AVAIL_STATUSES.map((s) => [s, { g: AVAILABILITY[s].glyph, cls: AVAILABILITY[s].chip }]),
)

const SKILL_CODES = ['BAT', 'BWL', 'ALL', 'WKT']
const STATUS_LABEL = Object.fromEntries(AVAIL_STATUSES.map((s) => [s, AVAILABILITY[s].label.toLowerCase()]))
// Roster visibility: default to current squad only (hides dormant + inactive).
const ROSTER_OPTS = [
  { key: 'current', label: 'Current squad' },
  { key: 'with_dormant', label: '+ Dormant' },
  { key: 'all', label: 'All (incl. inactive)' },
]

function fmtDay(d) {
  try { return new Date(d + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) }
  catch { return d }
}

function fmtYear(d) {
  if (!d) return '—'
  try { return new Date(d + 'T00:00:00').getFullYear() } catch { return '—' }
}

function fmtMonths(m) {
  if (m % 12 === 0) { const y = m / 12; return `${y} year${y === 1 ? '' : 's'}` }
  return `${m} months`
}

export default function AdminAvailability() {
  const { hasCapability } = useAuth()
  const toast = useToast()
  const canEdit = hasCapability(CAP.MANAGE_SELECTIONS)
  const [data, setData] = useState(null)
  const [avail, setAvail] = useState({}) // {playerId: {date: {status}}}

  // Filters
  const [search, setSearch] = useState('')
  const [roster, setRoster] = useState('current')
  const [squad, setSquad] = useState('')        // team name, '' = any
  const [role, setRole] = useState('')          // player_role, '' = any
  const [skill, setSkill] = useState('')        // skill code, '' = any
  const [respFilter, setRespFilter] = useState('') // availability status across shown dates, '' = any

  // Bulk update: select players, then mark them all in one action.
  const [selected, setSelected] = useState(() => new Set())
  const [bulkStatus, setBulkStatus] = useState('AVAILABLE')
  const [bulkDate, setBulkDate] = useState('ALL')   // 'ALL' = every shown date
  const [applying, setApplying] = useState(false)

  const load = useCallback(() => {
    setData(null)
    api.bsAvailabilityMatrix()
      .then(d => { setData(d); setAvail(d.availability || {}) })
      .catch(e => { toast.error(e.message); setData({ dates: [], players: [], availability: {} }) })
  }, [toast])

  useEffect(() => { load() }, [load])

  // Distinct roles present in the roster, for the role dropdown.
  const roleOptions = useMemo(() => {
    const s = new Set()
    ;(data?.players || []).forEach(p => { if (p.player_role) s.add(p.player_role) })
    return [...s].sort()
  }, [data])

  // A player's "effective" response for the response filter: AVAILABLE/etc if
  // they hold that status on ANY shown date; NO_RESPONSE if untouched.
  const matchesResponse = useCallback((p) => {
    if (!respFilter) return true
    const dates = data?.dates || []
    const byDate = avail[p.id] || {}
    if (respFilter === 'NO_RESPONSE') {
      return dates.every(d => (byDate[d.date]?.status || 'NO_RESPONSE') === 'NO_RESPONSE')
    }
    return dates.some(d => byDate[d.date]?.status === respFilter)
  }, [respFilter, data, avail])

  const filteredPlayers = useMemo(() => {
    return (data?.players || []).filter(p => {
      // Roster visibility
      if (roster === 'current' && !p.is_current) return false
      if (roster === 'with_dormant' && p.is_inactive) return false
      // 'all' shows everyone
      if (search.trim() && !nameMatchesSearch(p.display_name, search)) return false
      if (squad && !(p.squads || []).includes(squad)) return false
      if (role && p.player_role !== role) return false
      if (skill && !(p.skill_positions || []).includes(skill)) return false
      if (!matchesResponse(p)) return false
      return true
    })
  }, [data, roster, search, squad, role, skill, matchesResponse])

  const resetFilters = () => {
    setSearch(''); setRoster('current'); setSquad(''); setRole(''); setSkill(''); setRespFilter('')
  }
  const filtersActive = search || squad || role || skill || respFilter || roster !== 'current'

  const cycle = async (pid, date, cur) => {
    if (!canEdit) return
    const next = CYCLE[(CYCLE.indexOf(cur) + 1) % CYCLE.length]
    setAvail(a => ({ ...a, [pid]: { ...(a[pid] || {}), [date]: { status: next } } }))
    try {
      await api.bsSetAvailability({ player_id: pid, date, status: next })
    } catch (e) {
      toast.error('Save failed: ' + e.message)
      setAvail(a => ({ ...a, [pid]: { ...(a[pid] || {}), [date]: { status: cur } } }))
    }
  }

  const toggleSelect = (pid) => setSelected(s => {
    const n = new Set(s); n.has(pid) ? n.delete(pid) : n.add(pid); return n
  })
  const allFilteredSelected = filteredPlayers.length > 0 && filteredPlayers.every(p => selected.has(p.id))
  const toggleSelectAll = () => setSelected(s => {
    const n = new Set(s)
    if (filteredPlayers.every(p => n.has(p.id))) filteredPlayers.forEach(p => n.delete(p.id))
    else filteredPlayers.forEach(p => n.add(p.id))
    return n
  })

  const applyBulk = async () => {
    if (!canEdit || selected.size === 0) return
    const targetDates = bulkDate === 'ALL' ? (data.dates || []).map(d => d.date) : [bulkDate]
    const items = []
    for (const pid of selected) for (const date of targetDates) items.push({ player_id: pid, date, status: bulkStatus })
    if (!items.length) return
    setApplying(true)
    const prev = avail
    setAvail(a => {
      const next = { ...a }
      for (const pid of selected) {
        next[pid] = { ...(next[pid] || {}) }
        for (const date of targetDates) next[pid][date] = { status: bulkStatus }
      }
      return next
    })
    try {
      await api.bsBulkAvailability(items)
      toast.success(`Marked ${selected.size} player${selected.size === 1 ? '' : 's'} ${STATUS_LABEL[bulkStatus]}${bulkDate === 'ALL' ? ' (all dates)' : ' for ' + fmtDay(bulkDate)}`)
      setSelected(new Set())
    } catch (e) {
      setAvail(prev)
      toast.error('Bulk update failed: ' + e.message)
    } finally {
      setApplying(false)
    }
  }

  if (data === null) return <BetterSelectLayout title="Availability"><PbSpinner message="Loading availability…" /></BetterSelectLayout>

  if (!data.dates.length) {
    return (
      <BetterSelectLayout title="Availability">
        <div className="pb-card px-5 py-10 text-center text-pb-faint text-sm">
          No upcoming fixtures to collect availability for.{' '}
          <Link to="/admin/betterselect/fixtures" className="text-pb-accent underline">Add or sync fixtures</Link> first.
        </div>
      </BetterSelectLayout>
    )
  }

  return (
    <BetterSelectLayout title="Availability">
      <p className="text-pb-faint text-sm mb-3 max-w-2xl">
        {canEdit ? 'Click a cell to cycle: ' : 'Read-only — '}
        <span className="text-pb-accent">✓ available</span> ·{' '}
        <span className="text-pb-red">✕ unavailable</span> ·{' '}
        <span className="text-amber-300">? maybe</span> ·{' '}
        <span className="text-pb-faintest">– no response</span>.
        One answer covers every fixture that day; two-day games show both weekends.
      </p>

      {/* Filter bar */}
      <div className="pb-card p-3 mb-3 flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[180px]">
          <label className="font-mono text-[10px] text-pb-faintest block mb-1">Search</label>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Player name…"
            className="w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
          />
        </div>
        <FilterSelect label="Roster" value={roster} onChange={setRoster}
          options={ROSTER_OPTS.map(o => [o.key, o.label])} includeAny={false} />
        {(data.all_squads || []).length > 0 &&
          <FilterSelect label="Squad" value={squad} onChange={setSquad}
            options={(data.all_squads || []).map(s => [s, s])} anyLabel="Any squad" />}
        {roleOptions.length > 0 &&
          <FilterSelect label="Role" value={role} onChange={setRole}
            options={roleOptions.map(r => [r, r])} anyLabel="Any role" />}
        <FilterSelect label="Skill" value={skill} onChange={setSkill}
          options={SKILL_CODES.map(c => [c, c])} anyLabel="Any skill" />
        <FilterSelect label="Response" value={respFilter} onChange={setRespFilter}
          options={[['AVAILABLE', '✓ Available'], ['UNAVAILABLE', '✕ Unavailable'], ['MAYBE', '? Maybe'], ['NO_RESPONSE', '– No response']]}
          anyLabel="Any response" />
        {filtersActive &&
          <button onClick={resetFilters}
            className="text-xs text-pb-faint hover:text-pb-text underline px-1 py-1.5">Clear</button>}
        <div className="ml-auto font-mono text-[10px] text-pb-faintest self-center text-right">
          {filteredPlayers.length} / {data.players.length} players
          {data.dormancy_months != null && (
            <div className="text-pb-faintest/70">dormant after {fmtMonths(data.dormancy_months)}</div>
          )}
        </div>
      </div>

      {/* Bulk action bar — appears once players are ticked */}
      {canEdit && selected.size > 0 && (
        <div className="pb-card p-3 mb-3 flex flex-wrap items-center gap-3 border" style={{ borderColor: 'var(--pb-accent)' }}>
          <span className="font-mono text-[11px] text-pb-accent">{selected.size} selected</span>
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-[10px] text-pb-faintest">mark as</span>
            <select value={bulkStatus} onChange={e => setBulkStatus(e.target.value)}
              className="bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent">
              <option value="AVAILABLE">✓ Available</option>
              <option value="UNAVAILABLE">✕ Unavailable</option>
              <option value="MAYBE">? Maybe</option>
              <option value="NO_RESPONSE">– No response</option>
            </select>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-[10px] text-pb-faintest">for</span>
            <select value={bulkDate} onChange={e => setBulkDate(e.target.value)}
              className="bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent">
              <option value="ALL">All shown dates</option>
              {data.dates.map(d => <option key={d.date} value={d.date}>{fmtDay(d.date)}</option>)}
            </select>
          </div>
          <button onClick={applyBulk} disabled={applying}
            className="px-4 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50"
            style={{ background: 'var(--pb-accent)' }}>
            {applying ? 'Applying…' : 'Apply'}
          </button>
          <button onClick={() => setSelected(new Set())}
            className="font-mono text-[10px] text-pb-faint hover:text-pb-text underline px-1">Clear</button>
        </div>
      )}

      <div className="pb-card overflow-auto">
        <table className="border-collapse text-sm w-full">
          <thead>
            <tr>
              <th className="sticky left-0 z-20 bg-pb-surface2 text-left px-3 py-2 font-mono text-[10px] uppercase tracking-wide2 text-pb-faint min-w-[160px]">
                {canEdit && (
                  <input type="checkbox" checked={allFilteredSelected} onChange={toggleSelectAll}
                    className="accent-pb-accent mr-2 align-middle" title="Select all shown" />
                )}
                Player
              </th>
              {data.dates.map(d => (
                <th key={d.date} className="px-2 py-2 border-l pb-hairline bg-pb-surface2 align-top min-w-[112px]">
                  <div className="font-semibold text-pb-text text-xs">{fmtDay(d.date)}</div>
                  <div className="mt-1 space-y-0.5">
                    {d.fixtures.map((f, fi) => (
                      <div key={fi} className="text-[10px] text-pb-faint truncate max-w-[104px]" title={f.opponent_name || f.label || ''}>
                        {f.two_day && <span className="text-amber-300">{f.role === 'day1' ? 'D1 ' : 'D2 '}</span>}
                        {f.home_away === 'AWAY' ? '@' : f.home_away === 'BYE' ? '' : 'v'} {f.opponent_name || f.label || 'TBC'}
                      </div>
                    ))}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filteredPlayers.length === 0 && (
              <tr>
                <td colSpan={data.dates.length + 1} className="px-3 py-8 text-center text-pb-faint text-sm border-t pb-hairline">
                  No players match these filters.{' '}
                  {filtersActive && <button onClick={resetFilters} className="text-pb-accent underline">Clear filters</button>}
                </td>
              </tr>
            )}
            {filteredPlayers.map(p => (
              <tr key={p.id}>
                <td className={`sticky left-0 z-10 px-3 py-1.5 whitespace-nowrap border-t pb-hairline ${selected.has(p.id) ? 'bg-pb-accent/10' : 'bg-pb-surface'}`}>
                  {canEdit && (
                    <input type="checkbox" checked={selected.has(p.id)} onChange={() => toggleSelect(p.id)}
                      className="accent-pb-accent mr-2 align-middle" />
                  )}
                  <span className="text-sm">{p.display_name}</span>
                  {p.player_role && <span className="ml-2 font-mono text-[9px] text-pb-faintest uppercase">{p.player_role}</span>}
                  {p.is_inactive && <span className="ml-2 font-mono text-[9px] text-pb-red/80 uppercase" title="Marked inactive">inactive</span>}
                  {p.is_dormant && <span className="ml-2 font-mono text-[9px] text-amber-300/80 uppercase" title={`No appearances since ${fmtYear(p.last_played)}`}>dormant · {fmtYear(p.last_played)}</span>}
                </td>
                {data.dates.map(d => {
                  const st = avail[p.id]?.[d.date]?.status || 'NO_RESPONSE'
                  const m = META[st]
                  return (
                    <td key={d.date} className="px-1.5 py-1.5 border-l border-t pb-hairline text-center">
                      <button
                        onClick={() => cycle(p.id, d.date, st)}
                        disabled={!canEdit}
                        className={`w-9 h-7 rounded border text-sm transition-transform active:scale-90 ${m.cls} ${canEdit ? 'cursor-pointer' : 'cursor-default'}`}
                        title={st}
                      >{m.g}</button>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </BetterSelectLayout>
  )
}

// Compact labelled <select> for the filter bar. `options` is [value, label][].
// When includeAny is true (default), a blank "any" option is prepended.
function FilterSelect({ label, value, onChange, options, anyLabel = 'Any', includeAny = true }) {
  return (
    <div>
      <label className="font-mono text-[10px] text-pb-faintest block mb-1">{label}</label>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        className="bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
      >
        {includeAny && <option value="">{anyLabel}</option>}
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </div>
  )
}
