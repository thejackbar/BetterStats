// BetterSelect → Squads. A drag-and-drop board of selection pools: one card
// per team plus a leading "Unassigned" pool. A player belongs to exactly one
// squad via players.squad_team_id; dragging a card (or bulk-adding) reassigns
// it through POST /teams/squad-assign.
//
// Clubs can have many squads (16+ for Applecross), so the columns WRAP into a
// responsive grid rather than a single off-screen row, and each is collapsible
// to a compact header. A recency filter keeps the long tail of historical-only
// players out of the Unassigned pool (assigned squads always show their full
// membership, so dormant "backups" you've deliberately filed stay visible).
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { PbSpinner, Field, Input, Select } from '../../../lib/presskit'
import { AVAILABILITY } from '../../../lib/availability'
import {
  Icon, Avatar, Dot, AvailDot, RoleChips, Btn, Search, Chip, Empty, AvailSummary, QuickAvailModal,
} from './ui'

function matchesName(p, q) {
  const needle = q.trim().toLowerCase()
  if (!needle) return true
  return `${p.display_name || ''} ${p.name || ''}`.toLowerCase().includes(needle)
}

// "Played within" recency filter — drops the long tail of historical-only
// players from the Unassigned pool. Never-played players (e.g. a freshly added
// manual player with no appearances yet) are kept.
const YEAR_FILTERS = [
  { value: 0, label: 'Any' },
  { value: 1, label: '≤1y' },
  { value: 2, label: '≤2y' },
  { value: 3, label: '≤3y' },
  { value: 5, label: '≤5y' },
]
function playedWithinYears(lastPlayed, years) {
  if (!years) return true
  if (!lastPlayed) return true
  const cutoff = new Date(); cutoff.setFullYear(cutoff.getFullYear() - years)
  return new Date(lastPlayed + 'T00:00:00') >= cutoff
}

const UNASSIGNED_TINT = 'var(--pb-faintest)'
// Per-column accent tints (a fixed category palette — not the white-label
// accent, not the semantic availability green).
const COLUMN_TINTS = ['#3b82f6', '#a855f7', '#f5b542', '#06b6d4', '#84cc16', '#f97316', '#ef5b5b', '#e879f9', '#22d3ee', '#fb7185']

const EMPTY_TEAM = { name: '', short_name: '', sequence: 0, default_formation: '', is_active: true, grade_id: '' }

function isKeeper(p) { return (p.skill_positions || []).includes('WKT') }

