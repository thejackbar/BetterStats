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
  RecencySelect, playedWithinYears, FilterButton, FilterPanel, FacetGroup,
} from './ui'

function matchesName(p, q) {
  const needle = q.trim().toLowerCase()
  if (!needle) return true
  return `${p.display_name || ''} ${p.name || ''}`.toLowerCase().includes(needle)
}

const ROLE_CHIPS = ['BAT', 'BWL', 'ALL', 'WKT']
const ROLE_LABEL = { BAT: 'Bat', BWL: 'Bowl', ALL: 'All-r', WKT: 'WK' }

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

/* ── Bulk-add modal ──────────────────────────────────────────────────────────
 * Two modes: a fixed target (the "Add players" button on a squad) or "choose a
 * squad" (the toolbar Bulk-add tool) where you pick the destination here. Either
 * way: multi-select players, then assign them all at once. */
function BulkAddModal({ fixedTeam, teams, players, statusOf, onAssign, onClose }) {
  const [sel, setSel] = useState(() => new Set())
  const [q, setQ] = useState('')
  const [years, setYears] = useState(0)
  const [targetId, setTargetId] = useState(fixedTeam?.id || '')
  const [saving, setSaving] = useState(false)

  const nameById = useMemo(() => new Map((teams || []).map((t) => [t.id, t.name])), [teams])
  const targetName = fixedTeam?.name || nameById.get(targetId) || ''
  // Candidates = everyone not already in the chosen target.
  const list = useMemo(() => (players || []).filter((p) =>
    (p.squad_team_id || null) !== (targetId || null)
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
            const cur = p.squad_team_id ? nameById.get(p.squad_team_id) : null
            return (
              <label key={p.id} className={`flex items-center gap-3 px-4 py-2 border-b pb-hairline cursor-pointer ${on ? 'bg-pb-accent/[0.06]' : ''}`}>
                <input type="checkbox" checked={on} onChange={() => toggle(p.id)} className="accent-pb-accent w-[15px] h-[15px]" />
                <Dot status={statusOf(p.id)} />
                <Avatar player={p} size={26} />
                <span className="flex-1 text-[13.5px] font-medium truncate">{p.display_name || p.name}</span>
                {cur && <span className="font-mono text-[9px] text-pb-faintest truncate shrink-0">in {cur}</span>}
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
            <Btn variant="primary" sm icon="plus" disabled={!sel.size || !targetId || saving} onClick={submit}>
              {saving ? 'Adding…' : `Add ${sel.size || ''}${targetName ? ' to ' + targetName : ''}`}
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

/* ── Auto-assign modal: suggest a squad per player from where they played ──── */
function AutoAssignModal({ onApply, onClose }) {
  const toast = useToast()
  const [seasons, setSeasons] = useState(2)
  const [onlyUnassigned, setOnlyUnassigned] = useState(true)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)      // { seasons_considered, suggestions, unmatched }
  const [picked, setPicked] = useState(() => new Set())
  const [applying, setApplying] = useState(false)
  const [showUnmatched, setShowUnmatched] = useState(false)

  const preview = useCallback(async (s = seasons, ou = onlyUnassigned) => {
    setLoading(true); setResult(null)
    try {
      const d = await api.bsAutoAssignSuggest({ seasons: s, onlyUnassigned: ou })
      setResult(d)
      setPicked(new Set((d.suggestions || []).map((x) => x.player_id)))
    } catch (e) { toast.error('Preview failed: ' + e.message) }
    finally { setLoading(false) }
  }, [seasons, onlyUnassigned, toast])

  useEffect(() => { preview(2, true) }, [])   // initial preview with defaults

  const toggle = (pid) => setPicked((s) => { const n = new Set(s); n.has(pid) ? n.delete(pid) : n.add(pid); return n })

  const groups = useMemo(() => {
    const m = new Map()
    ;(result?.suggestions || []).forEach((s) => {
      if (!m.has(s.team_id)) m.set(s.team_id, { name: s.team_name, rows: [] })
      m.get(s.team_id).rows.push(s)
    })
    return [...m.values()]
  }, [result])

  const apply = async () => {
    const chosen = (result?.suggestions || []).filter((s) => picked.has(s.player_id))
    if (!chosen.length) return
    setApplying(true)
    try {
      const byTeam = new Map()
      chosen.forEach((s) => { if (!byTeam.has(s.team_id)) byTeam.set(s.team_id, []); byTeam.get(s.team_id).push(s.player_id) })
      await onApply([...byTeam.entries()])
      toast.success(`Assigned ${chosen.length} player${chosen.length === 1 ? '' : 's'} to their squads`)
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
            <div className="text-[12px] text-pb-faint mt-1">Each player is matched to the squad they played the most games for over the chosen window. Review and adjust before applying — nothing is saved until you hit Apply.</div>
          </div>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text p-1 shrink-0"><Icon name="close" size={18} /></button>
        </div>

        {/* Controls */}
        <div className="px-4 py-3 border-b pb-hairline flex flex-wrap items-center gap-3">
          <span className="inline-flex items-center gap-1.5 text-[12px] text-pb-faint">
            Last
            {[1, 2, 3, 5].map((n) => (
              <Chip key={n} label={`${n}`} active={seasons === n} onClick={() => { setSeasons(n); preview(n, onlyUnassigned) }} />
            ))}
            season{seasons === 1 ? '' : 's'}
          </span>
          <label className="inline-flex items-center gap-2 text-[12px] text-pb-faint cursor-pointer">
            <input type="checkbox" checked={onlyUnassigned} onChange={(e) => { setOnlyUnassigned(e.target.checked); preview(seasons, e.target.checked) }} className="accent-pb-accent w-[14px] h-[14px]" />
            Only players without a squad
          </label>
          {result?.seasons_considered?.length > 0 && (
            <span className="ml-auto font-mono text-[10px] text-pb-faintest truncate" title={result.seasons_considered.join(', ')}>{result.seasons_considered.join(' · ')}</span>
          )}
        </div>

        {/* Body */}
        <div className="overflow-auto flex-1 pb-scroll">
          {loading ? <div className="py-10"><PbSpinner message="Working out squads…" /></div> : (
            total === 0 ? (
              <div className="px-4 py-10"><Empty>{onlyUnassigned ? 'No unassigned players have games in this window. Try more seasons, or untick “only players without a squad”.' : 'Everyone is already in the squad they played most for.'}</Empty></div>
            ) : (
              <>
                {groups.map((g) => (
                  <div key={g.name}>
                    <div className="sticky top-0 z-10 bg-pb-surface2 px-4 py-1.5 flex items-center gap-2 border-b pb-hairline">
                      <span className="font-display font-bold text-[13px]">{g.name}</span>
                      <span className="font-mono text-[10px] text-pb-faint">{g.rows.filter((r) => picked.has(r.player_id)).length}/{g.rows.length}</span>
                    </div>
                    {g.rows.map((s) => {
                      const on = picked.has(s.player_id)
                      return (
                        <label key={s.player_id} className={`flex items-center gap-3 px-4 py-2 border-b pb-hairline cursor-pointer ${on ? '' : 'opacity-50'}`}>
                          <input type="checkbox" checked={on} onChange={() => toggle(s.player_id)} className="accent-pb-accent w-[15px] h-[15px]" />
                          <span className="flex-1 text-[13.5px] font-medium truncate">{s.player_name}</span>
                          {s.current_team_name && <span className="font-mono text-[10px] text-pb-faintest truncate">from {s.current_team_name}</span>}
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
  const [seeding, setSeeding] = useState(false)
  const [autoAssign, setAutoAssign] = useState(false)  // auto-assign modal open
  const [availEdit, setAvailEdit] = useState(null)     // player for quick-update modal

  // Filters + view
  const [search, setSearch] = useState('')
  const [years, setYears] = useState(3)                // Unassigned recency filter; default ≤3y
  const [showFilters, setShowFilters] = useState(false)
  const [roleF, setRoleF] = useState(null)             // skill-position filter (all columns)
  const [availOnly, setAvailOnly] = useState(false)    // available-only filter (all columns)
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

  const activeFilters = (roleF ? 1 : 0) + (availOnly ? 1 : 0) + (years ? 1 : 0)

  // Members of a column. Search / role / availability apply everywhere; the
  // recency filter applies only to the Unassigned pool (assigned squads always
  // show full membership, so a dormant "backup" you've filed into BackUps stays
  // visible there).
  const membersOf = useCallback((col) => {
    let list = (players || []).filter((p) => (p.squad_team_id || null) === col.id)
    if (search.trim()) list = list.filter((p) => matchesName(p, search))
    if (roleF) list = list.filter((p) => (p.skill_positions || []).includes(roleF))
    if (availOnly) list = list.filter((p) => statusOf(p.id) === 'AVAILABLE')
    if (col.unassigned) list = list.filter((p) => playedWithinYears(p.last_played, years))
    return list
  }, [players, search, roleF, availOnly, years, statusOf])

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
  // Apply auto-assign: one squad-assign call per target team, then reload.
  const applyAutoAssign = async (entries) => {
    for (const [teamId, ids] of entries) await api.bsAssignSquad(ids, teamId)
    loadPlayers()
  }

  const loading = teams === null || players === null
  const actions = canManage && (
    <div className="flex gap-2">
      {(teams?.length || 0) > 0 && <Btn variant="ghost" sm icon="bolt" onClick={seed} disabled={seeding}>{seeding ? 'Seeding…' : 'Auto-seed'}</Btn>}
      {(teams?.length || 0) > 0 && <Btn variant="soft" sm icon="bolt" onClick={() => setAutoAssign(true)}>Auto-assign players</Btn>}
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
          statusOf={statusOf} onAssign={assign} onClose={() => setAddTo(undefined)} />
      )}
      {availEdit && (
        <QuickAvailModal player={availEdit} dateLabel={firstDate}
          current={statusOf(availEdit.id)} onPick={pickAvail} onClose={() => setAvailEdit(null)} />
      )}
      {autoAssign && <AutoAssignModal onApply={applyAutoAssign} onClose={() => setAutoAssign(false)} />}

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
            {/* Toolbar: search + quiet filters + bulk-add + collapse controls */}
            <div className="flex flex-wrap items-center gap-2.5 mb-3">
              <Search value={search} onChange={setSearch} placeholder="Search players…" className="w-[200px]" />
              <FilterButton active={showFilters} count={activeFilters} onClick={() => setShowFilters((v) => !v)} />
              <RecencySelect value={years} onChange={setYears} title="Hide unassigned players who haven’t played recently" />
              {canManage && <Btn variant="soft" sm icon="plus" onClick={() => setAddTo(null)}>Bulk add</Btn>}
              <div className="ml-auto flex items-center gap-3">
                <span className="text-pb-faint text-[12.5px]"><b className="text-pb-text pb-num">{players.length}</b> players · <b className="text-pb-text pb-num">{teams.length}</b> squads</span>
                <div className="flex gap-1">
                  <Btn variant="ghost" sm onClick={collapseAll}>Collapse all</Btn>
                  <Btn variant="ghost" sm onClick={expandAll}>Expand all</Btn>
                </div>
              </div>
            </div>
            {showFilters && (
              <FilterPanel className="mb-4">
                <FacetGroup label="Role">
                  {ROLE_CHIPS.map((r) => <Chip key={r} label={ROLE_LABEL[r]} active={roleF === r} onClick={() => setRoleF(roleF === r ? null : r)} />)}
                </FacetGroup>
                <Chip label="Available only" active={availOnly} onClick={() => setAvailOnly((v) => !v)} />
                <FacetGroup label="Unassigned recency"><RecencySelect value={years} onChange={setYears} /></FacetGroup>
                {activeFilters > 0 && <button onClick={() => { setRoleF(null); setAvailOnly(false); setYears(0) }} className="text-[11.5px] text-pb-accent hover:underline">Clear</button>}
                <span className="ml-auto font-mono text-[10px] text-pb-faintest">Role & availability filter every column · recency only thins Unassigned</span>
              </FilterPanel>
            )}

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
