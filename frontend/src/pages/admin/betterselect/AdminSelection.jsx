import { useState, useEffect, useCallback, useMemo } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { nameMatchesSearch } from '../../../lib/nameFormat'
import { PbSpinner, Btn } from '../../../lib/presskit'

const AVAIL_META = {
  AVAILABLE:   { dot: 'bg-pb-accent',   cls: 'text-pb-accent',   label: 'Available' },
  UNAVAILABLE: { dot: 'bg-pb-red',      cls: 'text-pb-red',      label: 'Unavailable' },
  MAYBE:       { dot: 'bg-amber-400',   cls: 'text-amber-300',   label: 'Maybe' },
  NO_RESPONSE: { dot: 'bg-pb-faintest', cls: 'text-pb-faintest', label: 'No response' },
}
const AVAIL_RANK = { AVAILABLE: 0, MAYBE: 1, NO_RESPONSE: 2, UNAVAILABLE: 3 }

// Specialist-role filter: maps our skill codes to the labels clubs expect.
const SKILL_LABELS = { BAT: 'Batsman', BWL: 'Bowler', ALL: 'All Rounder', WKT: 'Wicketkeeper' }

// Side-size presets. size = batting slots; the label mirrors familiar formats.
const FORMATS = [
  { key: 11, label: '11 a side' },
  { key: 12, label: '12 (incl. 12th man)' },
  { key: 13, label: '13 a side' },
  { key: 0,  label: 'No limit' },
]

function fmtHeader(fx) {
  if (!fx) return { title: 'Selection', sub: '' }
  const us = fx.home_away === 'AWAY' ? (fx.away_team || 'Us') : (fx.home_team || 'Us')
  const opp = fx.opponent_name || fx.label || 'TBC'
  const title = fx.home_away === 'BYE' ? 'BYE' : `${us} vs ${opp}`
  const bits = []
  if (fx.round) bits.push(`Round ${fx.round}`)
  if (fx.played_on) {
    try { bits.push(new Date(fx.played_on + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })) }
    catch { bits.push(fx.played_on) }
  }
  if (fx.start_time) bits.push(fx.start_time)
  if (fx.venue) bits.push(`${fx.venue}${fx.home_away === 'AWAY' ? ' (A)' : fx.home_away === 'HOME' ? ' (H)' : ''}`)
  return { title, sub: bits.join(', ') }
}

function Avatar({ p }) {
  if (p.photo_url) {
    return <img src={p.photo_url} alt="" className="w-7 h-7 rounded-full object-cover bg-pb-surface2" />
  }
  const initials = (p.display_name || '?').split(/[ ,]+/).filter(Boolean).slice(0, 2).map(s => s[0]).join('').toUpperCase()
  return <span className="w-7 h-7 rounded-full bg-pb-surface2 text-pb-faint text-[10px] font-mono flex items-center justify-center">{initials}</span>
}

