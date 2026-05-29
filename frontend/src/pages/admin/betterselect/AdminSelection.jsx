import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { nameMatchesSearch } from '../../../lib/nameFormat'
import { PbSpinner, Btn } from '../../../lib/presskit'

// Row state → tint. Order of precedence handled in rowState().
const ROW_TINT = {
  CLASH:       'bg-pb-red/15',
  UNAVAILABLE: 'bg-pb-red/5',
  AVAILABLE:   'bg-pb-accent/5',
  MAYBE:       'bg-amber-400/5',
  DORMANT:     'bg-amber-400/[0.03]',
  NONE:        '',
}
const AVAIL_META = {
  AVAILABLE:   { dot: 'bg-pb-accent',   label: 'Available' },
  UNAVAILABLE: { dot: 'bg-pb-red',      label: 'Unavailable' },
  MAYBE:       { dot: 'bg-amber-400',   label: 'Maybe' },
  NO_RESPONSE: { dot: 'bg-pb-faintest', label: 'No response' },
}
const AVAIL_RANK = { AVAILABLE: 0, MAYBE: 1, NO_RESPONSE: 2, UNAVAILABLE: 3 }
const SKILL_LABELS = { BAT: 'Batsman', BWL: 'Bowler', ALL: 'All Rounder', WKT: 'Wicketkeeper' }
const BAT_HANDS = { LEFT: 'Left handed', RIGHT: 'Right handed' }
const BOWL_ACTIONS = { RIGHT_ARM: 'Right arm', LEFT_ARM: 'Left arm' }
const BOWL_TYPES = {
  FAST: 'Fast', FAST_MEDIUM: 'Fast medium', MEDIUM: 'Medium',
  MEDIUM_FAST: 'Medium fast', FINGER_SPIN: 'Finger spinner', WRIST_SPIN: 'Wrist spinner',
}
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
  if (p.photo_url) return <img src={p.photo_url} alt="" className="w-7 h-7 rounded-full object-cover bg-pb-surface2" />
  const initials = (p.display_name || '?').split(/[ ,]+/).filter(Boolean).slice(0, 2).map(s => s[0]).join('').toUpperCase()
  return <span className="w-7 h-7 rounded-full bg-pb-surface2 text-pb-faint text-[10px] font-mono flex items-center justify-center">{initials}</span>
}

function roleText(p) {
  return p.skill_positions?.length ? p.skill_positions.join(' ') : (p.player_role || '—')
}

