// BetterSelect → Players. Master–detail roster + the canonical player profile:
// a filterable list on the left, the shared <Profile> panel (selection snapshot
// + inline-editable management fields) on the right. The profile UI itself now
// lives in components/player/PlayerProfilePanel so Admin → Players renders the
// exact same thing.
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { nameMatchesSearch, nameSortKey } from '../../../lib/nameFormat'
import { ALPHABET, RANGES, letterOfName, rangeOfName, groupByLetter } from '../../../lib/playerAlphabet'
import { PbSpinner } from '../../../lib/presskit'
import { bowls, bowlingLabel } from '../../../lib/playerAttributes'
import { Profile, draftFromProfile, patchFromDraft } from '../../../components/player/PlayerProfilePanel'
import {
  Icon, Avatar, AvailDot, RoleChips, Btn, Empty,
  QuickAvailModal, RecencySelect, playedWithinYears,
  AVAIL_ORDER, AVAILABILITY,
} from './ui'
import { useFilters, FilterBar } from './filters'
import '../../../styles/players-list.css'

function normGender(g) { const s = (g || '').toLowerCase(); return s.startsWith('f') ? 'female' : s.startsWith('m') ? 'male' : '' }

function statusOfMatrixRow(row) {
  return row?.status ?? 'NO_RESPONSE'
}

/* ── List row ─────────────────────────────────────────────────────────────── */
function PlayerRow({ p, active, selected, status, squadName, onSelect, onOpenProfile, onToggleSel, onEditAvail, canEditAvail }) {
  const inactive = p.status === 'inactive'
  const hasContact = !!(p.email || p.phone)
  return (
    <div onClick={onSelect}
      className="flex items-center gap-3 px-3.5 py-2.5 cursor-pointer border-b border-pb-hairline transition"
      style={{ background: active ? 'color-mix(in srgb, var(--pb-accent) 7%, transparent)' : 'transparent', opacity: inactive ? 0.6 : 1 }}>
      <input type="checkbox" checked={selected} onClick={(e) => e.stopPropagation()} onChange={onToggleSel}
        className="accent-pb-accent w-[15px] h-[15px]" />
      <span onClick={(e) => { e.stopPropagation(); onOpenProfile() }} title="Open profile"
        className="inline-flex cursor-pointer rounded-full"
        style={{ boxShadow: `0 0 0 2px ${active ? 'var(--pb-accent)' : 'transparent'}` }}>
        <Avatar player={p} size={32} />
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-medium truncate">{p.display_name || p.name}</span>
          {p.is_overseas && (
            <span title={`Overseas${p.overseas_country ? ` — ${p.overseas_country}` : ''}`}
              className="font-mono text-[8.5px] text-pb-amber bg-pb-amber/10 px-[5px] py-px rounded">OS</span>
          )}
        </div>
        <div className="text-[11px] text-pb-faint mt-px truncate">
          {[p.batting_hand === 'LEFT' ? 'LHB' : p.batting_hand === 'RIGHT' ? 'RHB' : null,
            bowls(p.bowling_action, p.bowling_type) ? bowlingLabel(p.bowling_action, p.bowling_type) : null]
            .filter(Boolean).join(' · ')}
        </div>
      </div>
      {squadName && (
        <span className="font-mono text-[9px] text-pb-faint bg-pb-surface2 px-1.5 py-0.5 rounded">{squadName}</span>
      )}
      <RoleChips roles={p.skill_positions || []} muted />
      <span className="flex items-center gap-1.5 justify-end">
        <AvailDot player={p} status={status} onEdit={canEditAvail ? () => onEditAvail(p) : undefined} />
      </span>
      <span className="flex items-center gap-2 justify-end">
        <span title={hasContact ? 'Contact on file' : 'No contact'} className={`flex ${hasContact ? 'text-pb-dim' : 'text-pb-faintest'}`}>
          <Icon name={hasContact ? 'check' : 'close'} size={13} />
        </span>
        {inactive
          ? <span className="font-mono text-[9px] text-pb-faint border border-pb-hairline2 px-[5px] py-px rounded">INACTIVE</span>
          : <span className="w-1.5 h-1.5 rounded-full bg-pb-accent" title="Active" />}
      </span>
    </div>
  )
}