export default function AdminSelection() {
  const { fixtureId } = useParams()
  const navigate = useNavigate()
  const { hasCapability } = useAuth()
  const toast = useToast()
  const canEdit = hasCapability(CAP.MANAGE_SELECTIONS)

  const [data, setData] = useState(null)
  // picked: ordered [{ player_id, is_captain, is_wicket_keeper }]
  const [picked, setPicked] = useState([])
  const [search, setSearch] = useState('')
  const [hideUnavailable, setHideUnavailable] = useState(true)
  const [format, setFormat] = useState(12)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  // Filters (multi-select sets). Empty set = no constraint for that facet.
  const [fSquads, setFSquads] = useState(() => new Set())
  const [fRoles, setFRoles] = useState(() => new Set())
  const [fAvail, setFAvail] = useState(() => new Set())
  const [showFilters, setShowFilters] = useState(false)

  const load = useCallback(() => {
    setData(null)
    api.bsGetSelection(fixtureId)
      .then(d => {
        setData(d)
        setPicked((d.lineup || []).map(l => ({
          player_id: l.player_id, is_captain: l.is_captain, is_wicket_keeper: l.is_wicket_keeper,
        })))
        setDirty(false)
      })
      .catch(e => { toast.error(e.message); setData({ pool: [], lineup: [], fixture: null }) })
  }, [fixtureId, toast])

  useEffect(() => { load() }, [load])

  const poolById = useMemo(() => {
    const m = {}
    ;(data?.pool || []).forEach(p => { m[p.id] = p })
    return m
  }, [data])

  const pickedIds = useMemo(() => new Set(picked.map(p => p.player_id)), [picked])

  // Distinct squads across the whole pool, for the squad filter list.
  const squadOptions = useMemo(() => {
    const s = new Set()
    ;(data?.pool || []).forEach(p => (p.squads || []).forEach(sq => s.add(sq)))
    return [...s].sort()
  }, [data])

  const available = useMemo(() => {
    let list = (data?.pool || []).filter(p => !pickedIds.has(p.id))
    if (hideUnavailable) list = list.filter(p => p.availability !== 'UNAVAILABLE')
    if (search.trim()) list = list.filter(p => nameMatchesSearch(p.display_name, search))
    if (fSquads.size) list = list.filter(p => (p.squads || []).some(sq => fSquads.has(sq)))
    if (fRoles.size) list = list.filter(p => (p.skill_positions || []).some(c => fRoles.has(c)))
    if (fAvail.size) list = list.filter(p => fAvail.has(p.availability))
    return list.sort((a, b) => {
      const ra = AVAIL_RANK[a.availability] ?? 9, rb = AVAIL_RANK[b.availability] ?? 9
      if (ra !== rb) return ra - rb
      return a.display_name.localeCompare(b.display_name)
    })
  }, [data, pickedIds, hideUnavailable, search, fSquads, fRoles, fAvail])

  const filterCount = fSquads.size + fRoles.size + fAvail.size
  const toggleIn = (setter) => (val) => setter(prev => {
    const next = new Set(prev)
    next.has(val) ? next.delete(val) : next.add(val)
    return next
  })
  const clearFilters = () => { setFSquads(new Set()); setFRoles(new Set()); setFAvail(new Set()) }

  const add = (p) => {
    if (!canEdit) return
    if (p.clash?.length > 0) {
      // Clash policy = block entirely: can't pick someone already in another XI today.
      toast.error(`${p.display_name} is already selected for ${p.clash.join(', ')} on this date`)
      return
    }
    setPicked(prev => [...prev, { player_id: p.id, is_captain: false, is_wicket_keeper: false }])
    setDirty(true)
  }
  const remove = (pid) => { setPicked(prev => prev.filter(p => p.player_id !== pid)); setDirty(true) }
  const move = (idx, dir) => {
    setPicked(prev => {
      const next = [...prev]; const j = idx + dir
      if (j < 0 || j >= next.length) return prev
      ;[next[idx], next[j]] = [next[j], next[idx]]
      return next
    })
    setDirty(true)
  }
  const toggleFlag = (pid, flag) => {
    setPicked(prev => prev.map(p => {
      if (p.player_id === pid) return { ...p, [flag]: !p[flag] }
      return { ...p, [flag]: false } // C and WK are each exclusive
    }))
    setDirty(true)
  }

  const save = async () => {
    setSaving(true)
    try {
      const players = picked.map((p, i) => ({
        player_id: p.player_id, batting_order: i + 1,
        is_captain: p.is_captain, is_wicket_keeper: p.is_wicket_keeper,
      }))
      const r = await api.bsSetSelection(fixtureId, players)
      toast.success(`Saved ${r.count} player${r.count === 1 ? '' : 's'}`)
      setDirty(false)
      load() // refresh clash flags for other fixtures
    } catch (e) {
      // 409 = clash block from the backend (defensive: UI already prevents adds)
      toast.error(e.message.includes('Already selected') ? e.message : 'Save failed: ' + e.message)
    } finally { setSaving(false) }
  }

  const shareTeamSheet = () => {
    const fx = data?.fixture
    navigate('/admin/social-post', {
      state: {
        teamSheet: {
          players: picked.map(p => {
            const pool = poolById[p.player_id]
            return {
              player_id: p.player_id,
              role: (pool?.skill_positions?.[0]) || pool?.player_role || 'BAT',
              is_captain: p.is_captain,
              is_wicket_keeper: p.is_wicket_keeper,
            }
          }),
          match: { round: fx?.round || '', venue: fx?.venue || '', date: fx?.played_on || '', time: fx?.start_time || '' },
          opponent: { name: fx?.opponent_name || '' },
        },
      },
    })
  }

  if (data === null) return <BetterSelectLayout title="Selection"><PbSpinner message="Loading selection…" /></BetterSelectLayout>

  const fx = data.fixture
  const { title, sub } = fmtHeader(fx)
  const target = format || 0
  const sizeWarn = target > 0 && picked.length !== target
  const availCount = available.length

  const actions = canEdit && (
    <div className="flex gap-2">
      <Btn onClick={shareTeamSheet} disabled={picked.length === 0}>↗ Share team sheet</Btn>
      <Btn primary onClick={save} disabled={saving || !dirty}>
        {saving ? 'Saving…' : dirty ? `Save XI (${picked.length})` : 'Saved'}
      </Btn>
    </div>
  )

  return (
    <BetterSelectLayout title="Selection" actions={actions}>
      {/* Fixture header */}
      <div className="rounded-lg px-5 py-3 mb-3" style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>
        <Link to="/admin/betterselect/fixtures" className="text-[11px] opacity-80 hover:opacity-100">← Fixtures</Link>
        <h2 className="font-display font-bold text-xl leading-tight">{title}</h2>
        {sub && <div className="text-sm opacity-90">{sub}</div>}
      </div>

      {/* Controls */}
      <div className="pb-card p-3 mb-3 flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[200px]">
          <label className="font-mono text-[10px] text-pb-faintest block mb-1">Search player</label>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search the available pool…"
            className="w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent" />
        </div>
        <div>
          <label className="font-mono text-[10px] text-pb-faintest block mb-1">Format</label>
          <select value={format} onChange={e => setFormat(Number(e.target.value))}
            className="bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent">
            {FORMATS.map(f => <option key={f.key} value={f.key}>{f.label}</option>)}
          </select>
        </div>
        <label className="flex items-center gap-1.5 text-[11px] text-pb-faint cursor-pointer pb-1.5">
          <input type="checkbox" checked={hideUnavailable} onChange={e => setHideUnavailable(e.target.checked)} className="accent-pb-accent" />
          Hide unavailable
        </label>
        <Btn sm primary={showFilters || filterCount > 0} onClick={() => setShowFilters(v => !v)}>
          Filter{filterCount > 0 ? ` (${filterCount})` : ''} {showFilters ? '▲' : '▼'}
        </Btn>
        <div className="ml-auto font-mono text-[10px] self-center text-right">
          <div className={sizeWarn ? 'text-amber-300' : 'text-pb-faint'}>
            {picked.length}{target > 0 ? ` / ${target}` : ''} selected
          </div>
          {data.dormancy_months != null && <div className="text-pb-faintest/70">dormant after {data.dormancy_months}mo</div>}
        </div>
      </div>

      {/* Filter panel */}
      {showFilters && (
        <div className="pb-card p-4 mb-3">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-mono text-[11px] uppercase tracking-wide2 text-pb-faint">Filters</h3>
            {filterCount > 0 && <button onClick={clearFilters} className="text-xs text-pb-accent hover:underline">Clear settings</button>}
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
            <FilterGroup title="Squads">
              {squadOptions.length === 0 && <p className="text-pb-faintest text-xs">No squads found.</p>}
              {squadOptions.map(sq => (
                <FilterCheck key={sq} label={sq} checked={fSquads.has(sq)} onChange={() => toggleIn(setFSquads)(sq)} />
              ))}
            </FilterGroup>
            <FilterGroup title="Specialist roles">
              {Object.entries(SKILL_LABELS).map(([code, label]) => (
                <FilterCheck key={code} label={label} checked={fRoles.has(code)} onChange={() => toggleIn(setFRoles)(code)} />
              ))}
            </FilterGroup>
            <FilterGroup title="Availability">
              {['AVAILABLE', 'MAYBE', 'NO_RESPONSE', 'UNAVAILABLE'].map(s => (
                <FilterCheck key={s} label={AVAIL_META[s].label} checked={fAvail.has(s)} onChange={() => toggleIn(setFAvail)(s)} />
              ))}
            </FilterGroup>
          </div>
          <p className="text-pb-faintest text-[10px] mt-3">
            Batting hand, bowling action &amp; bowling type filters need per-player attributes we don’t track yet — coming once those fields exist.
          </p>
        </div>
      )}

      <div className="grid lg:grid-cols-2 gap-4">
        {/* Selected XI — the team sheet */}
        <div className="pb-card overflow-hidden">
          <div className="px-4 py-2.5 border-b pb-hairline flex items-center justify-between">
            <h3 className="font-mono text-[11px] uppercase tracking-wide2 text-pb-faint">Team sheet · {picked.length}</h3>
            {sizeWarn && <span className="font-mono text-[10px] text-amber-300">≠ {target}</span>}
          </div>
          <div className="overflow-auto max-h-[62vh]">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-pb-faintest font-mono text-[9px] uppercase tracking-wide2">
                  <th className="text-left px-2 py-1.5 w-8">#</th>
                  <th className="text-left px-1 py-1.5 w-8">AVL</th>
                  <th className="text-left px-1 py-1.5">Player</th>
                  <th className="text-left px-1 py-1.5">Roles</th>
                  {canEdit && <th className="px-1 py-1.5 w-28"></th>}
                </tr>
              </thead>
              <tbody>
                {picked.length === 0 && (
                  <tr><td colSpan={5} className="px-4 py-8 text-center text-pb-faint">Add players from the pool →</td></tr>
                )}
                {picked.map((sel, i) => {
                  const p = poolById[sel.player_id]
                  if (!p) return null
                  const m = AVAIL_META[p.availability] || AVAIL_META.NO_RESPONSE
                  return (
                    <tr key={sel.player_id} className="border-t pb-hairline">
                      <td className="px-2 py-1.5 font-mono text-[11px] text-pb-faintest">{i + 1}</td>
                      <td className="px-1 py-1.5"><span className={`inline-block w-2.5 h-2.5 rounded-full ${m.dot}`} title={m.label} /></td>
                      <td className="px-1 py-1.5">
                        <span className="flex items-center gap-2 min-w-0">
                          <Avatar p={p} />
                          <span className="truncate">
                            {p.display_name}
                            {(sel.is_captain || sel.is_wicket_keeper) && (
                              <span className="ml-1.5 font-mono text-[9px] text-pb-accent">{[sel.is_captain && '(C)', sel.is_wicket_keeper && '(WK)'].filter(Boolean).join(' ')}</span>
                            )}
                          </span>
                        </span>
                      </td>
                      <td className="px-1 py-1.5 text-pb-faint text-xs">
                        {(p.skill_positions?.length ? p.skill_positions.join(' ') : (p.player_role || '—'))}
                      </td>
                      {canEdit && (
                        <td className="px-1 py-1.5">
                          <span className="flex items-center justify-end gap-1">
                            <button onClick={() => toggleFlag(sel.player_id, 'is_captain')}
                              className={`font-mono text-[10px] px-1 rounded border ${sel.is_captain ? 'bg-pb-accent/15 text-pb-accent border-pb-accent/40' : 'pb-hairline text-pb-faintest'}`} title="Captain">C</button>
                            <button onClick={() => toggleFlag(sel.player_id, 'is_wicket_keeper')}
                              className={`font-mono text-[10px] px-1 rounded border ${sel.is_wicket_keeper ? 'bg-pb-accent/15 text-pb-accent border-pb-accent/40' : 'pb-hairline text-pb-faintest'}`} title="Keeper">WK</button>
                            <button onClick={() => move(i, -1)} disabled={i === 0} className="text-pb-faintest hover:text-pb-text disabled:opacity-30 text-[10px]">▲</button>
                            <button onClick={() => move(i, 1)} disabled={i === picked.length - 1} className="text-pb-faintest hover:text-pb-text disabled:opacity-30 text-[10px]">▼</button>
                            <button onClick={() => remove(sel.player_id)} className="text-pb-faintest hover:text-pb-red text-xs" title="Remove">✕</button>
                          </span>
                        </td>
                      )}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Available pool */}
        <div className="pb-card overflow-hidden">
          <div className="px-4 py-2.5 border-b pb-hairline">
            <h3 className="font-mono text-[11px] uppercase tracking-wide2 text-pb-faint">Available · {availCount}</h3>
          </div>
          <div className="overflow-auto max-h-[62vh]">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-pb-faintest font-mono text-[9px] uppercase tracking-wide2">
                  <th className="text-left px-2 py-1.5 w-8">AVL</th>
                  <th className="text-left px-1 py-1.5">Player</th>
                  <th className="text-left px-1 py-1.5">Roles</th>
                  <th className="text-left px-1 py-1.5">Squad</th>
                </tr>
              </thead>
              <tbody>
                {available.length === 0 && (
                  <tr><td colSpan={4} className="px-4 py-8 text-center text-pb-faint">No players to show.</td></tr>
                )}
                {available.map(p => {
                  const m = AVAIL_META[p.availability] || AVAIL_META.NO_RESPONSE
                  const blocked = p.clash?.length > 0
                  return (
                    <tr key={p.id}
                      onClick={() => add(p)}
                      className={`border-t pb-hairline ${canEdit && !blocked ? 'cursor-pointer hover:bg-pb-surface2/50' : blocked ? 'opacity-60' : ''}`}>
                      <td className="px-2 py-1.5"><span className={`inline-block w-2.5 h-2.5 rounded-full ${m.dot}`} title={m.label} /></td>
                      <td className="px-1 py-1.5">
                        <span className="flex items-center gap-2 min-w-0">
                          <Avatar p={p} />
                          <span className="truncate">
                            {p.display_name}
                            {p.is_dormant && <span className="ml-1.5 font-mono text-[9px] text-amber-300/70 uppercase">dormant</span>}
                            {blocked && <span className="ml-1.5 font-mono text-[9px] text-pb-red/80" title={`Already picked: ${p.clash.join(', ')}`}>⛔ in another XI</span>}
                          </span>
                        </span>
                      </td>
                      <td className="px-1 py-1.5 text-pb-faint text-xs">{(p.skill_positions?.length ? p.skill_positions.join(' ') : (p.player_role || '—'))}</td>
                      <td className="px-1 py-1.5 text-pb-faintest text-xs truncate max-w-[140px]">{p.squads?.join(' · ') || '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </BetterSelectLayout>
  )
}

function FilterGroup({ title, children }) {
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-2 pb-1.5 border-b pb-hairline">{title}</div>
      <div className="space-y-1.5">{children}</div>
    </div>
  )
}

function FilterCheck({ label, checked, onChange }) {
  return (
    <label className="flex items-center gap-2 text-sm text-pb-faint hover:text-pb-text cursor-pointer">
      <input type="checkbox" checked={checked} onChange={onChange} className="accent-pb-accent" />
      {label}
    </label>
  )
}