/* ── Team create/edit modal (grade linking preserved) ─────────────────────── */
function TeamModal({ team, onClose, onSaved }) {
  const toast = useToast()
  const [form, setForm] = useState(() => ({ ...EMPTY_TEAM, ...(team || {}), grade_id: team?.grade_id || '' }))
  const [saving, setSaving] = useState(false)
  const [gradeSeasons, setGradeSeasons] = useState([])
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  useEffect(() => { api.bsTeamGradeOptions().then((d) => setGradeSeasons(d.seasons || [])).catch(() => {}) }, [])

  const knownGradeIds = new Set(gradeSeasons.flatMap((s) => s.grades.map((g) => g.id)))
  const currentGradeMissing = form.grade_id && !knownGradeIds.has(form.grade_id)

  const save = async () => {
    if (!form.name.trim()) { toast.error('Squad name is required'); return }
    setSaving(true)
    try {
      const payload = {
        name: form.name.trim(), short_name: form.short_name || null,
        sequence: Number(form.sequence) || 0, default_formation: form.default_formation || null,
        is_active: !!form.is_active, grade_id: form.grade_id || null,
      }
      const saved = team ? await api.bsUpdateTeam(team.id, payload) : await api.bsCreateTeam(payload)
      toast.success(team ? 'Squad updated' : 'Squad added')
      onSaved(saved)
    } catch (e) { toast.error('Save failed: ' + e.message) }
    finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="bg-pb-surface pb-card max-w-md w-full mt-16 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b pb-hairline">
          <h3 className="font-mono text-[11px] uppercase tracking-wide3 text-pb-faint">{team ? 'Edit squad' : 'New squad'}</h3>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text"><Icon name="close" size={16} /></button>
        </div>
        <div className="p-5 space-y-3">
          <Field label="Name"><Input value={form.name} onChange={set('name')} placeholder="e.g. 1st XI" /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Short name"><Input value={form.short_name || ''} onChange={set('short_name')} placeholder="e.g. 1s" /></Field>
            <Field label="Order (1 = top)"><Input type="number" value={form.sequence} onChange={set('sequence')} /></Field>
          </div>
          <Field label="Default formation (optional)"><Input value={form.default_formation || ''} onChange={set('default_formation')} placeholder="e.g. Traditional" /></Field>
          <Field label="Grade (for ladder — auto-linked, override here)">
            <Select value={form.grade_id || ''} onChange={set('grade_id')}>
              <option value="">— Auto-link from match data —</option>
              {currentGradeMissing && <option value={form.grade_id}>{team?.grade_name || 'Current grade'}</option>}
              {gradeSeasons.map((s) => (
                <optgroup key={s.season_id} label={s.season_name}>
                  {s.grades.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                </optgroup>
              ))}
            </Select>
          </Field>
          <label className="flex items-center gap-2 text-sm text-pb-faint">
            <input type="checkbox" checked={!!form.is_active} onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))} className="accent-pb-accent" />
            Active
          </label>
        </div>
        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t pb-hairline">
          <Btn variant="ghost" sm onClick={onClose}>Cancel</Btn>
          <Btn variant="primary" sm onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save'}</Btn>
        </div>
      </div>
    </div>
  )
}

