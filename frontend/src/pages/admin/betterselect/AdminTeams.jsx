// BetterSelect → Squads. A drag-and-drop board of selection pools: one card per
// team plus the "Unassigned" pools. A PLAYER CAN BE IN SEVERAL SQUADS AT ONCE —
// a fringe 1st XI player who is also a Colt and plays T20 sits in the 1st XI,
// 2nd XI, Colts and T20 squads, so their card shows in each of those columns.
// Membership is team_members (players.squad_team_ids on the payload); the single
// players.squad_team_id is the derived primary the rest of the app reads.
//
// Dragging a card MOVES it: from one squad to another it moves (leaving every
// other squad the player is in alone), and to Unassigned it removes them from
// that one squad. To ADD a player to a SECOND squad, use the squad's "Add
// players" button, the "＋" on the card, or Auto-assign — all additive. Writes
// go through POST /teams/squad-assign with an action (move/add/remove).
//
// Clubs can have many squads (16+ for Applecross), so the columns WRAP into a
// responsive grid rather than a single off-screen row, and each is collapsible
// to a compact header.
//
// THE UNASSIGNED SIDE IS THREE POOLS, split by gender when the club has a mix.
// "Unassigned" is the working list — active players who are still around and in
// no squad — so a club's whole history doesn't sit in the column a selector
// reads. Everyone else is still on the board, just filed: "Potential fill-ins"
// for players who have dropped off, "Not yet played" for a new signing with no
// appearance. A club that fields both men's and women's sides sees each pool
// split into Men / Women (/ Unspecified) so the lists stay short. Nothing is
// dropped; a card in any pool drags into a squad. Assigned squads always show
// their FULL membership, so a dormant backup you filed stays visible.
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { PbSpinner, Field, Input, Select } from '../../../lib/presskit'
import { formatSeason } from '../../../lib/cricketFormat'
import { AVAILABILITY, AVAIL_ORDER } from '../../../lib/availability'
import {
  Icon, Avatar, Dot, AvailDot, RoleChips, Btn, Search, Chip, Empty, AvailSummary, QuickAvailModal,
  RecencySelect, playedWithinYears, monthsAgoISO,
} from './ui'
import { useFilters, FilterBar } from './filters'

function matchesName(p, q) {
  const needle = q.trim().toLowerCase()
  if (!needle) return true
  return `${p.display_name || ''} ${p.name || ''}`.toLowerCase().includes(needle)
}

// Gender as the board buckets it — 'male' | 'female' | '' (unspecified). Free
// text on the player, so read the first letter (same rule as BetterSelect
// Players). '' when nothing is recorded.
function normGender(g) {
  const s = (g || '').toLowerCase()
  return s.startsWith('f') ? 'female' : s.startsWith('m') ? 'male' : ''
}

// A player's squads (team_members). squad_team_ids is authoritative for the
// board; the single squad_team_id is folded in server-side for legacy rows.
function squadIds(p) { return p.squad_team_ids || [] }
function inSquad(p, teamId) { return squadIds(p).includes(teamId) }
function hasNoSquad(p) { return squadIds(p).length === 0 }
const GENDER_COLS = [{ g: 'male', lbl: 'Men' }, { g: 'female', lbl: 'Women' }, { g: '', lbl: 'Unspecified' }]

// Which unassigned pool a player belongs in. `cutoff` is the club's own
// dormancy window as a YYYY-MM-DD string — the same definition of "still
// around" the availability matrix and the selection pool already use, rather
// than a number this screen invents for itself.
function poolOf(p, cutoff) {
  if (!p.last_played) return 'newcomers'
  return p.last_played < cutoff ? 'fillins' : 'unassigned'
}

// The one thing worth saying on a card beyond the name: a newcomer has no
// history yet, and a dormant player's last season is exactly what you weigh
// when you're looking for a fill-in.
function recencyBadge(p, cutoff) {
  if (!p.last_played) return { text: 'new', title: 'No appearances recorded yet' }
  if (p.last_played < cutoff) return { text: p.last_played.slice(0, 4), title: `Last played ${p.last_played}` }
  return null
}

const DEFAULT_DORMANCY_MONTHS = 24   // matches the backend fallback
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
                <optgroup key={s.season_id} label={formatSeason(s.season_name)}>
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

/* ── Bulk-add modal ──────────────────────────────────────────────────────────
 * Two modes: a fixed target (the "Add players" button on a squad) or "choose a
 * squad" (the toolbar Bulk-add tool) where you pick the destination here. Either
 * way: multi-select players, then assign them all at once. */
