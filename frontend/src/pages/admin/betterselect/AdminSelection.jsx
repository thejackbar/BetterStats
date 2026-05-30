import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { nameMatchesSearch } from '../../../lib/nameFormat'
import { PbSpinner, Btn } from '../../../lib/presskit'
import { AVAIL_RANK } from './selection/shared'
import SelectionFilters from './selection/SelectionFilters'
import TeamSheet from './selection/TeamSheet'
import PlayerPool from './selection/PlayerPool'

// Status meta, row tints and the Avatar / roleText / rowState helpers live in
// ./selection/shared, shared with the extracted TeamSheet / PlayerPool / SelectionFilters.
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

export default function AdminSelection() {
  const { fixtureId } = useParams()
  const navigate = useNavigate()
  const { hasCapability } = useAuth()
  const toast = useToast()
  const canEdit = hasCapability(CAP.MANAGE_SELECTIONS)

  const [data, setData] = useState(null)
  const [picked, setPicked] = useState([]) // ordered [{ player_id, is_captain, is_wicket_keeper }]
  const [search, setSearch] = useState('')
  const [format, setFormat] = useState(11)  // overwritten by the club default on load
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
        setFormat(d.default_team_size ?? 11)  // club default (persisted), 11 a side by default
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

  // Facet plumbing for the SelectionFilters panel: one dispatcher + a snapshot.
  const FACET_SETTERS = { squads: setFSquads, roles: setFRoles, avail: setFAvail, batHand: setFBatHand, bowlAction: setFBowlAction, bowlType: setFBowlType, activity: setFActivity }
  const toggleFacet = (key, val) => toggleIn(FACET_SETTERS[key])(val)
  const facets = { squads: fSquads, roles: fRoles, avail: fAvail, batHand: fBatHand, bowlAction: fBowlAction, bowlType: fBowlType, activity: fActivity }

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

  // Team size is a persisted club default (so it survives a reload), editable
  // here by selectors. Update locally first, then save in the background.
  const changeFormat = async (size) => {
    setFormat(size)
    if (!canEdit) return
    try { await api.bsSetDefaultTeamSize(size) }
    catch (e) { toast.error('Could not save team size: ' + e.message) }
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
          <select value={format} onChange={e => changeFormat(Number(e.target.value))}
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
        <SelectionFilters
          squadOptions={squadOptions}
          filterCount={filterCount}
          onClear={clearFilters}
          facets={facets}
          onToggle={toggleFacet}
        />
      )}

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mb-2 font-mono text-[10px] text-pb-faint">
        <LegendDot cls="bg-pb-positive" label="Available" />
        <LegendDot cls="bg-pb-amber" label="Maybe" />
        <LegendDot cls="bg-pb-faintest" label="No response" />
        <LegendDot cls="bg-pb-red" label="Unavailable" />
        <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 rounded bg-pb-red/15 border border-pb-red/40" /> Picked elsewhere (blocked)</span>
        <span className="flex items-center gap-1.5"><span className="text-amber-300/70">dormant</span> inactive recently</span>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <TeamSheet
          picked={picked}
          poolById={poolById}
          canEdit={canEdit}
          onDragStart={onDragStart}
          onDragOver={onDragOver}
          onDrop={onDrop}
          onToggleFlag={toggleFlag}
          onRemove={remove}
        />

        <PlayerPool available={available} canEdit={canEdit} onAdd={add} />
      </div>
    </BetterSelectLayout>
  )
}

// FilterGroup + FilterCheck now live in lib/filters (shared with Availability).
function LegendDot({ cls, label }) {
  return <span className="flex items-center gap-1.5"><span className={`inline-block w-2.5 h-2.5 rounded-full ${cls}`} /> {label}</span>
}