/* ── List panel ───────────────────────────────────────────────────────────── */
function PlayerList({ players, statusOf, squadNameOf, selectedIds, selectedId, onSelect, onOpenProfile, canEdit, teams, onBulkSquad, onBulkInactive, onEditAvail }) {
  const [years, setYears] = useState(0)        // 0 = any time (quiet recency control)
  const [sel, setSel] = useState(() => new Set())
  const [bulkSquad, setBulkSquad] = useState('')

  const squadOptions = useMemo(() => teams.map((t) => ({ value: t.id, label: t.name })), [teams])
  const facets = useMemo(() => [
    { key: 'squad', label: 'Squad', type: 'multi', options: squadOptions },
    { key: 'avail', label: 'Availability', type: 'multi', options: AVAIL_ORDER.map((s) => ({ value: s, label: AVAILABILITY[s].label, dot: AVAILABILITY[s].cssVar })) },
    { key: 'role', label: 'Role', type: 'multi', options: [
      { value: 'Batter', label: 'Batter' }, { value: 'Bowler', label: 'Bowler' },
      { value: 'All Rounder', label: 'All-rounder' }, { value: 'Wicketkeeper', label: 'Keeper' },
    ] },
    { key: 'gender', label: 'Gender', type: 'single', options: [
      { value: 'male', label: 'Men' }, { value: 'female', label: 'Women' },
    ] },
    { key: 'selected', label: 'Selected', type: 'single', options: [
      { value: 'selected', label: 'Selected this round' }, { value: 'unselected', label: 'Not selected' },
    ] },
    { key: 'inactive', label: 'Include inactive', type: 'bool' },
    { key: 'nocontact', label: 'Missing contact', type: 'bool' },
    { key: 'overseas', label: 'Overseas', type: 'bool' },
    { key: 'nophoto', label: 'Missing photo', type: 'bool' },
    { key: 'newbie', label: 'Never played', type: 'bool' },
  ], [squadOptions])
  const filters = useFilters(facets)
  const { values, search } = filters
  const searching = search.trim().length > 0

  const nameOf = (p) => p.display_name || p.name || ''

  // Filtered + surname-sorted. Alphabet range/grouping happens after.
  const base = useMemo(() => players.filter((p) => {
    if (!values.inactive && p.status === 'inactive') return false
    if (search.trim() && !nameMatchesSearch(p.display_name || p.name, search)) return false
    if (values.role?.length && !values.role.includes(p.player_role)) return false
    if (values.squad?.length && !values.squad.includes(p.squad_team_id)) return false
    if (values.avail?.length && !values.avail.includes(statusOf(p.id))) return false
    if (values.gender && normGender(p.gender) !== values.gender) return false
    if (values.selected === 'selected' && !selectedIds.has(p.id)) return false
    if (values.selected === 'unselected' && selectedIds.has(p.id)) return false
    if (values.nocontact && (p.email || p.phone)) return false
    if (values.overseas && !p.is_overseas) return false
    if (values.nophoto && p.photo_url) return false
    if (values.newbie && p.last_played) return false
    if (!playedWithinYears(p.last_played, years)) return false
    return true
  }).sort((a, b) => nameSortKey(nameOf(a)).localeCompare(nameSortKey(nameOf(b)))),
  [players, values, search, years, statusOf, selectedIds])

  const [range, setRange] = useState(RANGES[0].key)
  const scrollRef = useRef(null)
  const headerRefs = useRef({})
  const pendingJump = useRef(null)

  const rangeCounts = useMemo(() => {
    const m = {}; RANGES.forEach((r) => (m[r.key] = 0))
    base.forEach((p) => { const k = rangeOfName(nameOf(p)); m[k] = (m[k] || 0) + 1 })
    return m
  }, [base])
  const shown = useMemo(() => searching ? base : base.filter((p) => rangeOfName(nameOf(p)) === range), [base, searching, range])
  const groups = useMemo(() => groupByLetter(shown, nameOf), [shown])
  const letterSet = useMemo(() => new Set(base.map((p) => letterOfName(nameOf(p)))), [base])

  const scrollToLetter = useCallback((L) => {
    const el = headerRefs.current[L]; const sc = scrollRef.current
    if (el && sc) sc.scrollTop = Math.max(0, el.offsetTop - 4)
  }, [])
  useEffect(() => {
    if (pendingJump.current) { scrollToLetter(pendingJump.current); pendingJump.current = null }
  }, [range, shown, scrollToLetter])
  const jumpTo = useCallback((L) => {
    if (!searching) {
      const r = RANGES.find((rg) => L >= rg.from && L <= rg.to)
      if (r && r.key !== range) { pendingJump.current = L; setRange(r.key); return }
    }
    scrollToLetter(L)
  }, [searching, range, scrollToLetter])

  const toggleSel = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const clearSel = () => setSel(new Set())

  return (
    <div className="pl-root pb-card bg-pb-surface flex flex-col min-h-0 h-[70vh] lg:h-full overflow-hidden">
      <div className="px-3.5 py-3 border-b border-pb-hairline">
        <FilterBar filters={filters} facets={facets} searchPlaceholder="Search players…"
          count={base.length} total={players.length}
          right={<RecencySelect value={years} onChange={setYears} />} />
      </div>

      {!searching && (
        <div className="px-3 py-2 border-b border-pb-hairline flex items-center gap-2 flex-wrap">
          <div className="pl-ranges">
            {RANGES.map((r) => (
              <button key={r.key}
                className={`pl-rangetab${range === r.key ? ' on' : ''}${!rangeCounts[r.key] ? ' empty' : ''}`}
                onClick={() => { setRange(r.key); if (scrollRef.current) scrollRef.current.scrollTop = 0 }}>
                {r.label}<i>{rangeCounts[r.key] || 0}</i>
              </button>
            ))}
          </div>
          <span className="pl-shown">{shown.length} shown</span>
        </div>
      )}

      <div className="flex-1 min-h-0 flex gap-1.5 p-1.5">
        <div ref={scrollRef} className="relative overflow-auto flex-1 min-w-0 bs-scroll sb-prominent rounded-lg">
          {shown.length === 0
            ? <div className="px-4 py-8"><Empty>{searching ? 'No players match these filters.' : 'No players in this range.'}</Empty></div>
            : groups.map(([L, glist]) => (
              <section key={L}>
                <div className="pl-letterhead" ref={(el) => { headerRefs.current[L] = el }}>
                  <span>{L}</span><i>{glist.length}</i>
                </div>
                {glist.map((p) => (
                  <PlayerRow key={p.id} p={p} active={p.id === selectedId} selected={sel.has(p.id)}
                    status={statusOf(p.id)} squadName={squadNameOf(p)}
                    onSelect={() => onSelect(p.id)} onOpenProfile={() => onOpenProfile(p.id)} onToggleSel={() => toggleSel(p.id)}
                    onEditAvail={onEditAvail} canEditAvail={!!onEditAvail} />
                ))}
              </section>
            ))}
        </div>
        {!searching && (
          <div className="pl-rail">
            {ALPHABET.map((L) => {
              const has = letterSet.has(L)
              const here = groups.some(([g]) => g === L)
              return (
                <button key={L} className={`pl-rail-l${here ? ' here' : ''}${has ? '' : ' off'}`}
                  disabled={!has} onClick={() => jumpTo(L)}>{L}</button>
              )
            })}
          </div>
        )}
      </div>

      {canEdit && sel.size > 0 && (
        <div className="px-3.5 py-2.5 border-t border-pb-hairline flex items-center gap-3 flex-wrap"
          style={{ background: 'color-mix(in srgb, var(--pb-accent) 5%, transparent)' }}>
          <span className="font-mono text-xs text-pb-accent">{sel.size} selected</span>
          <span className="text-[12.5px] text-pb-dim">set squad</span>
          <select value={bulkSquad} onChange={(e) => setBulkSquad(e.target.value)}
            className="bg-pb-surface2 text-pb-text border border-pb-hairline2 rounded-lg px-2.5 py-1.5 text-[12.5px] cursor-pointer focus:outline-none focus:border-pb-accent">
            <option value="">— pick —</option>
            {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <Btn variant="soft" sm disabled={!bulkSquad} onClick={async () => { await onBulkSquad([...sel], bulkSquad); clearSel() }}>Apply</Btn>
          <Btn variant="ghost" sm onClick={async () => { await onBulkInactive([...sel]); clearSel() }}>Mark inactive</Btn>
          <Btn variant="ghost" sm onClick={clearSel}>Clear</Btn>
        </div>
      )}
    </div>
  )
}

export default function BetterSelectPlayers() {
  const { hasCapability } = useAuth()
  const toast = useToast()
  const canEdit = hasCapability(CAP.MANAGE_PLAYERS)
  const [searchParams, setSearchParams] = useSearchParams()

  const [players, setPlayers] = useState(null)   // roster (adminListPlayers)
  const [teams, setTeams] = useState([])         // bsListTeams
  const [availability, setAvailability] = useState({}) // playerId → {date: {status}}
  const [firstDate, setFirstDate] = useState(null)     // next upcoming date
  const [selectedIds, setSelectedIds] = useState(() => new Set()) // picked in any XI this round

  // ?player=<id> deep-link — set when an Avatar is clicked anywhere in
  // BetterSelect. Selecting a player keeps the URL in sync so it's shareable
  // and the back button works.
  const [selId, setSelId] = useState(() => searchParams.get('player') || null)
  const [profile, setProfile] = useState(null)   // full profile of selId
  const [draft, setDraft] = useState(null)
  const [savedTick, setSavedTick] = useState(false)
  const [saving, setSaving] = useState(false)
  const [availEdit, setAvailEdit] = useState(null) // { player, date } for the quick-update modal

  // Load roster + teams + availability matrix (matrix degrades gracefully).
  const loadRoster = useCallback(() => {
    api.adminListPlayers()
      .then((rows) => {
        setPlayers(rows)
        // Default to the first player only when nothing's been deep-linked or
        // chosen, and the deep-linked id actually exists in this roster.
        setSelId((cur) => {
          if (cur && rows.some((r) => r.id === cur)) return cur
          return rows.length ? rows[0].id : null
        })
      })
      .catch((e) => { toast.error(e.message); setPlayers([]) })
  }, [toast])

  useEffect(() => { loadRoster() }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  // Follow ?player= changes that happen while already mounted (e.g. clicking an
  // avatar elsewhere routes here with a new id).
  useEffect(() => {
    const pid = searchParams.get('player')
    if (pid && pid !== selId) setSelId(pid)
  }, [searchParams])  // eslint-disable-line react-hooks/exhaustive-deps

  // Keep the URL's ?player= in sync with the active selection (replace, so we
  // don't stack history entries as the user browses the roster).
  useEffect(() => {
    if (!selId) return
    if (searchParams.get('player') === selId) return
    const next = new URLSearchParams(searchParams)
    next.set('player', selId)
    setSearchParams(next, { replace: true })
  }, [selId])  // eslint-disable-line react-hooks/exhaustive-deps

  const loadMatrix = useCallback(() => {
    api.bsAvailabilityMatrix()
      .then((d) => {
        setAvailability(d?.availability || {})
        setFirstDate((d?.dates || [])[0]?.date || null)
      })
      .catch(() => { setAvailability({}); setFirstDate(null) })
  }, [])

  useEffect(() => {
    api.bsListTeams().then((t) => setTeams(t || [])).catch(() => setTeams([]))
    loadMatrix()
  }, [loadMatrix])

  // Who's named in any saved XI for the round of the next upcoming date — powers
  // the "Selected" filter. Degrades to an empty set when there are no fixtures.
  useEffect(() => {
    if (!firstDate) { setSelectedIds(new Set()); return }
    let live = true
    api.bsSelectedPlayers(firstDate)
      .then((d) => { if (live) setSelectedIds(new Set(d?.player_ids || [])) })
      .catch(() => { if (live) setSelectedIds(new Set()) })
    return () => { live = false }
  }, [firstDate])

  // Load the selected player's full profile.
  useEffect(() => {
    if (!selId) { setProfile(null); setDraft(null); return }
    let live = true
    setProfile(null); setDraft(null)
    api.bsGetPlayerProfile(selId)
      .then((p) => { if (live) { setProfile(p); setDraft(draftFromProfile(p)) } })
      .catch((e) => { if (live) toast.error(e.message) })
    return () => { live = false }
  }, [selId, toast])

  // List-row dot = the player's status on the next upcoming date.
  const statusOf = useCallback(
    (id) => (firstDate && availability[id]?.[firstDate]?.status) || 'NO_RESPONSE',
    [availability, firstDate],
  )

  // Quick-update modal: opened from a list dot (date defaults to firstDate) or a
  // specific date cell in the profile snapshot. Writes one (player, date) row.
  const openAvail = useCallback((player, date) => {
    const d = date || firstDate
    if (!d) { toast.error('No upcoming fixtures to set availability against'); return }
    setAvailEdit({ player, date: d })
  }, [firstDate, toast])

  const pickAvail = async (status) => {
    const { player, date } = availEdit || {}
    setAvailEdit(null)
    if (!player || !date) return
    setAvailability((a) => ({ ...a, [player.id]: { ...(a[player.id] || {}), [date]: { ...(a[player.id]?.[date] || {}), status } } }))
    try {
      await api.bsSetAvailability({ player_id: player.id, date, status })
      // Refresh the selected player's profile snapshot dots if it's this player.
      if (player.id === selId) {
        api.bsGetPlayerProfile(selId).then((p) => { setProfile(p) }).catch(() => {})
      }
    } catch (e) { toast.error('Could not update availability: ' + e.message); loadMatrix() }
  }

  const teamNameById = useMemo(() => Object.fromEntries(teams.map((t) => [t.id, t.name])), [teams])
  const squadNameOf = useCallback((p) => (p.squad_team_id ? teamNameById[p.squad_team_id] : null), [teamNameById])

  // Dirty-tracking: compare normalised current draft to the loaded profile.
  const dirty = useMemo(() => {
    if (!profile || !draft) return false
    const base = patchFromDraft(draftFromProfile(profile))
    const cur = patchFromDraft(draft)
    return JSON.stringify(base) !== JSON.stringify(cur)
  }, [profile, draft])

  const onSave = async () => {
    if (!selId || !draft || saving) return
    setSaving(true)
    try {
      const updated = await api.bsUpdatePlayerProfile(selId, patchFromDraft(draft))
      setProfile(updated)
      setDraft(draftFromProfile(updated))
      setSavedTick(true)
      setTimeout(() => setSavedTick(false), 1800)
      // Reflect edits (squad/status/overseas/contact) back into the list row.
      setPlayers((rows) => (rows || []).map((r) => r.id === selId ? { ...r, ...patchFromDraft(draft), display_name: updated.display_name } : r))
    } catch (e) {
      toast.error('Save failed: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  // Photo upload/remove happens inside the profile panel; reflect the new URL
  // into the panel header avatar and the list row immediately.
  const onPhotoChange = useCallback((url) => {
    setProfile((p) => p ? { ...p, photo_url: url } : p)
    setPlayers((rows) => (rows || []).map((r) => r.id === selId ? { ...r, photo_url: url } : r))
  }, [selId])

  const onBulkSquad = async (ids, squadId) => {
    try {
      await Promise.all(ids.map((id) => api.bsUpdatePlayerProfile(id, { squad_team_id: squadId })))
      setPlayers((rows) => (rows || []).map((r) => ids.includes(r.id) ? { ...r, squad_team_id: squadId } : r))
      if (ids.includes(selId)) setDraft((d) => d ? { ...d, squad_team_id: squadId } : d)
      toast.success(`Assigned ${ids.length} player${ids.length === 1 ? '' : 's'} to ${teamNameById[squadId] || 'squad'}`)
    } catch (e) { toast.error('Bulk assign failed: ' + e.message) }
  }
  const onBulkInactive = async (ids) => {
    try {
      await Promise.all(ids.map((id) => api.bsUpdatePlayerProfile(id, { status: 'inactive' })))
      setPlayers((rows) => (rows || []).map((r) => ids.includes(r.id) ? { ...r, status: 'inactive' } : r))
      if (ids.includes(selId)) setDraft((d) => d ? { ...d, status: 'inactive' } : d)
      toast.success(`Marked ${ids.length} player${ids.length === 1 ? '' : 's'} inactive`)
    } catch (e) { toast.error('Bulk update failed: ' + e.message) }
  }

  if (players === null) {
    return <BetterSelectLayout title="Players"><PbSpinner message="Loading players…" /></BetterSelectLayout>
  }

  // Give the profile panel the team list so the Squad <select> can render.
  const profileForView = profile ? { ...profile, _teams: teams } : null

  return (
    <BetterSelectLayout title="Players">
      <div className="grid gap-4 grid-cols-1 lg:grid-cols-[minmax(380px,1fr)_1.35fr] lg:h-[calc(100vh-140px)]">
        <PlayerList
          players={players} statusOf={statusOf} squadNameOf={squadNameOf} selectedIds={selectedIds}
          selectedId={selId} onSelect={setSelId} onOpenProfile={setSelId}
          canEdit={canEdit} teams={teams} onBulkSquad={onBulkSquad} onBulkInactive={onBulkInactive}
          onEditAvail={canEdit ? (p) => openAvail(p, null) : undefined} />
        <div className="pb-card bg-pb-surface min-h-0 h-[80vh] lg:h-full overflow-hidden">
          {!selId
            ? <div className="p-6"><Empty>Select a player</Empty></div>
            : (!profileForView || !draft)
              ? <PbSpinner message="Loading profile…" />
              : <Profile profile={profileForView} draft={draft} setDraft={setDraft}
                  dirty={dirty} saved={savedTick} onSave={onSave} canEdit={canEdit}
                  onEditAvail={openAvail} canEditAvail={canEdit}
                  onPhotoChange={onPhotoChange} />}
        </div>
      </div>

      {availEdit && (
        <QuickAvailModal
          player={availEdit.player}
          dateLabel={availEdit.date}
          current={availability[availEdit.player.id]?.[availEdit.date]?.status || 'NO_RESPONSE'}
          onPick={pickAvail}
          onClose={() => setAvailEdit(null)} />
      )}
    </BetterSelectLayout>
  )
}