function BulkAddModal({ fixedTeam, teams, players, dormantCutoff, statusOf, onAssign, onClose }) {
  const [sel, setSel] = useState(() => new Set())
  const [q, setQ] = useState('')
  const [years, setYears] = useState(0)
  const [targetId, setTargetId] = useState(fixedTeam?.id || '')
  const [saving, setSaving] = useState(false)

  const nameById = useMemo(() => new Map((teams || []).map((t) => [t.id, t.name])), [teams])
  const targetName = fixedTeam?.name || nameById.get(targetId) || ''
  // Candidates = everyone not ALREADY IN the chosen target (a player can be in
  // several squads, so this only excludes the target itself, not every squad).
  // An inactive player is never offered: marking someone inactive takes them
  // OUT of their squads server-side, so adding them here would only be undone.
  const list = useMemo(() => (players || []).filter((p) =>
    !(targetId && inSquad(p, targetId)) && p.status !== 'inactive'
    && matchesName(p, q) && playedWithinYears(p.last_played, years),
  ), [players, targetId, q, years])

  const toggle = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const submit = async () => {
    if (!targetId || !sel.size) return
    setSaving(true)
    try { await onAssign([...sel], targetId); onClose() }
    finally { setSaving(false) }
  }

  return (
    <div onClick={onClose} className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div onClick={(e) => e.stopPropagation()} className="w-[480px] max-w-full max-h-[84%] flex flex-col bg-pb-surface rounded-2xl border border-pb-hairline2 overflow-hidden shadow-2xl">
        <div className="flex items-center gap-3 px-[18px] py-4 border-b pb-hairline">
          <div className="flex-1 min-w-0">
            <div className="font-mono text-[10px] uppercase tracking-wide3 text-pb-accent">{fixedTeam ? 'Add players to' : 'Bulk add to squad'}</div>
            {fixedTeam ? (
              <div className="font-display font-bold text-[18px] mt-0.5 truncate">{fixedTeam.name}</div>
            ) : (
              <select value={targetId} onChange={(e) => setTargetId(e.target.value)}
                className="mt-1 bg-pb-surface2 border pb-hairline rounded-lg px-2.5 py-1.5 text-pb-text text-[15px] font-medium focus:outline-none focus:border-pb-accent">
                <option value="">— choose a squad —</option>
                {(teams || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            )}
          </div>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text p-1"><Icon name="close" size={18} /></button>
        </div>
        <div className="px-4 py-3 border-b pb-hairline flex flex-wrap items-center gap-2">
          <Search value={q} onChange={setQ} placeholder="Search players…" className="flex-1 min-w-[160px]" />
          <RecencySelect value={years} onChange={setYears} />
        </div>
        <div className="overflow-auto flex-1 pb-scroll">
          {list.map((p) => {
            const on = sel.has(p.id)
            const nSquads = squadIds(p).length
            const cur = nSquads === 1 ? nameById.get(squadIds(p)[0]) : (nSquads > 1 ? `${nSquads} squads` : null)
            const badge = recencyBadge(p, dormantCutoff)
            return (
              <label key={p.id} className={`flex items-center gap-3 px-4 py-2 border-b pb-hairline cursor-pointer ${on ? 'bg-pb-accent/[0.06]' : ''}`}>
                <input type="checkbox" checked={on} onChange={() => toggle(p.id)} className="accent-pb-accent w-[15px] h-[15px]" />
                <Dot status={statusOf(p.id)} />
                <Avatar player={p} size={26} />
                <span className="flex-1 text-[13.5px] font-medium truncate">{p.display_name || p.name}</span>
                {cur && <span className="font-mono text-[9px] text-pb-faintest truncate shrink-0">in {cur}</span>}
                {badge && (
                  <span className="font-mono text-[8.5px] text-amber-300/70 uppercase shrink-0"
                    title={badge.title}>{badge.text}</span>
                )}
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
            <Btn variant="primary" sm icon="plus" disabled={!sel.size || !targetId || saving} onClick={submit}>
              {saving ? 'Adding…' : `Add ${sel.size || ''}${targetName ? ' to ' + targetName : ''}`}
            </Btn>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ── "＋ Add to squad" control on a card ──────────────────────────────────────
 * A native <select> on purpose: its dropdown renders OUTSIDE the column's
 * overflow:auto box, where an absolutely-positioned popover would be clipped.
 * It never starts a card drag (draggable off + stopPropagation). Lists only the
 * squads the player is NOT already in — the way to give a fringe player a second
 * (or third) squad without leaving the one they're in. */
function AddToSquadSelect({ p, teams, onAddToSquad }) {
  const options = (teams || []).filter((t) => !inSquad(p, t.id))
  if (!options.length) return null
  return (
    <select
      value="" draggable={false}
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
      onDragStart={(e) => { e.preventDefault(); e.stopPropagation() }}
      onChange={(e) => { const v = e.target.value; e.target.value = ''; if (v) onAddToSquad(p.id, v) }}
      title="Add to another squad"
      className="shrink-0 appearance-none cursor-pointer rounded-md border border-pb-hairline2 bg-pb-surface2 text-pb-faint hover:text-pb-accent hover:border-pb-accent/40 text-[12px] leading-none px-1 py-0.5 focus:outline-none focus:border-pb-accent"
    >
      <option value="">＋</option>
      {options.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
    </select>
  )
}

/* ── A draggable player card ───────────────────────────────────────────────── */
function PlayerCard({ p, status, dormantCutoff, draggable, onDragStart, onDragEnd, onEditAvail, teams, onAddToSquad }) {
  const meta = AVAILABILITY[status] || AVAILABILITY.NO_RESPONSE
  const badge = recencyBadge(p, dormantCutoff)
  return (
    <div draggable={draggable} onDragStart={onDragStart} onDragEnd={onDragEnd}
      className={`flex items-center gap-2.5 px-2.5 py-2 rounded-lg border border-pb-hairline ${draggable ? 'cursor-grab active:cursor-grabbing' : ''}`}
      style={{ background: status === 'NO_RESPONSE' ? 'var(--pb-surface2)' : `color-mix(in srgb, ${meta.cssVar} 8%, var(--pb-surface2))` }}>
      {draggable && <span className="text-pb-faintest shrink-0"><Icon name="grip" size={14} /></span>}
      <AvailDot player={p} status={status} onEdit={onEditAvail} />
      <Avatar player={p} size={26} />
      <span className="flex-1 min-w-0 text-[13px] font-medium truncate">{p.display_name || p.name}</span>
      {p.status === 'inactive' && <span className="font-mono text-[8px] text-pb-faintest uppercase shrink-0" title="Marked inactive">inactive</span>}
      {badge && <span className="font-mono text-[8px] text-amber-300/60 uppercase shrink-0" title={badge.title}>{badge.text}</span>}
      <RoleChips roles={p.skill_positions} muted />
      {draggable && onAddToSquad && <AddToSquadSelect p={p} teams={teams} onAddToSquad={onAddToSquad} />}
    </div>
  )
}

/* ── One squad column (collapsible) ────────────────────────────────────────── */
function SquadColumn({ col, members, dormantCutoff, statusOf, canManage, collapsed, onToggleCollapse, isOver, dragHandlers, onAdd, onEdit, onDelete, onEditAvail, teams, onAddToSquad }) {
  const hasKeeper = members.some(isKeeper)
  const nAvail = members.filter((m) => statusOf(m.id) === 'AVAILABLE').length
  // The card handlers belong to the cards, not the column — spreading them onto
  // the column div hands React two props no DOM element knows, which it warns
  // about on every render.
  const { onCardDragStart, onCardDragEnd, ...columnDrag } = dragHandlers
  const sorted = useMemo(
    () => [...members].sort((a, b) =>
      (AVAILABILITY[statusOf(a.id)]?.rank ?? 9) - (AVAILABILITY[statusOf(b.id)]?.rank ?? 9)
      || (a.display_name || a.name || '').localeCompare(b.display_name || b.name || '')),
    [members, statusOf],
  )

  return (
    <div {...columnDrag} className="pb-card flex flex-col min-h-0 transition-colors self-start"
      style={{ borderColor: isOver ? 'var(--pb-accent)' : undefined, background: isOver ? 'color-mix(in srgb, var(--pb-accent) 5%, var(--pb-surface))' : undefined }}>
      <div className="px-3 py-2.5 border-b pb-hairline">
        <div className="flex items-center gap-2">
          <button onClick={onToggleCollapse} className="text-pb-faintest hover:text-pb-text shrink-0" title={collapsed ? 'Expand' : 'Collapse'}>
            <span className="inline-block transition-transform" style={{ transform: collapsed ? 'rotate(0deg)' : 'rotate(90deg)' }}><Icon name="chevron" size={13} /></span>
          </button>
          <span className="w-2 h-2 rounded-sm shrink-0" style={{ background: col.tint }} />
          <span className="font-display font-bold text-[14px] truncate" title={col.short_name ? col.name : undefined}>{col.short_name || col.name}</span>
          <span className="ml-auto font-mono text-xs text-pb-faint pb-num shrink-0">{members.length}</span>
          {canManage && !col.unassigned && (
            <div className="flex items-center gap-1 ml-1 shrink-0">
              <button onClick={onEdit} title="Edit squad" className="text-pb-faintest hover:text-pb-text p-0.5"><Icon name="filter" size={13} /></button>
              <button onClick={onDelete} title="Delete squad" className="text-pb-faintest hover:text-pb-red p-0.5"><Icon name="trash" size={13} /></button>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 mt-1.5 pl-[26px]">
          {(col.grade_name || col.note) && <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint truncate">{col.grade_name || col.note}</span>}
          {members.length > 0 && !hasKeeper && !col.unassigned && <span className="text-[10px] text-pb-amber">· no keeper</span>}
          <span className="ml-auto inline-flex items-center gap-1 text-[11px] text-pb-faint shrink-0"><Dot status="AVAILABLE" size={7} /> {nAvail}</span>
        </div>
        {collapsed && members.length > 0 && <div className="mt-2 pl-[26px]"><AvailSummary players={members.map((m) => ({ availability: statusOf(m.id) }))} compact hideTotal /></div>}
      </div>

      {!collapsed && (
        <>
          <div className="overflow-auto flex-1 p-2 flex flex-col gap-1.5 pb-scroll" style={{ maxHeight: 360 }}>
            {sorted.map((p) => (
              <PlayerCard key={p.id} p={p} status={statusOf(p.id)} dormantCutoff={dormantCutoff} draggable={canManage}
                onDragStart={() => onCardDragStart(p.id)} onDragEnd={onCardDragEnd}
                onEditAvail={onEditAvail ? () => onEditAvail(p) : undefined}
                teams={teams} onAddToSquad={onAddToSquad} />
            ))}
            {members.length === 0 && (
              <div className="m-1 px-2.5 py-5 text-center text-pb-faintest text-[11.5px] border border-dashed border-pb-hairline2 rounded-lg">
                {col.unassigned ? (col.emptyText || 'Everyone shown is assigned') : 'Empty — drag or add players'}
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

/* ── Auto-assign modal: suggest a squad per player from where they played ──── */
function AutoAssignModal({ onApply, onClose }) {
  const toast = useToast()
  const [seasons, setSeasons] = useState(2)
  const [onlyUnassigned, setOnlyUnassigned] = useState(false)
  const [minSharePct, setMinSharePct] = useState(20)   // a team counts at ≥ this share of a player's games
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)      // { seasons_considered, suggestions, unmatched }
  const [picked, setPicked] = useState(() => new Set())  // keyed `${player_id}:${team_id}`
  const [applying, setApplying] = useState(false)
  const [showUnmatched, setShowUnmatched] = useState(false)

  const keyOf = (s) => `${s.player_id}:${s.team_id}`

  const preview = useCallback(async (s = seasons, ou = onlyUnassigned, share = minSharePct) => {
    setLoading(true); setResult(null)
    try {
      const d = await api.bsAutoAssignSuggest({ seasons: s, onlyUnassigned: ou, minShare: share / 100 })
      setResult(d)
      setPicked(new Set((d.suggestions || []).map((x) => `${x.player_id}:${x.team_id}`)))
    } catch (e) { toast.error('Preview failed: ' + e.message) }
    finally { setLoading(false) }
  }, [seasons, onlyUnassigned, minSharePct, toast])

  useEffect(() => { preview(2, false, 20) }, [])   // initial preview with defaults

  const toggle = (k) => setPicked((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n })

  const groups = useMemo(() => {
    const m = new Map()
    ;(result?.suggestions || []).forEach((s) => {
      if (!m.has(s.team_id)) m.set(s.team_id, { name: s.team_name, rows: [] })
      m.get(s.team_id).rows.push(s)
    })
    return [...m.values()]
  }, [result])

  const apply = async () => {
    const chosen = (result?.suggestions || []).filter((s) => picked.has(keyOf(s)))
    if (!chosen.length) return
    setApplying(true)
    try {
      const byTeam = new Map()
      chosen.forEach((s) => { if (!byTeam.has(s.team_id)) byTeam.set(s.team_id, []); byTeam.get(s.team_id).push(s.player_id) })
      await onApply([...byTeam.entries()])
      const nPlayers = new Set(chosen.map((s) => s.player_id)).size
      toast.success(`Added ${nPlayers} player${nPlayers === 1 ? '' : 's'} to their squads`)
      onClose()
    } catch (e) { toast.error('Apply failed: ' + e.message) }
    finally { setApplying(false) }
  }

  const total = result?.suggestions?.length || 0
  const unmatched = result?.unmatched || []

  return (
    <div onClick={onClose} className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div onClick={(e) => e.stopPropagation()} className="w-[560px] max-w-full max-h-[88%] flex flex-col bg-pb-surface rounded-2xl border border-pb-hairline2 overflow-hidden shadow-2xl">
        <div className="flex items-start gap-3 px-[18px] py-4 border-b pb-hairline">
          <div className="flex-1 min-w-0">
            <div className="font-mono text-[10px] uppercase tracking-wide3 text-pb-accent">Auto-assign squads</div>
            <div className="font-display font-bold text-[18px] mt-0.5">From where players actually played</div>
            <div className="text-[12px] text-pb-faint mt-1">A player is suggested for every squad that is a meaningful share of their games — someone who's played 50% 1sts, 40% 2nds and 10% 3rds is suggested for the 1st and 2nd XI, not the 3rd. This ADDS squads; it never removes one. Nothing is saved until you hit Apply.</div>
          </div>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text p-1 shrink-0"><Icon name="close" size={18} /></button>
        </div>

        {/* Controls */}
        <div className="px-4 py-3 border-b pb-hairline flex flex-wrap items-center gap-3">
          <span className="inline-flex items-center gap-1.5 text-[12px] text-pb-faint">
            Last
            {[1, 2, 3, 5].map((n) => (
              <Chip key={n} label={`${n}`} active={seasons === n} onClick={() => { setSeasons(n); preview(n, onlyUnassigned, minSharePct) }} />
            ))}
            season{seasons === 1 ? '' : 's'}
          </span>
          <span className="inline-flex items-center gap-1.5 text-[12px] text-pb-faint" title="A squad is suggested when it is at least this share of the player's games in the window">
            Min share
            {[10, 20, 33, 50].map((n) => (
              <Chip key={n} label={`${n}%`} active={minSharePct === n} onClick={() => { setMinSharePct(n); preview(seasons, onlyUnassigned, n) }} />
            ))}
          </span>
          <label className="inline-flex items-center gap-2 text-[12px] text-pb-faint cursor-pointer">
            <input type="checkbox" checked={onlyUnassigned} onChange={(e) => { setOnlyUnassigned(e.target.checked); preview(seasons, e.target.checked, minSharePct) }} className="accent-pb-accent w-[14px] h-[14px]" />
            Only players in no squad yet
          </label>
          {result?.seasons_considered?.length > 0 && (
            <span className="ml-auto font-mono text-[10px] text-pb-faintest truncate" title={result.seasons_considered.join(', ')}>{result.seasons_considered.join(' · ')}</span>
          )}
        </div>

        {/* Body */}
        <div className="overflow-auto flex-1 pb-scroll">
          {loading ? <div className="py-10"><PbSpinner message="Working out squads…" /></div> : (
            total === 0 ? (
              <div className="px-4 py-10"><Empty>{onlyUnassigned ? 'No players in no squad have games in this window. Try more seasons, or untick “only players in no squad yet”.' : 'Everyone is already in every squad they play a real share of.'}</Empty></div>
            ) : (
              <>
                {groups.map((g) => (
                  <div key={g.name}>
                    <div className="sticky top-0 z-10 bg-pb-surface2 px-4 py-1.5 flex items-center gap-2 border-b pb-hairline">
                      <span className="font-display font-bold text-[13px]">{g.name}</span>
                      <span className="font-mono text-[10px] text-pb-faint">{g.rows.filter((r) => picked.has(keyOf(r))).length}/{g.rows.length}</span>
                    </div>
                    {g.rows.map((s) => {
                      const k = keyOf(s)
                      const on = picked.has(k)
                      return (
                        <label key={k} className={`flex items-center gap-3 px-4 py-2 border-b pb-hairline cursor-pointer ${on ? '' : 'opacity-50'}`}>
                          <input type="checkbox" checked={on} onChange={() => toggle(k)} className="accent-pb-accent w-[15px] h-[15px]" />
                          <span className="flex-1 text-[13.5px] font-medium truncate">{s.player_name}</span>
                          {typeof s.share === 'number' && <span className="font-mono text-[10px] text-pb-faintest shrink-0">{Math.round(s.share * 100)}%</span>}
                          {s.matched_by === 'grade' && <span className="font-mono text-[8.5px] text-pb-faint uppercase" title="Matched via grade name (no squad matched the team name)">via grade</span>}
                          <span className="font-mono text-[11px] text-pb-faint pb-num shrink-0">{s.games}g</span>
                        </label>
                      )
                    })}
                  </div>
                ))}
                {unmatched.length > 0 && (
                  <div className="px-4 py-3">
                    <button onClick={() => setShowUnmatched((v) => !v)} className="text-[11.5px] text-pb-faint hover:text-pb-text inline-flex items-center gap-1">
                      <span className="inline-block transition-transform" style={{ transform: showUnmatched ? 'rotate(90deg)' : 'none' }}><Icon name="chevron" size={12} /></span>
                      {unmatched.length} player{unmatched.length === 1 ? '' : 's'} couldn’t be matched to a squad
                    </button>
                    {showUnmatched && (
                      <div className="mt-2 space-y-1">
                        {unmatched.map((u) => (
                          <div key={u.player_id} className="flex items-center gap-2 text-[12px] text-pb-faint">
                            <span className="flex-1 truncate">{u.player_name}</span>
                            <span className="font-mono text-[10px] text-pb-faintest truncate">played “{u.top_team_name}” · {u.games}g</span>
                          </div>
                        ))}
                        <p className="text-[10.5px] text-pb-faintest pt-1">No squad is named like their team. Create/rename a squad to match, then re-run.</p>
                      </div>
                    )}
                  </div>
                )}
              </>
            )
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center gap-2.5 px-4 py-3 border-t pb-hairline">
          <span className={`font-mono text-xs ${picked.size ? 'text-pb-accent' : 'text-pb-faint'}`}>{picked.size} selected</span>
          <div className="ml-auto flex gap-2">
            <Btn variant="ghost" sm onClick={onClose}>Cancel</Btn>
            <Btn variant="primary" sm icon="check" disabled={!picked.size || applying || loading} onClick={apply}>
              {applying ? 'Assigning…' : `Apply ${picked.size || ''}`}
            </Btn>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ── Auto-seed modal: discover team names from the last N seasons, tick which
 * ones should become squads, confirm — then squads are created and every
 * player who played is auto-assigned into theirs in one go. Combines what
 * used to be two separate steps (seed, then auto-assign) into one flow so a
 * club realistically ends up with everyone in a squad. */
function AutoSeedModal({ onSeeded, onClose }) {
  const toast = useToast()
  const [seasons, setSeasons] = useState(3)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)   // { seasons_considered, candidates }
  const [picked, setPicked] = useState(() => new Set())
  const [working, setWorking] = useState(false)

  const load = useCallback(async (s) => {
    setLoading(true); setResult(null)
    try {
      const d = await api.bsSeedCandidates({ seasons: s })
      setResult(d)
      setPicked(new Set((d.candidates || []).filter((c) => !c.exists).map((c) => c.name)))
    } catch (e) { toast.error('Preview failed: ' + e.message) }
    finally { setLoading(false) }
  }, [toast])

  useEffect(() => { load(3) }, [load])

  const toggle = (name) => setPicked((s) => { const n = new Set(s); n.has(name) ? n.delete(name) : n.add(name); return n })

  const candidates = result?.candidates || []
  const fresh = candidates.filter((c) => !c.exists)
  const already = candidates.filter((c) => c.exists)

  const confirm = async () => {
    setWorking(true)
    try {
      const seedRes = await api.bsSeedTeams({ names: [...picked] })
      const suggest = await api.bsAutoAssignSuggest({ seasons, onlyUnassigned: true })
      const byTeam = new Map()
      ;(suggest.suggestions || []).forEach((s) => {
        if (!byTeam.has(s.team_id)) byTeam.set(s.team_id, [])
        byTeam.get(s.team_id).push(s.player_id)
      })
      let assigned = 0
      for (const [teamId, ids] of byTeam.entries()) { await api.bsAssignSquad(ids, teamId); assigned += ids.length }
      const unmatched = suggest.unmatched?.length || 0
      toast.success(
        `Created ${seedRes.created} squad${seedRes.created === 1 ? '' : 's'}, assigned ${assigned} player${assigned === 1 ? '' : 's'}`
        + (unmatched ? ` · ${unmatched} still need a manual squad` : ''),
      )
      onSeeded()
      onClose()
    } catch (e) { toast.error('Auto-seed failed: ' + e.message) }
    finally { setWorking(false) }
  }

  return (
    <div onClick={onClose} className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div onClick={(e) => e.stopPropagation()} className="w-[560px] max-w-full max-h-[88%] flex flex-col bg-pb-surface rounded-2xl border border-pb-hairline2 overflow-hidden shadow-2xl">
        <div className="flex items-start gap-3 px-[18px] py-4 border-b pb-hairline">
          <div className="flex-1 min-w-0">
            <div className="font-mono text-[10px] uppercase tracking-wide3 text-pb-accent">Auto-seed squads</div>
            <div className="font-display font-bold text-[18px] mt-0.5">Bring in the teams you've actually played</div>
            <div className="text-[12px] text-pb-faint mt-1">Tick which teams from recent match history should become squads. On confirm we create them, then auto-assign every player who played into their squad.</div>
          </div>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text p-1 shrink-0"><Icon name="close" size={18} /></button>
        </div>

        <div className="px-4 py-3 border-b pb-hairline flex flex-wrap items-center gap-3">
          <span className="inline-flex items-center gap-1.5 text-[12px] text-pb-faint">
            Last
            {[1, 2, 3, 5].map((n) => (
              <Chip key={n} label={`${n}`} active={seasons === n} onClick={() => { setSeasons(n); load(n) }} />
            ))}
            season{seasons === 1 ? '' : 's'}
          </span>
          {result?.seasons_considered?.length > 0 && (
            <span className="ml-auto font-mono text-[10px] text-pb-faintest truncate" title={result.seasons_considered.join(', ')}>{result.seasons_considered.join(' · ')}</span>
          )}
        </div>

        <div className="overflow-auto flex-1 pb-scroll">
          {loading ? <div className="py-10"><PbSpinner message="Looking through match history…" /></div> : (
            fresh.length === 0 ? (
              <div className="px-4 py-10"><Empty>{already.length > 0 ? 'Every team from this window already has a squad.' : 'No team names found in this window.'}</Empty></div>
            ) : (
              fresh.map((c) => {
                const on = picked.has(c.name)
                return (
                  <label key={c.name} className={`flex items-center gap-3 px-4 py-2 border-b pb-hairline cursor-pointer ${on ? '' : 'opacity-50'}`}>
                    <input type="checkbox" checked={on} onChange={() => toggle(c.name)} className="accent-pb-accent w-[15px] h-[15px]" />
                    <span className="flex-1 text-[13.5px] font-medium truncate">{c.name}</span>
                    <span className="font-mono text-[11px] text-pb-faint pb-num shrink-0">{c.players} player{c.players === 1 ? '' : 's'} · {c.games}g</span>
                  </label>
                )
              })
            )
          )}
          {already.length > 0 && (
            <div className="px-4 py-2 text-[10.5px] text-pb-faintest">{already.length} team{already.length === 1 ? '' : 's'} in this window already {already.length === 1 ? 'has' : 'have'} a squad, so it's skipped here, but still gets re-checked when assigning players below.</div>
          )}
        </div>

        <div className="flex items-center gap-2.5 px-4 py-3 border-t pb-hairline">
          <span className={`font-mono text-xs ${picked.size ? 'text-pb-accent' : 'text-pb-faint'}`}>{picked.size} squad{picked.size === 1 ? '' : 's'} to create</span>
          <div className="ml-auto flex gap-2">
            <Btn variant="ghost" sm onClick={onClose}>Cancel</Btn>
            <Btn variant="primary" sm icon="bolt" disabled={working || loading} onClick={confirm}>
              {working ? 'Seeding…' : 'Create & auto-seed players'}
            </Btn>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ── Manage squads modal: a plain list of every squad with a checkbox, for
 * bulk deletion — quicker than the per-column delete icon when cleaning up
 * after an auto-seed that created more (or wrongly-ordered) squads than
 * wanted. Members shown per squad so a full one isn't deleted by mistake. */
function ManageSquadsModal({ teams, players, onDeleted, onClose }) {
  const toast = useToast()
  const [sel, setSel] = useState(() => new Set())
  const [deleting, setDeleting] = useState(false)

  const memberCount = useMemo(() => {
    const m = new Map()
    ;(players || []).forEach((p) => squadIds(p).forEach((tid) => m.set(tid, (m.get(tid) || 0) + 1)))
    return m
  }, [players])

  const sorted = useMemo(
    () => [...(teams || [])].sort((a, b) => (a.sequence || 0) - (b.sequence || 0) || a.name.localeCompare(b.name)),
    [teams],
  )

  const toggle = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const toggleAll = () => setSel((s) => (s.size === sorted.length ? new Set() : new Set(sorted.map((t) => t.id))))

  const submit = async () => {
    if (!sel.size) return
    const names = sorted.filter((t) => sel.has(t.id)).map((t) => t.name)
    if (!window.confirm(`Delete ${sel.size} squad${sel.size === 1 ? '' : 's'} (${names.join(', ')})? Players in them become Unassigned.`)) return
    setDeleting(true)
    try {
      for (const id of sel) await api.bsDeleteTeam(id)
      toast.success(`Deleted ${sel.size} squad${sel.size === 1 ? '' : 's'}`)
      onDeleted()
      onClose()
    } catch (e) { toast.error('Delete failed: ' + e.message) }
    finally { setDeleting(false) }
  }

  return (
    <div onClick={onClose} className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div onClick={(e) => e.stopPropagation()} className="w-[480px] max-w-full max-h-[84%] flex flex-col bg-pb-surface rounded-2xl border border-pb-hairline2 overflow-hidden shadow-2xl">
        <div className="flex items-center gap-3 px-[18px] py-4 border-b pb-hairline">
          <div className="flex-1 min-w-0">
            <div className="font-mono text-[10px] uppercase tracking-wide3 text-pb-accent">Manage squads</div>
            <div className="font-display font-bold text-[18px] mt-0.5">Remove squads in bulk</div>
          </div>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text p-1"><Icon name="close" size={18} /></button>
        </div>
        <label className="flex items-center gap-3 px-4 py-2 border-b pb-hairline cursor-pointer text-[12px] text-pb-faint">
          <input type="checkbox" checked={sorted.length > 0 && sel.size === sorted.length} onChange={toggleAll} className="accent-pb-accent w-[15px] h-[15px]" />
          Select all
        </label>
        <div className="overflow-auto flex-1 pb-scroll">
          {sorted.map((t) => {
            const on = sel.has(t.id)
            return (
              <label key={t.id} className={`flex items-center gap-3 px-4 py-2 border-b pb-hairline cursor-pointer ${on ? 'bg-pb-red/[0.06]' : ''}`}>
                <input type="checkbox" checked={on} onChange={() => toggle(t.id)} className="accent-pb-red w-[15px] h-[15px]" />
                <span className="flex-1 min-w-0 text-[13.5px] font-medium truncate">{t.name}{t.short_name ? ` (${t.short_name})` : ''}</span>
                <span className="font-mono text-[11px] text-pb-faint pb-num shrink-0">{memberCount.get(t.id) || 0} players</span>
              </label>
            )
          })}
          {sorted.length === 0 && <div className="px-4 py-6"><Empty>No squads yet.</Empty></div>}
        </div>
        <div className="flex items-center gap-2.5 px-4 py-3 border-t pb-hairline">
          <span className={`font-mono text-xs ${sel.size ? 'text-pb-red' : 'text-pb-faint'}`}>{sel.size} selected</span>
          <div className="ml-auto flex gap-2">
            <Btn variant="ghost" sm onClick={onClose}>Cancel</Btn>
            <Btn variant="danger" sm icon="trash" disabled={!sel.size || deleting} onClick={submit}>
              {deleting ? 'Deleting…' : `Delete ${sel.size || ''}`}
            </Btn>
          </div>
        </div>
      </div>
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
  const [addTo, setAddTo] = useState(undefined)        // BulkAddModal target: a team (fixed), or null (choose squad)
  const [over, setOver] = useState(null)
  const [autoSeed, setAutoSeed] = useState(false)      // auto-seed modal open
  const [autoAssign, setAutoAssign] = useState(false)  // auto-assign modal open
  const [manageSquads, setManageSquads] = useState(false)  // bulk-delete modal open
  const [resequencing, setResequencing] = useState(false)
  const [availEdit, setAvailEdit] = useState(null)     // player for quick-update modal

  // Filters + view — the fill-in reach is a quiet control; the rest are facets.
  const [dormancyMonths, setDormancyMonths] = useState(DEFAULT_DORMANCY_MONTHS)
  const [fillInYears, setFillInYears] = useState(3)    // how far back the fill-in pool digs
  const [selectedIds, setSelectedIds] = useState(() => new Set()) // picked in any XI this round
  // Collapse state as explicit user overrides (key → bool); a column with no
  // override falls back to its default — the secondary pools (fill-ins, not yet
  // played) start collapsed, everything else open. Kept as overrides because
  // the gender split makes the column keys dynamic.
  const [collapseOverride, setCollapseOverride] = useState(() => new Map())
  // The dragged card: the player AND which squad column they were dragged FROM
  // (null for an unassigned pool), so a drop can MOVE them out of that one squad.
  const dragRef = useRef(null)

  const loadTeams = useCallback(() => {
    api.bsListTeams(true).then(setTeams).catch((e) => { toast.error(e.message); setTeams([]) })
  }, [toast])
  const loadPlayers = useCallback(() => {
    api.adminListPlayers().then((rows) => setPlayers(rows.filter((p) => p.is_player !== false)))
      .catch((e) => { toast.error(e.message); setPlayers([]) })
  }, [toast])
  const loadMatrix = useCallback(() => {
    api.bsAvailabilityMatrix()
      .then((d) => {
        setAvailability(d.availability || {}); setFirstDate((d.dates || [])[0]?.date || null)
        // The club's own dormancy window rides on this payload, so the board
        // splits its pools on the same boundary every other BetterSelect
        // screen uses instead of a hardcoded number of its own.
        if (d.dormancy_months) setDormancyMonths(d.dormancy_months)
      })
      .catch(() => {})
  }, [])

  useEffect(() => { loadTeams() }, [loadTeams])
  useEffect(() => { loadPlayers() }, [loadPlayers])
  useEffect(() => { loadMatrix() }, [loadMatrix])

  // Who's named in any saved XI for the round of the next upcoming date.
  useEffect(() => {
    if (!firstDate) { setSelectedIds(new Set()); return }
    let live = true
    api.bsSelectedPlayers(firstDate)
      .then((d) => { if (live) setSelectedIds(new Set(d?.player_ids || [])) })
      .catch(() => { if (live) setSelectedIds(new Set()) })
    return () => { live = false }
  }, [firstDate])

  const statusOf = useCallback(
    (id) => (firstDate && availability[id]?.[firstDate]?.status) || 'NO_RESPONSE',
    [availability, firstDate],
  )

  // Dormancy boundary as a plain date string, and the pool each unassigned
  // player falls in. Counted before any facet so a column doesn't vanish
  // mid-search — the facets empty it out with the usual empty state instead.
  const dormantCutoff = useMemo(() => monthsAgoISO(dormancyMonths), [dormancyMonths])

  // Split the unassigned pools by gender only when the club fields both — a
  // men's-only (or women's-only) club keeps single lists, the same call
  // ageFilterOptions makes: a split that can only ever answer "everyone" is
  // worse than none. Decided off the ACTIVE unassigned players.
  const genderSplit = useMemo(() => {
    const gs = new Set()
    ;(players || []).forEach((p) => {
      if (hasNoSquad(p) && p.status !== 'inactive') gs.add(normGender(p.gender))
    })
    return gs.has('male') && gs.has('female')
  }, [players])

  // Pre-facet counts of the unassigned side, keyed `${pool}:${bucket}` (+ a
  // `${pool}:__all__` roll-up), plus the inactive count held out of every pool.
  const poolCounts = useMemo(() => {
    const c = { inactive: 0 }
    ;(players || []).forEach((p) => {
      if (!hasNoSquad(p)) return
      if (p.status === 'inactive') { c.inactive += 1; return }
      const pool = poolOf(p, dormantCutoff)
      const bucket = normGender(p.gender)
      c[`${pool}:${bucket}`] = (c[`${pool}:${bucket}`] || 0) + 1
      c[`${pool}:__all__`] = (c[`${pool}:__all__`] || 0) + 1
    })
    return c
  }, [players, dormantCutoff])
  const poolTotal = useCallback(
    (col) => poolCounts[`${col.pool}:${col.gender === null ? '__all__' : col.gender}`] || 0,
    [poolCounts],
  )

  // Columns: the unassigned pools (each split by gender when the club has a
  // mix) first, then teams by sequence/name. Fill-ins and Not-yet-played only
  // appear when they hold someone; the primary Unassigned always shows (both
  // Men and Women when split, so each working list is there even when empty).
  const columns = useMemo(() => {
    const cols = []
    const buckets = genderSplit ? GENDER_COLS : [{ g: null, lbl: null }]
    const POOLS = [
      { pool: 'unassigned', base: 'Unassigned', emptyText: 'Everyone active is in a squad', primary: true },
      { pool: 'fillins', base: 'Potential fill-ins', note: 'Played before, but not lately' },
      { pool: 'newcomers', base: 'Not yet played', note: 'No appearances recorded yet' },
    ]
    let primaryFirst = true
    POOLS.forEach((P) => {
      buckets.forEach((b) => {
        const n = poolCounts[`${P.pool}:${b.g === null ? '__all__' : b.g}`] || 0
        // Primary pool: always show the Men & Women lists (and the single
        // Unassigned when not split); Unspecified only when it holds someone.
        // Secondary pools: only when non-empty.
        const show = P.primary
          ? (b.g === null || b.g === 'male' || b.g === 'female' ? true : n > 0)
          : n > 0
        if (!show) return
        const genderKey = b.g === null ? 'all' : (b.g || 'none')
        const isPrimaryFirst = P.primary && primaryFirst
        if (P.primary) primaryFirst = false
        cols.push({
          key: P.primary && b.g === null ? '__unassigned__' : `__${P.pool}__${genderKey}`,
          id: null, pool: P.pool, gender: b.g, unassigned: true, secondary: !P.primary,
          tint: UNASSIGNED_TINT,
          name: b.lbl ? `${P.base} — ${b.lbl}` : P.base,
          emptyText: P.emptyText || 'Nobody in this window', note: P.note,
          inactiveNote: isPrimaryFirst,
        })
      })
    })
    ;(teams || []).forEach((t, i) => cols.push({
      key: t.id, id: t.id, name: t.name, short_name: t.short_name, grade_name: t.grade_name,
      tint: COLUMN_TINTS[i % COLUMN_TINTS.length], team: t,
    }))
    return cols
  }, [teams, poolCounts, genderSplit])

  const facets = useMemo(() => [
    { key: 'squad', label: 'Squad', type: 'multi', options: (teams || []).map((t) => ({ value: t.id, label: t.name })) },
    { key: 'avail', label: 'Availability', type: 'multi', options: AVAIL_ORDER.map((s) => ({ value: s, label: AVAILABILITY[s].label, dot: AVAILABILITY[s].cssVar })) },
    { key: 'role', label: 'Role', type: 'multi', options: [
      { value: 'BAT', label: 'BAT' }, { value: 'BWL', label: 'BWL' }, { value: 'ALL', label: 'ALL' }, { value: 'WKT', label: 'WK' },
    ] },
    { key: 'selected', label: 'Selected', type: 'single', options: [
      { value: 'selected', label: 'Selected this round' }, { value: 'unselected', label: 'Not selected' },
    ] },
    { key: 'showinactive', label: 'Show inactive players', type: 'bool' },
    { key: 'hideunassigned', label: 'Hide unassigned pools', type: 'bool' },
  ], [teams])
  const filters = useFilters(facets)
  const { values, search } = filters

  // How far back the fill-in pool digs. Only offer windows WIDER than the
  // dormancy boundary — anyone inside it is already in the Unassigned column,
  // so a shorter option could only ever answer "nobody".
  const fillInOptions = useMemo(() => {
    const minYears = Math.ceil(dormancyMonths / 12)
    return [
      ...[1, 2, 3, 5, 10].filter((y) => y > minYears)
        .map((y) => ({ value: y, label: `Fill-ins: played ≤ ${y} yr${y === 1 ? '' : 's'}` })),
      { value: 0, label: 'Fill-ins: any time' },
    ]
  }, [dormancyMonths])
  // Fall back to the narrowest offered window if the stored pick isn't one.
  const fillInReach = fillInOptions.some((o) => o.value === fillInYears) ? fillInYears : fillInOptions[0].value
  const fillInCutoff = useMemo(
    () => (fillInReach ? monthsAgoISO(fillInReach * 12) : null),
    [fillInReach],
  )

  // The squad facet hides whole columns; the bool hides all three unassigned pools.
  const visibleColumns = useMemo(() => columns.filter((col) => {
    if (col.unassigned) return !values.hideunassigned
    if (values.squad?.length) return values.squad.includes(col.id)
    return true
  }), [columns, values.squad, values.hideunassigned])

  // Members of a column. Search / role / availability / selected apply
  // everywhere. The pool split applies only to the unassigned side: an assigned
  // squad always shows its full membership, so a dormant "backup" you filed
  // there on purpose stays visible.
  const membersOf = useCallback((col) => {
    let list
    if (col.unassigned) {
      list = (players || []).filter(hasNoSquad)
      // A club marks someone inactive precisely to take them out of selection,
      // so they are off every pool unless you ask for them.
      if (!values.showinactive) list = list.filter((p) => p.status !== 'inactive')
      list = list.filter((p) => poolOf(p, dormantCutoff) === col.pool)
      if (col.gender !== null && col.gender !== undefined) list = list.filter((p) => normGender(p.gender) === col.gender)
      if (col.pool === 'fillins' && fillInCutoff) list = list.filter((p) => p.last_played >= fillInCutoff)
    } else {
      // A squad column shows everyone whose membership includes it — a player
      // in several squads appears in each. Full membership always (a dormant
      // backup you filed here stays visible).
      list = (players || []).filter((p) => inSquad(p, col.id))
    }
    if (search.trim()) list = list.filter((p) => matchesName(p, search))
    if (values.role?.length) list = list.filter((p) => (p.skill_positions || []).some((r) => values.role.includes(r)))
    if (values.avail?.length) list = list.filter((p) => values.avail.includes(statusOf(p.id)))
    if (values.selected === 'selected') list = list.filter((p) => selectedIds.has(p.id))
    else if (values.selected === 'unselected') list = list.filter((p) => !selectedIds.has(p.id))
    return list
  }, [players, search, values, dormantCutoff, fillInCutoff, statusOf, selectedIds])

  // Optimistically edit a player's membership set, then persist. A drag from
  // one squad to another is a MOVE (remove + add in one call); a drag to
  // Unassigned is a remove; the "Add players" button and the card "＋" are adds.
  const editMembership = useCallback(async (id, { add = null, remove = null }) => {
    if (!add && !remove) return
    const prev = players
    setPlayers((ps) => ps.map((p) => {
      if (p.id !== id) return p
      const s = new Set(squadIds(p))
      if (remove) s.delete(remove)
      if (add) s.add(add)
      return { ...p, squad_team_ids: [...s] }
    }))
    try {
      if (add && remove) await api.bsAssignSquad([id], add, { action: 'move', from: remove })
      else if (add) await api.bsAssignSquad([id], add, { action: 'add' })
      else await api.bsAssignSquad([id], null, { action: 'remove', from: remove })
    } catch (e) { setPlayers(prev); toast.error('Move failed: ' + e.message) }
  }, [players, toast])

  // Additive: add one or many players to a squad, keeping every squad they are
  // already in. Backs the per-squad "Add players" modal and the card "＋".
  const addToSquad = useCallback(async (ids, teamId) => {
    const list = Array.isArray(ids) ? ids : [ids]
    if (!list.length || !teamId) return
    const prev = players
    setPlayers((ps) => ps.map((p) => (list.includes(p.id) && !inSquad(p, teamId)
      ? { ...p, squad_team_ids: [...squadIds(p), teamId] } : p)))
    try { await api.bsAssignSquad(list, teamId, { action: 'add' }) }
    catch (e) { setPlayers(prev); toast.error('Add failed: ' + e.message) }
  }, [players, toast])

  const onDrop = (col) => {
    setOver(null)
    const d = dragRef.current
    dragRef.current = null
    if (!d) return
    const toId = col.id || null   // null for any unassigned pool
    if ((d.fromId || null) === toId) return   // dropped back where it came from
    editMembership(d.id, { add: toId, remove: d.fromId || null })
  }

  const isCollapsed = useCallback(
    (col) => (collapseOverride.has(col.key) ? collapseOverride.get(col.key) : !!col.secondary),
    [collapseOverride],
  )
  const toggleCollapse = (col) => setCollapseOverride((m) => { const n = new Map(m); n.set(col.key, !isCollapsed(col)); return n })
  const collapseAll = () => setCollapseOverride(new Map(columns.map((c) => [c.key, true])))
  const expandAll = () => setCollapseOverride(new Map(columns.map((c) => [c.key, false])))

  const pickAvail = async (status) => {
    const p = availEdit
    setAvailEdit(null)
    if (!p) return
    if (!firstDate) { toast.error('No upcoming fixtures to set availability against'); return }
    setAvailability((a) => ({ ...a, [p.id]: { ...(a[p.id] || {}), [firstDate]: { status } } }))
    try { await api.bsSetAvailability({ player_id: p.id, date: firstDate, status }) }
    catch (e) { toast.error('Could not update availability: ' + e.message); loadMatrix() }
  }

  const del = async (t) => {
    if (!window.confirm(`Delete squad "${t.name}"? Players in it become Unassigned.`)) return
    try { await api.bsDeleteTeam(t.id); toast.success('Deleted'); loadTeams(); loadPlayers() }
    catch (e) { toast.error('Delete failed: ' + e.message) }
  }
  // Apply auto-assign: one ADD per target team (never removes a squad), reload.
  const applyAutoAssign = async (entries) => {
    for (const [teamId, ids] of entries) await api.bsAssignSquad(ids, teamId, { action: 'add' })
    loadPlayers()
  }
  // Re-guess column order for auto-seeded squads (fixes squads created under
  // an older/naive sequence guess — never touches a manually-set order).
  const fixOrder = async () => {
    setResequencing(true)
    try { const r = await api.bsResequenceTeams(); toast.success(`Reordered ${r.updated} squad${r.updated === 1 ? '' : 's'}`); loadTeams() }
    catch (e) { toast.error('Reorder failed: ' + e.message) }
    finally { setResequencing(false) }
  }

  const loading = teams === null || players === null
  const actions = canManage && (
    <div className="flex gap-2">
      <Btn variant="ghost" sm icon="bolt" onClick={() => setAutoSeed(true)}>Auto-seed squads</Btn>
      {(teams?.length || 0) > 0 && <Btn variant="soft" sm icon="bolt" onClick={() => setAutoAssign(true)}>Auto-assign players</Btn>}
      {(teams?.length || 0) > 0 && <Btn variant="ghost" sm icon="reset" onClick={fixOrder} disabled={resequencing}>{resequencing ? 'Reordering…' : 'Fix order'}</Btn>}
      {(teams?.length || 0) > 0 && <Btn variant="ghost" sm icon="trash" onClick={() => setManageSquads(true)}>Manage squads</Btn>}
      <Btn variant="primary" sm icon="plus" onClick={() => setEditing(null)}>New squad</Btn>
    </div>
  )

  return (
    <BetterSelectLayout title="Squads" actions={actions}>
      {editing !== undefined && (
        <TeamModal team={editing} onClose={() => setEditing(undefined)} onSaved={() => { setEditing(undefined); loadTeams() }} />
      )}
      {addTo !== undefined && (
        <BulkAddModal fixedTeam={addTo} teams={teams || []} players={players || []}
          dormantCutoff={dormantCutoff} statusOf={statusOf} onAssign={addToSquad} onClose={() => setAddTo(undefined)} />
      )}
      {availEdit && (
        <QuickAvailModal player={availEdit} dateLabel={firstDate}
          current={statusOf(availEdit.id)} onPick={pickAvail} onClose={() => setAvailEdit(null)} />
      )}
      {autoAssign && <AutoAssignModal onApply={applyAutoAssign} onClose={() => setAutoAssign(false)} />}
      {autoSeed && <AutoSeedModal onSeeded={() => { loadTeams(); loadPlayers() }} onClose={() => setAutoSeed(false)} />}
      {manageSquads && (
        <ManageSquadsModal teams={teams || []} players={players || []}
          onDeleted={() => { loadTeams(); loadPlayers() }} onClose={() => setManageSquads(false)} />
      )}

      {loading ? <PbSpinner message="Loading squads…" /> : (
        (teams.length === 0) ? (
          <div className="pb-card px-5 py-12 text-center">
            <p className="text-pb-faint text-sm mb-4">No squads yet.{canManage && ' Auto-seed from your match history, or create one.'}</p>
            {canManage && (
              <div className="flex gap-2 justify-center">
                <Btn variant="ghost" sm icon="bolt" onClick={() => setAutoSeed(true)}>Auto-seed from data</Btn>
                <Btn variant="primary" sm icon="plus" onClick={() => setEditing(null)}>New squad</Btn>
              </div>
            )}
          </div>
        ) : (
          <>
            {/* Toolbar: shared FilterBar + bulk-add + collapse controls */}
            <FilterBar
              filters={filters} facets={facets} searchPlaceholder="Search players…" className="mb-3"
              right={(<>
                {(poolCounts['fillins:__all__'] || 0) > 0 && (
                  <RecencySelect value={fillInReach} onChange={setFillInYears} options={fillInOptions}
                    title="How far back the Potential fill-ins pool reaches" />
                )}
                {canManage && <Btn variant="soft" sm icon="plus" onClick={() => setAddTo(null)}>Bulk add</Btn>}
                <span className="ml-auto text-pb-faint text-[12.5px]"><b className="text-pb-text pb-num">{players.length}</b> players · <b className="text-pb-text pb-num">{teams.length}</b> squads</span>
                <div className="flex gap-1">
                  <Btn variant="ghost" sm onClick={collapseAll}>Collapse all</Btn>
                  <Btn variant="ghost" sm onClick={expandAll}>Expand all</Btn>
                </div>
              </>)}
            />

            <div className="grid gap-3 items-start" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))' }}>
              {visibleColumns.map((col) => {
                const members = membersOf(col)
                const total = col.unassigned ? poolTotal(col) : 0
                const facetsOn = !!(values.role?.length || values.avail?.length || values.selected || search.trim())
                return (
                  <div key={col.key}>
                    <SquadColumn
                      col={col} members={members} dormantCutoff={dormantCutoff} statusOf={statusOf} canManage={canManage}
                      collapsed={isCollapsed(col)} onToggleCollapse={() => toggleCollapse(col)}
                      isOver={over === col.key}
                      teams={teams} onAddToSquad={addToSquad}
                      dragHandlers={{
                        onDragOver: canManage ? (e) => { e.preventDefault(); setOver(col.key) } : undefined,
                        onDragLeave: canManage ? () => setOver((o) => (o === col.key ? null : o)) : undefined,
                        onDrop: canManage ? () => onDrop(col) : undefined,
                        onCardDragStart: (id) => { dragRef.current = { id, fromId: col.id || null } },
                        onCardDragEnd: () => { dragRef.current = null; setOver(null) },
                      }}
                      onAdd={() => setAddTo(col.team)} onEdit={() => setEditing(col.team)} onDelete={() => del(col.team)}
                      onEditAvail={canManage ? setAvailEdit : undefined} />
                    {col.unassigned && !isCollapsed(col) && (
                      <div className="text-[10.5px] text-pb-faintest mt-1 px-1 space-y-0.5">
                        {facetsOn && members.length < total && (
                          <div>Showing {members.length} of {total} · {total - members.length} hidden by filters</div>
                        )}
                        {col.inactiveNote && !values.showinactive && poolCounts.inactive > 0 && (
                          <div>{poolCounts.inactive} inactive not shown — tick “Show inactive players” to include them.</div>
                        )}
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