/* ── Bulk-add modal: pick players not already in this squad ────────────────── */
function BulkAddModal({ squadName, candidates, statusOf, onAdd, onClose }) {
  const [sel, setSel] = useState(() => new Set())
  const [q, setQ] = useState('')
  const [years, setYears] = useState(3)
  const [saving, setSaving] = useState(false)
  const list = candidates.filter((p) => matchesName(p, q) && playedWithinYears(p.last_played, years))
  const toggle = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const submit = async () => { setSaving(true); await onAdd([...sel]); setSaving(false); onClose() }

  return (
    <div onClick={onClose} className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div onClick={(e) => e.stopPropagation()} className="w-[460px] max-w-full max-h-[84%] flex flex-col bg-pb-surface rounded-2xl border border-pb-hairline2 overflow-hidden shadow-2xl">
        <div className="flex items-center gap-3 px-[18px] py-4 border-b pb-hairline">
          <div className="flex-1 min-w-0">
            <div className="font-mono text-[10px] uppercase tracking-wide3 text-pb-accent">Add players to</div>
            <div className="font-display font-bold text-[18px] mt-0.5 truncate">{squadName}</div>
          </div>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text p-1"><Icon name="close" size={18} /></button>
        </div>
        <div className="px-4 py-3 border-b pb-hairline flex flex-wrap items-center gap-2">
          <Search value={q} onChange={setQ} placeholder="Search players…" className="flex-1 min-w-[160px]" />
          <div className="flex gap-1">
            {YEAR_FILTERS.map((y) => <Chip key={y.value} label={y.label} active={years === y.value} onClick={() => setYears(y.value)} />)}
          </div>
        </div>
        <div className="overflow-auto flex-1 pb-scroll">
          {list.map((p) => {
            const on = sel.has(p.id)
            return (
              <label key={p.id} className={`flex items-center gap-3 px-4 py-2 border-b pb-hairline cursor-pointer ${on ? 'bg-pb-accent/[0.06]' : ''}`}>
                <input type="checkbox" checked={on} onChange={() => toggle(p.id)} className="accent-pb-accent w-[15px] h-[15px]" />
                <Dot status={statusOf(p.id)} />
                <Avatar player={p} size={26} />
                <span className="flex-1 text-[13.5px] font-medium truncate">{p.display_name || p.name}</span>
                {!playedWithinYears(p.last_played, 3) && <span className="font-mono text-[8.5px] text-amber-300/70 uppercase shrink-0">dormant</span>}
                <RoleChips roles={p.skill_positions} muted />
              </label>
            )
          })}
          {list.length === 0 && <div className="px-4 py-6"><Empty>No players to add.</Empty></div>}
        </div>
        <div className="flex items-center gap-2.5 px-4 py-3 border-t pb-hairline">
          <span className={`font-mono text-xs ${sel.size ? 'text-pb-accent' : 'text-pb-faint'}`}>{sel.size} selected</span>
          <div className="ml-auto flex gap-2">
            <Btn variant="ghost" sm onClick={onClose}>Cancel</Btn>
            <Btn variant="primary" sm icon="plus" disabled={!sel.size || saving} onClick={submit}>
              {saving ? 'Adding…' : `Add ${sel.size || ''} to ${squadName}`}
            </Btn>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ── A draggable player card ───────────────────────────────────────────────── */
function PlayerCard({ p, status, draggable, onDragStart, onDragEnd, onEditAvail }) {
  const meta = AVAILABILITY[status] || AVAILABILITY.NO_RESPONSE
  return (
    <div draggable={draggable} onDragStart={onDragStart} onDragEnd={onDragEnd}
      className={`flex items-center gap-2.5 px-2.5 py-2 rounded-lg border border-pb-hairline ${draggable ? 'cursor-grab active:cursor-grabbing' : ''}`}
      style={{ background: status === 'NO_RESPONSE' ? 'var(--pb-surface2)' : `color-mix(in srgb, ${meta.cssVar} 8%, var(--pb-surface2))` }}>
      {draggable && <span className="text-pb-faintest shrink-0"><Icon name="grip" size={14} /></span>}
      <AvailDot player={p} status={status} onEdit={onEditAvail} />
      <Avatar player={p} size={26} />
      <span className="flex-1 min-w-0 text-[13px] font-medium truncate">{p.display_name || p.name}</span>
      {!playedWithinYears(p.last_played, 3) && <span className="font-mono text-[8px] text-amber-300/60 uppercase shrink-0" title="Hasn't played in 3+ years">dorm</span>}
      <RoleChips roles={p.skill_positions} muted />
    </div>
  )
}

/* ── One squad column (collapsible) ────────────────────────────────────────── */
function SquadColumn({ col, members, statusOf, canManage, collapsed, onToggleCollapse, isOver, dragHandlers, onAdd, onEdit, onDelete, onEditAvail }) {
  const hasKeeper = members.some(isKeeper)
  const nAvail = members.filter((m) => statusOf(m.id) === 'AVAILABLE').length
  const sorted = useMemo(
    () => [...members].sort((a, b) =>
      (AVAILABILITY[statusOf(a.id)]?.rank ?? 9) - (AVAILABILITY[statusOf(b.id)]?.rank ?? 9)
      || (a.display_name || a.name || '').localeCompare(b.display_name || b.name || '')),
    [members, statusOf],
  )

  return (
    <div {...dragHandlers} className="pb-card flex flex-col min-h-0 transition-colors self-start"
      style={{ borderColor: isOver ? 'var(--pb-accent)' : undefined, background: isOver ? 'color-mix(in srgb, var(--pb-accent) 5%, var(--pb-surface))' : undefined }}>
      <div className="px-3 py-2.5 border-b pb-hairline">
        <div className="flex items-center gap-2">
          <button onClick={onToggleCollapse} className="text-pb-faintest hover:text-pb-text shrink-0" title={collapsed ? 'Expand' : 'Collapse'}>
            <span className="inline-block transition-transform" style={{ transform: collapsed ? 'rotate(0deg)' : 'rotate(90deg)' }}><Icon name="chevron" size={13} /></span>
          </button>
          <span className="w-2 h-2 rounded-sm shrink-0" style={{ background: col.tint }} />
          <span className="font-display font-bold text-[14px] truncate">{col.name}</span>
          <span className="ml-auto font-mono text-xs text-pb-faint pb-num shrink-0">{members.length}</span>
          {canManage && !col.unassigned && (
            <div className="flex items-center gap-1 ml-1 shrink-0">
              <button onClick={onEdit} title="Edit squad" className="text-pb-faintest hover:text-pb-text p-0.5"><Icon name="filter" size={13} /></button>
              <button onClick={onDelete} title="Delete squad" className="text-pb-faintest hover:text-pb-red p-0.5"><Icon name="close" size={13} /></button>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 mt-1.5 pl-[26px]">
          {col.grade_name && <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint truncate">{col.grade_name}</span>}
          {members.length > 0 && !hasKeeper && !col.unassigned && <span className="text-[10px] text-pb-amber">· no keeper</span>}
          <span className="ml-auto inline-flex items-center gap-1 text-[11px] text-pb-faint shrink-0"><Dot status="AVAILABLE" size={7} /> {nAvail}</span>
        </div>
        {collapsed && members.length > 0 && <div className="mt-2 pl-[26px]"><AvailSummary players={members.map((m) => ({ availability: statusOf(m.id) }))} compact hideTotal /></div>}
      </div>

      {!collapsed && (
        <>
          <div className="overflow-auto flex-1 p-2 flex flex-col gap-1.5 pb-scroll" style={{ maxHeight: 360 }}>
            {sorted.map((p) => (
              <PlayerCard key={p.id} p={p} status={statusOf(p.id)} draggable={canManage}
                onDragStart={() => dragHandlers.onCardDragStart(p.id)} onDragEnd={dragHandlers.onCardDragEnd}
                onEditAvail={onEditAvail ? () => onEditAvail(p) : undefined} />
            ))}
            {members.length === 0 && (
              <div className="m-1 px-2.5 py-5 text-center text-pb-faintest text-[11.5px] border border-dashed border-pb-hairline2 rounded-lg">
                {col.unassigned ? 'Everyone shown is assigned' : 'Empty — drag or add players'}
              </div>
            )}
          </div>
          {canManage && !col.unassigned && (
            <div className="p-2 border-t pb-hairline">
              <button onClick={onAdd}
                className="w-full inline-flex items-center justify-center gap-1.5 rounded-lg border border-dashed border-pb-hairline2 text-pb-faint hover:text-pb-accent hover:border-pb-accent/40 py-1.5 text-xs transition-colors">
                <Icon name="plus" size={14} /> Add players
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default function AdminTeams() {
  const { hasCapability } = useAuth()
  const toast = useToast()
  const canManage = hasCapability(CAP.MANAGE_SELECTIONS)

  const [teams, setTeams] = useState(null)
  const [players, setPlayers] = useState(null)
  const [availability, setAvailability] = useState({})  // playerId → {date:{status}}
  const [firstDate, setFirstDate] = useState(null)
  const [editing, setEditing] = useState(undefined)
  const [addTo, setAddTo] = useState(null)
  const [over, setOver] = useState(null)
  const [seeding, setSeeding] = useState(false)
  const [availEdit, setAvailEdit] = useState(null)     // player for quick-update modal

  // Filters + view
  const [search, setSearch] = useState('')
  const [years, setYears] = useState(3)                // Unassigned recency filter; default ≤3y
  const [collapsed, setCollapsed] = useState(() => new Set())
  const dragId = useRef(null)

  const loadTeams = useCallback(() => {
    api.bsListTeams(true).then(setTeams).catch((e) => { toast.error(e.message); setTeams([]) })
  }, [toast])
  const loadPlayers = useCallback(() => {
    api.adminListPlayers().then((rows) => setPlayers(rows.filter((p) => p.is_player !== false)))
      .catch((e) => { toast.error(e.message); setPlayers([]) })
  }, [toast])
  const loadMatrix = useCallback(() => {
    api.bsAvailabilityMatrix()
      .then((d) => { setAvailability(d.availability || {}); setFirstDate((d.dates || [])[0]?.date || null) })
      .catch(() => {})
  }, [])

  useEffect(() => { loadTeams() }, [loadTeams])
  useEffect(() => { loadPlayers() }, [loadPlayers])
  useEffect(() => { loadMatrix() }, [loadMatrix])

  const statusOf = useCallback(
    (id) => (firstDate && availability[id]?.[firstDate]?.status) || 'NO_RESPONSE',
    [availability, firstDate],
  )

  // Columns: Unassigned first, then teams by sequence/name.
  const columns = useMemo(() => {
    const cols = [{ key: '__unassigned__', id: null, name: 'Unassigned', unassigned: true, tint: UNASSIGNED_TINT }]
    ;(teams || []).forEach((t, i) => cols.push({
      key: t.id, id: t.id, name: t.name, grade_name: t.grade_name,
      tint: COLUMN_TINTS[i % COLUMN_TINTS.length], team: t,
    }))
    return cols
  }, [teams])

  // Members of a column. Search applies everywhere; the recency filter applies
  // only to the Unassigned pool (assigned squads always show full membership,
  // so a dormant "backup" you've filed into BackUps stays visible there).
  const membersOf = useCallback((col) => {
    let list = (players || []).filter((p) => (p.squad_team_id || null) === col.id)
    if (search.trim()) list = list.filter((p) => matchesName(p, search))
    if (col.unassigned) list = list.filter((p) => playedWithinYears(p.last_played, years))
    return list
  }, [players, search, years])

  // For the Unassigned "showing X of Y" hint.
  const unassignedTotal = useMemo(
    () => (players || []).filter((p) => !p.squad_team_id).length,
    [players],
  )

  const assign = useCallback(async (ids, squadId) => {
    if (!ids.length) return
    const prev = players
    setPlayers((ps) => ps.map((p) => (ids.includes(p.id) ? { ...p, squad_team_id: squadId } : p)))
    try { await api.bsAssignSquad(ids, squadId) }
    catch (e) { setPlayers(prev); toast.error('Move failed: ' + e.message) }
  }, [players, toast])

  const onDrop = (col) => {
    setOver(null)
    const id = dragId.current
    dragId.current = null
    if (!id) return
    const player = players.find((p) => p.id === id)
    if (player && (player.squad_team_id || null) !== col.id) assign([id], col.id)
  }

  const toggleCollapse = (key) => setCollapsed((s) => { const n = new Set(s); n.has(key) ? n.delete(key) : n.add(key); return n })
  const collapseAll = () => setCollapsed(new Set(columns.map((c) => c.key)))
  const expandAll = () => setCollapsed(new Set())

  const pickAvail = async (status) => {
    const p = availEdit
    setAvailEdit(null)
    if (!p) return
    if (!firstDate) { toast.error('No upcoming fixtures to set availability against'); return }
    setAvailability((a) => ({ ...a, [p.id]: { ...(a[p.id] || {}), [firstDate]: { status } } }))
    try { await api.bsSetAvailability({ player_id: p.id, date: firstDate, status }) }
    catch (e) { toast.error('Could not update availability: ' + e.message); loadMatrix() }
  }

  const seed = async () => {
    setSeeding(true)
    try { const r = await api.bsSeedTeams(); toast.success(`Created ${r.created} squad(s) from match data`); loadTeams() }
    catch (e) { toast.error('Seed failed: ' + e.message) }
    finally { setSeeding(false) }
  }
  const del = async (t) => {
    if (!window.confirm(`Delete squad "${t.name}"? Players in it become Unassigned.`)) return
    try { await api.bsDeleteTeam(t.id); toast.success('Deleted'); loadTeams(); loadPlayers() }
    catch (e) { toast.error('Delete failed: ' + e.message) }
  }

  const loading = teams === null || players === null
  const actions = canManage && (
    <div className="flex gap-2">
      {(teams?.length || 0) > 0 && <Btn variant="ghost" sm icon="bolt" onClick={seed} disabled={seeding}>{seeding ? 'Seeding…' : 'Auto-seed'}</Btn>}
      <Btn variant="primary" sm icon="plus" onClick={() => setEditing(null)}>New squad</Btn>
    </div>
  )

  return (
    <BetterSelectLayout title="Squads" actions={actions}>
      {editing !== undefined && (
        <TeamModal team={editing} onClose={() => setEditing(undefined)} onSaved={() => { setEditing(undefined); loadTeams() }} />
      )}
      {addTo && (
        <BulkAddModal squadName={addTo.name}
          candidates={(players || []).filter((p) => (p.squad_team_id || null) !== addTo.id)}
          statusOf={statusOf} onAdd={(ids) => assign(ids, addTo.id)} onClose={() => setAddTo(null)} />
      )}
      {availEdit && (
        <QuickAvailModal player={availEdit} dateLabel={firstDate}
          current={statusOf(availEdit.id)} onPick={pickAvail} onClose={() => setAvailEdit(null)} />
      )}

      {loading ? <PbSpinner message="Loading squads…" /> : (
        (teams.length === 0) ? (
          <div className="pb-card px-5 py-12 text-center">
            <p className="text-pb-faint text-sm mb-4">No squads yet.{canManage && ' Auto-seed from your match history, or create one.'}</p>
            {canManage && (
              <div className="flex gap-2 justify-center">
                <Btn variant="ghost" sm icon="bolt" onClick={seed} disabled={seeding}>{seeding ? 'Seeding…' : 'Auto-seed from data'}</Btn>
                <Btn variant="primary" sm icon="plus" onClick={() => setEditing(null)}>New squad</Btn>
              </div>
            )}
          </div>
        ) : (
          <>
            {/* Toolbar: search + Unassigned recency filter + collapse controls */}
            <div className="flex flex-wrap items-center gap-3 mb-4">
              <Search value={search} onChange={setSearch} placeholder="Search players…" className="w-[220px]" />
              <div className="flex items-center gap-1.5">
                <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest">Unassigned: played</span>
                {YEAR_FILTERS.map((y) => <Chip key={y.value} label={y.label} active={years === y.value} onClick={() => setYears(y.value)} />)}
              </div>
              <div className="ml-auto flex items-center gap-3">
                <span className="text-pb-faint text-[12.5px]"><b className="text-pb-text pb-num">{players.length}</b> players · <b className="text-pb-text pb-num">{teams.length}</b> squads</span>
                <div className="flex gap-1">
                  <Btn variant="ghost" sm onClick={collapseAll}>Collapse all</Btn>
                  <Btn variant="ghost" sm onClick={expandAll}>Expand all</Btn>
                </div>
              </div>
            </div>

            <div className="grid gap-3 items-start" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))' }}>
              {columns.map((col) => {
                const members = membersOf(col)
                const isUnassignedFiltered = col.unassigned && (years > 0 || search.trim())
                return (
                  <div key={col.key}>
                    <SquadColumn
                      col={col} members={members} statusOf={statusOf} canManage={canManage}
                      collapsed={collapsed.has(col.key)} onToggleCollapse={() => toggleCollapse(col.key)}
                      isOver={over === col.key}
                      dragHandlers={{
                        onDragOver: canManage ? (e) => { e.preventDefault(); setOver(col.key) } : undefined,
                        onDragLeave: canManage ? () => setOver((o) => (o === col.key ? null : o)) : undefined,
                        onDrop: canManage ? () => onDrop(col) : undefined,
                        onCardDragStart: (id) => { dragId.current = id },
                        onCardDragEnd: () => { dragId.current = null; setOver(null) },
                      }}
                      onAdd={() => setAddTo(col.team)} onEdit={() => setEditing(col.team)} onDelete={() => del(col.team)}
                      onEditAvail={canManage ? setAvailEdit : undefined} />
                    {isUnassignedFiltered && !collapsed.has(col.key) && members.length < unassignedTotal && (
                      <div className="text-[10.5px] text-pb-faintest mt-1 px-1">
                        Showing {members.length} of {unassignedTotal} unassigned · {unassignedTotal - members.length} hidden by filters
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </>
        )
      )}
    </BetterSelectLayout>
  )
}