export default function AdminSelection() {
  const { fixtureId } = useParams()
  const navigate = useNavigate()
  const { hasCapability } = useAuth()
  const toast = useToast()
  const canEdit = hasCapability(CAP.MANAGE_SELECTIONS)

  const [data, setData] = useState(null)
  const [picked, setPicked] = useState([]) // ordered [{ player_id, is_captain, is_wicket_keeper }]
  const [search, setSearch] = useState('')
  const [format, setFormat] = useState(12)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [showFilters, setShowFilters] = useState(false)
  // Filter facets (empty set = no constraint).
  const [fSquads, setFSquads] = useState(() => new Set())
  const [fRoles, setFRoles] = useState(() => new Set())
  const [fAvail, setFAvail] = useState(() => new Set())
  const [fBatHand, setFBatHand] = useState(() => new Set())
  const [fBowlAction, setFBowlAction] = useState(() => new Set())
  const [fBowlType, setFBowlType] = useState(() => new Set())
  const [fActivity, setFActivity] = useState(() => new Set()) // ACTIVE | DORMANT
  // For the fixture switcher.
  const [allFixtures, setAllFixtures] = useState([])
  // Drag state for reordering the team sheet.
  const dragIdx = useRef(null)

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
  // Fixture switcher options (load once).
  useEffect(() => {
    api.bsSelectionOverview().then(d => setAllFixtures(d.fixtures || [])).catch(() => {})
  }, [])

  const poolById = useMemo(() => {
    const m = {}
    ;(data?.pool || []).forEach(p => { m[p.id] = p })
    return m
  }, [data])

  const pickedIds = useMemo(() => new Set(picked.map(p => p.player_id)), [picked])

  const squadOptions = useMemo(() => {
    const s = new Set()
    ;(data?.pool || []).forEach(p => (p.squads || []).forEach(sq => s.add(sq)))
    return [...s].sort()
  }, [data])

  const available = useMemo(() => {
    let list = (data?.pool || []).filter(p => !pickedIds.has(p.id))
    if (search.trim()) list = list.filter(p => nameMatchesSearch(p.display_name, search))
    if (fSquads.size) list = list.filter(p => (p.squads || []).some(sq => fSquads.has(sq)))
    if (fRoles.size) list = list.filter(p => (p.skill_positions || []).some(c => fRoles.has(c)))
    if (fAvail.size) list = list.filter(p => fAvail.has(p.availability))
    if (fBatHand.size) list = list.filter(p => fBatHand.has(p.batting_hand))
    if (fBowlAction.size) list = list.filter(p => fBowlAction.has(p.bowling_action))
    if (fBowlType.size) list = list.filter(p => fBowlType.has(p.bowling_type))
    if (fActivity.size) list = list.filter(p => fActivity.has(p.is_dormant ? 'DORMANT' : 'ACTIVE'))
    return list.sort((a, b) => {
      const ra = AVAIL_RANK[a.availability] ?? 9, rb = AVAIL_RANK[b.availability] ?? 9
      if (ra !== rb) return ra - rb
      return a.display_name.localeCompare(b.display_name)
    })
  }, [data, pickedIds, search, fSquads, fRoles, fAvail, fBatHand, fBowlAction, fBowlType, fActivity])

  const filterCount = fSquads.size + fRoles.size + fAvail.size + fBatHand.size + fBowlAction.size + fBowlType.size + fActivity.size
  const toggleIn = (setter) => (val) => setter(prev => {
    const next = new Set(prev)
    next.has(val) ? next.delete(val) : next.add(val)
    return next
  })
  const clearFilters = () => {
    setFSquads(new Set()); setFRoles(new Set()); setFAvail(new Set())
    setFBatHand(new Set()); setFBowlAction(new Set()); setFBowlType(new Set()); setFActivity(new Set())
  }

  // Tint a pool row by its most salient state.
  const rowState = (p) => {
    if (p.clash?.length > 0) return 'CLASH'
    if (p.availability === 'UNAVAILABLE') return 'UNAVAILABLE'
    if (p.availability === 'AVAILABLE') return 'AVAILABLE'
    if (p.availability === 'MAYBE') return 'MAYBE'
    if (p.is_dormant) return 'DORMANT'
    return 'NONE'
  }

  const add = (p) => {
    if (!canEdit) return
    if (p.clash?.length > 0) {
      toast.error(`${p.display_name} is already picked for ${p.clash.join(', ')} on this date`)
      return
    }
    setPicked(prev => [...prev, { player_id: p.id, is_captain: false, is_wicket_keeper: false }])
    setDirty(true)
  }
  const remove = (pid) => { setPicked(prev => prev.filter(p => p.player_id !== pid)); setDirty(true) }
  const toggleFlag = (pid, flag) => {
    setPicked(prev => prev.map(p => {
      if (p.player_id === pid) return { ...p, [flag]: !p[flag] }
      return { ...p, [flag]: false } // C and WK are each exclusive
    }))
    setDirty(true)
  }
  // Drag-and-drop reorder.
  const onDragStart = (i) => { dragIdx.current = i }
  const onDragOver = (e) => { e.preventDefault() }
  const onDrop = (i) => {
    const from = dragIdx.current
    dragIdx.current = null
    if (from == null || from === i) return
    setPicked(prev => {
      const next = [...prev]
      const [moved] = next.splice(from, 1)
      next.splice(i, 0, moved)
      return next
    })
    setDirty(true)
  }

  const save = async () => {
    // Warn (but don't block) if the XI doesn't match the chosen format.
    const t = format || 0
    if (t > 0 && picked.length !== t) {
      const diff = picked.length > t ? `${picked.length - t} too many` : `${t - picked.length} too few`
      const ok = window.confirm(
        `You have ${picked.length} player${picked.length === 1 ? '' : 's'} selected for a ${t}-a-side match — ${diff}.\n\nSave anyway?`
      )
      if (!ok) return
    }
    setSaving(true)
    try {
      const players = picked.map((p, i) => ({
        player_id: p.player_id, batting_order: i + 1,
        is_captain: p.is_captain, is_wicket_keeper: p.is_wicket_keeper,
      }))
      const r = await api.bsSetSelection(fixtureId, players)
      toast.success(`Saved ${r.count} player${r.count === 1 ? '' : 's'}`)
      setDirty(false)
      load()
    } catch (e) {
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
  const over = target > 0 && picked.length > target
  const under = target > 0 && picked.length < target
  const sizeWarn = over || under

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
      {/* Fixture header + switcher */}
      <div className="rounded-lg px-5 py-3 mb-3" style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>
        <div className="flex items-center justify-between gap-3">
          <Link to="/admin/betterselect/selection" className="text-[11px] opacity-80 hover:opacity-100">← All teams</Link>
          {allFixtures.length > 1 && (
            <select
              value={fixtureId}
              onChange={e => navigate(`/admin/betterselect/select/${e.target.value}`)}
              className="bg-black/15 rounded px-2 py-1 text-[11px] max-w-[60%]"
              style={{ color: 'var(--pb-bg)' }}
            >
              {allFixtures.map(f => (
                <option key={f.id} value={f.id} style={{ color: '#000' }}>
                  {(f.home_away === 'AWAY' ? '@ ' : 'vs ') + (f.opponent_name || f.label || 'TBC')}{f.played_on ? ` · ${f.played_on}` : ''}
                </option>
              ))}
            </select>
          )}
        </div>
        <h2 className="font-display font-bold text-xl leading-tight mt-1">{title}</h2>
        {sub && <div className="text-sm opacity-90">{sub}</div>}
      </div>

      {/* Size warning banner — prominent, non-blocking */}
      {sizeWarn && (
        <div className="rounded-lg px-4 py-2.5 mb-3 text-sm bg-amber-400/15 border border-amber-400/40 text-amber-200 flex items-center gap-2">
          <span>⚠</span>
          <span>
            {picked.length} selected — {over ? `${picked.length - target} over` : `${target - picked.length} short of`} your {target}-a-side format.
          </span>
        </div>
      )}

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
              {squadOptions.map(sq => <FilterCheck key={sq} label={sq} checked={fSquads.has(sq)} onChange={() => toggleIn(setFSquads)(sq)} />)}
            </FilterGroup>
            <FilterGroup title="Specialist roles">
              {Object.entries(SKILL_LABELS).map(([code, label]) => <FilterCheck key={code} label={label} checked={fRoles.has(code)} onChange={() => toggleIn(setFRoles)(code)} />)}
            </FilterGroup>
            <FilterGroup title="Availability">
              {['AVAILABLE', 'MAYBE', 'NO_RESPONSE', 'UNAVAILABLE'].map(s => <FilterCheck key={s} label={AVAIL_META[s].label} checked={fAvail.has(s)} onChange={() => toggleIn(setFAvail)(s)} />)}
            </FilterGroup>
            <FilterGroup title="Batting">
              {Object.entries(BAT_HANDS).map(([v, l]) => <FilterCheck key={v} label={l} checked={fBatHand.has(v)} onChange={() => toggleIn(setFBatHand)(v)} />)}
            </FilterGroup>
            <FilterGroup title="Bowling — action">
              {Object.entries(BOWL_ACTIONS).map(([v, l]) => <FilterCheck key={v} label={l} checked={fBowlAction.has(v)} onChange={() => toggleIn(setFBowlAction)(v)} />)}
            </FilterGroup>
            <FilterGroup title="Bowling — type">
              {Object.entries(BOWL_TYPES).map(([v, l]) => <FilterCheck key={v} label={l} checked={fBowlType.has(v)} onChange={() => toggleIn(setFBowlType)(v)} />)}
            </FilterGroup>
            <FilterGroup title="Activity">
              <FilterCheck label="Active" checked={fActivity.has('ACTIVE')} onChange={() => toggleIn(setFActivity)('ACTIVE')} />
              <FilterCheck label="Dormant" checked={fActivity.has('DORMANT')} onChange={() => toggleIn(setFActivity)('DORMANT')} />
            </FilterGroup>
          </div>
        </div>
      )}

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mb-2 font-mono text-[10px] text-pb-faint">
        <LegendDot cls="bg-pb-accent" label="Available" />
        <LegendDot cls="bg-amber-400" label="Maybe" />
        <LegendDot cls="bg-pb-faintest" label="No response" />
        <LegendDot cls="bg-pb-red" label="Unavailable" />
        <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 rounded bg-pb-red/15 border border-pb-red/40" /> Picked elsewhere (blocked)</span>
        <span className="flex items-center gap-1.5"><span className="text-amber-300/70">dormant</span> inactive recently</span>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        {/* Team sheet (drag to reorder) */}
        <div className="pb-card overflow-hidden">
          <div className="px-4 py-2.5 border-b pb-hairline flex items-center justify-between">
            <h3 className="font-mono text-[11px] uppercase tracking-wide2 text-pb-faint">Team sheet · {picked.length}</h3>
            {canEdit && picked.length > 1 && <span className="font-mono text-[9px] text-pb-faintest">drag to reorder</span>}
          </div>
          <div className="overflow-auto max-h-[62vh]">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-pb-faintest font-mono text-[9px] uppercase tracking-wide2">
                  <th className="text-left px-2 py-1.5 w-8">#</th>
                  <th className="text-left px-1 py-1.5 w-8">AVL</th>
                  <th className="text-left px-1 py-1.5">Player</th>
                  <th className="text-left px-1 py-1.5">Roles</th>
                  {canEdit && <th className="px-1 py-1.5 w-24"></th>}
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
                    <tr key={sel.player_id}
                      draggable={canEdit}
                      onDragStart={() => onDragStart(i)}
                      onDragOver={onDragOver}
                      onDrop={() => onDrop(i)}
                      className={`border-t pb-hairline ${canEdit ? 'cursor-grab active:cursor-grabbing' : ''}`}>
                      <td className="px-2 py-1.5 font-mono text-[11px] text-pb-faintest">{i + 1}</td>
                      <td className="px-1 py-1.5"><span className={`inline-block w-2.5 h-2.5 rounded-full ${m.dot}`} title={m.label} /></td>
                      <td className="px-1 py-1.5">
                        <span className="flex items-center gap-2 min-w-0">
                          {canEdit && <span className="text-pb-faintest text-xs">⠿</span>}
                          <Avatar p={p} />
                          <span className="truncate">
                            {p.display_name}
                            {(sel.is_captain || sel.is_wicket_keeper) && (
                              <span className="ml-1.5 font-mono text-[9px] text-pb-accent">{[sel.is_captain && '(C)', sel.is_wicket_keeper && '(WK)'].filter(Boolean).join(' ')}</span>
                            )}
                          </span>
                        </span>
                      </td>
                      <td className="px-1 py-1.5 text-pb-faint text-xs">{roleText(p)}</td>
                      {canEdit && (
                        <td className="px-1 py-1.5">
                          <span className="flex items-center justify-end gap-1">
                            <button onClick={() => toggleFlag(sel.player_id, 'is_captain')}
                              className={`font-mono text-[10px] px-1 rounded border ${sel.is_captain ? 'bg-pb-accent/15 text-pb-accent border-pb-accent/40' : 'pb-hairline text-pb-faintest'}`} title="Captain">C</button>
                            <button onClick={() => toggleFlag(sel.player_id, 'is_wicket_keeper')}
                              className={`font-mono text-[10px] px-1 rounded border ${sel.is_wicket_keeper ? 'bg-pb-accent/15 text-pb-accent border-pb-accent/40' : 'pb-hairline text-pb-faintest'}`} title="Keeper">WK</button>
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

        {/* Available pool — row-tinted by state */}
        <div className="pb-card overflow-hidden">
          <div className="px-4 py-2.5 border-b pb-hairline">
            <h3 className="font-mono text-[11px] uppercase tracking-wide2 text-pb-faint">Available · {available.length}</h3>
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
                  <tr><td colSpan={4} className="px-4 py-8 text-center text-pb-faint">No players match these filters.</td></tr>
                )}
                {available.map(p => {
                  const m = AVAIL_META[p.availability] || AVAIL_META.NO_RESPONSE
                  const blocked = p.clash?.length > 0
                  const tint = ROW_TINT[rowState(p)] || ''
                  return (
                    <tr key={p.id}
                      onClick={() => add(p)}
                      title={blocked ? `Already picked for ${p.clash.join(', ')}` : undefined}
                      className={`border-t pb-hairline ${tint} ${canEdit && !blocked ? 'cursor-pointer hover:brightness-125' : blocked ? 'opacity-70 cursor-not-allowed' : ''}`}>
                      <td className="px-2 py-1.5"><span className={`inline-block w-2.5 h-2.5 rounded-full ${m.dot}`} title={m.label} /></td>
                      <td className="px-1 py-1.5">
                        <span className="flex items-center gap-2 min-w-0">
                          <Avatar p={p} />
                          <span className="truncate">
                            {p.display_name}
                            {p.is_dormant && <span className="ml-1.5 font-mono text-[9px] text-amber-300/70 uppercase">dormant</span>}
                            {blocked && <span className="ml-1.5 font-mono text-[9px] text-pb-red/90">⛔ {p.clash.join(', ')}</span>}
                          </span>
                        </span>
                      </td>
                      <td className="px-1 py-1.5 text-pb-faint text-xs">{roleText(p)}</td>
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
function LegendDot({ cls, label }) {
  return <span className="flex items-center gap-1.5"><span className={`inline-block w-2.5 h-2.5 rounded-full ${cls}`} /> {label}</span>
}
