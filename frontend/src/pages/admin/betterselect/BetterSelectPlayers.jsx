// BetterSelect → Players. Master–detail replacement for the cramped edit modal:
// a filterable roster on the left, a rich profile (selection snapshot +
// inline-editable management fields) on the right. Recreates
// docs/design_handoff_betterselect/prototype/bs-players.jsx with real
// components, the live API, and dirty-tracked saves.
import { useState, useEffect, useCallback, useMemo } from 'react'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { nameMatchesSearch } from '../../../lib/nameFormat'
import { PbSpinner } from '../../../lib/presskit'
import {
  Icon, Avatar, Dot, AvailDot, RoleChips, Tag, Btn, Search, Chip, Empty,
  AVAILABILITY, QuickAvailModal, RecencySelect, playedWithinYears,
} from './ui'

/* ── Option sets (mirror AdminPlayers field enums) ───────────────────────── */
const ROLE_OPTS = ['', 'Batter', 'Bowler', 'All Rounder', 'Wicketkeeper', 'Wicketkeeper-Batter']
const ROLE_LABEL = { '': '—' }
const BAT_HANDS = [['', '—'], ['RIGHT', 'Right handed'], ['LEFT', 'Left handed']]
const GENDER_OPTS = [['', '—'], ['male', 'Male'], ['female', 'Female']]

// Bowling action + type merged into one human-readable field. Each entry maps a
// label to the (bowling_action, bowling_type) pair persisted on the player.
const BOWLING_OPTS = [
  ['—', null, null],
  ['Right-arm fast', 'RIGHT_ARM', 'FAST'],
  ['Right-arm fast-medium', 'RIGHT_ARM', 'FAST_MEDIUM'],
  ['Right-arm medium', 'RIGHT_ARM', 'MEDIUM'],
  ['Off spin', 'RIGHT_ARM', 'FINGER_SPIN'],
  ['Leg spin', 'RIGHT_ARM', 'WRIST_SPIN'],
  ['Left-arm fast', 'LEFT_ARM', 'FAST'],
  ['Left-arm medium', 'LEFT_ARM', 'MEDIUM'],
  ['Left-arm orthodox', 'LEFT_ARM', 'FINGER_SPIN'],
  ['Left-arm wrist spin', 'LEFT_ARM', 'WRIST_SPIN'],
]
// (action, type) → label, for deriving the current selection.
function bowlingLabel(action, type) {
  const hit = BOWLING_OPTS.find((o) => o[1] === (action || null) && o[2] === (type || null))
  return hit ? hit[0] : '—'
}
function bowlingFromLabel(label) {
  const hit = BOWLING_OPTS.find((o) => o[0] === label)
  return hit ? { bowling_action: hit[1], bowling_type: hit[2] } : { bowling_action: null, bowling_type: null }
}
function bowls(action, type) {
  return !!(action || type)
}

const ROLE_CHIPS = [['Batter', 'Batter'], ['Bowler', 'Bowler'], ['All-R', 'All Rounder'], ['Wicketkeeper', 'Wicketkeeper']]

function statusOfMatrixRow(row) {
  return row?.status ?? 'NO_RESPONSE'
}

/* ── Inline field controls (match prototype look via pb-* tokens) ─────────── */
function Field({ label, half, children }) {
  return (
    <div className={half ? 'flex-1 min-w-0 basis-[calc(50%-6px)]' : 'flex-1 min-w-0 basis-full'}>
      <label className="block text-[11.5px] text-pb-faint mb-[5px]">{label}</label>
      {children}
    </div>
  )
}
function PSelect({ value, onChange, options }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}
      className="w-full bg-pb-surface2 text-pb-text border border-pb-hairline2 rounded-lg px-2.5 py-2 text-[13.5px] cursor-pointer focus:outline-none focus:border-pb-accent">
      {options.map((o) => Array.isArray(o)
        ? <option key={o[0]} value={o[0]}>{o[1]}</option>
        : <option key={o} value={o}>{ROLE_LABEL[o] ?? o}</option>)}
    </select>
  )
}
function PInput({ value, onChange, placeholder, type }) {
  return (
    <input type={type || 'text'} value={value || ''} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
      className="w-full bg-pb-surface2 text-pb-text border border-pb-hairline2 rounded-lg px-2.5 py-2 text-[13.5px] outline-none focus:border-pb-accent placeholder:text-pb-faint" />
  )
}
function PToggle({ on, onChange, label }) {
  return (
    <label className="flex items-center gap-2.5 cursor-pointer py-2">
      <span onClick={() => onChange(!on)}
        className="relative w-[38px] h-[22px] rounded-full transition shrink-0"
        style={{ background: on ? 'var(--pb-accent)' : 'var(--pb-surface2)', border: `1px solid ${on ? 'var(--pb-accent)' : 'var(--pb-hairline2)'}` }}>
        <span className="absolute top-[2px] w-4 h-4 rounded-full transition-all"
          style={{ left: on ? 18 : 2, background: on ? '#04130c' : 'var(--pb-faint)' }} />
      </span>
      <span className="text-[13.5px] text-pb-text">{label}</span>
    </label>
  )
}

/* ── Selection snapshot (right column, left half) ─────────────────────────── */
function Snapshot({ snapshot, squad, draft, player, onEditAvail, canEditAvail }) {
  const snap = snapshot || {}
  const avail = snap.availability_next || []
  const bat = snap.recent_batting || []
  const bowl = snap.recent_bowling || []
  const showBowling = bowls(draft.bowling_action, draft.bowling_type) && bowl.length > 0
  const lp = snap.last_picked
  const lastPicked = lp
    ? [lp.round, lp.opponent ? `vs ${lp.opponent}` : null].filter(Boolean).join(' · ') || (lp.date || null)
    : null

  return (
    <div className="px-5 py-[18px] border-r border-pb-hairline">
      <div className="font-mono text-[10px] uppercase tracking-wide3 text-pb-faint mb-3.5">Selection snapshot</div>

      {/* Availability — next 4 weeks */}
      <div className="mb-[18px]">
        <div className="text-xs text-pb-faint mb-2">Availability — next 4 weeks</div>
        {avail.length === 0
          ? <div className="text-[11.5px] text-pb-faintest">No upcoming fixtures.</div>
          : (
            <div className="flex gap-2">
              {avail.map((a, j) => (
                <button key={a.date} type="button"
                  onClick={canEditAvail ? () => onEditAvail(player, a.date) : undefined}
                  title={canEditAvail ? 'Update availability for this date' : undefined}
                  className={`flex-1 text-center rounded-lg py-[9px] px-1 ${canEditAvail ? 'cursor-pointer hover:border-pb-accent/50' : 'cursor-default'}`}
                  style={{
                    background: j === 0 ? 'color-mix(in srgb, var(--pb-accent) 5%, transparent)' : 'var(--pb-surface2)',
                    border: `1px solid ${j === 0 ? 'color-mix(in srgb, var(--pb-accent) 25%, transparent)' : 'var(--pb-hairline)'}`,
                  }}>
                  <div className="font-mono text-[9.5px] text-pb-faint">{(a.label || '').replace(/^[A-Za-z]{3} /, '')}</div>
                  <div className="flex justify-center mt-1.5"><Dot status={a.status} size={11} /></div>
                </button>
              ))}
            </div>
          )}
      </div>

      {/* Squad & eligibility */}
      <div className="mb-[18px]">
        <div className="text-xs text-pb-faint mb-2">Squad &amp; eligibility</div>
        {squad
          ? (
            <div className="flex gap-1.5 flex-wrap items-center">
              <Tag tone="accent">{squad.name}</Tag>
              <span className="text-[11.5px] text-pb-faintest">assigned · suggested first for {squad.name} fixtures</span>
            </div>
          )
          : <span className="text-[11.5px] text-pb-faintest">No squad assigned.</span>}
      </div>

      {/* Recent form */}
      <div className="mb-[18px]">
        <div className="text-xs text-pb-faint mb-2">Recent form</div>
        <div className="flex flex-col gap-2.5">
          <div className="flex items-center gap-2">
            <span className="font-mono text-[9.5px] text-pb-faint w-14">BATTING</span>
            <div className="flex gap-1.5">
              {bat.length === 0
                ? <span className="text-[11.5px] text-pb-faintest">No innings yet</span>
                : bat.map((s, i) => (
                  <span key={i} className="pb-num min-w-[28px] text-center py-[5px] rounded-md text-[12.5px] font-semibold"
                    style={{
                      background: s >= 50 ? 'color-mix(in srgb, var(--pb-accent) 14%, transparent)' : 'var(--pb-surface2)',
                      color: s >= 50 ? 'var(--pb-accent)' : s === 0 ? 'var(--pb-red)' : 'var(--pb-dim)',
                      border: '1px solid var(--pb-hairline)',
                    }}>{s}</span>
                ))}
            </div>
          </div>
          {showBowling && (
            <div className="flex items-center gap-2">
              <span className="font-mono text-[9.5px] text-pb-faint w-14">BOWLING</span>
              <div className="flex gap-1.5">
                {bowl.map((f, i) => (
                  <span key={i} className="pb-num min-w-[38px] text-center py-[5px] rounded-md text-[12.5px] font-semibold"
                    style={{
                      background: f.wickets >= 3 ? 'color-mix(in srgb, var(--pb-chart-wickets) 14%, transparent)' : 'var(--pb-surface2)',
                      color: f.wickets >= 3 ? 'var(--pb-chart-wickets)' : 'var(--pb-dim)',
                      border: '1px solid var(--pb-hairline)',
                    }}>{f.wickets}/{f.runs}</span>
                ))}
              </div>
            </div>
          )}
          <div className="flex items-center gap-2">
            <span className="font-mono text-[9.5px] text-pb-faint w-14">CATCHES</span>
            <span className="pb-num font-display font-bold text-base text-pb-text">{snap.season_catches ?? 0}</span>
            <span className="text-[11.5px] text-pb-faintest">this season</span>
          </div>
        </div>
      </div>

      <div>
        <div className="text-xs text-pb-faint mb-1">Last picked</div>
        <div className={`text-[13.5px] ${lastPicked ? 'text-pb-text' : 'text-pb-faint'}`}>{lastPicked || 'Not recently'}</div>
      </div>
    </div>
  )
}

/* ── Details (right column, right half) — inline editable ─────────────────── */
function Details({ draft, set, teams }) {
  const bowlingLabelVal = bowlingLabel(draft.bowling_action, draft.bowling_type)
  return (
    <div className="px-5 py-[18px]">
      <div className="font-mono text-[10px] uppercase tracking-wide3 text-pb-faint mb-3.5">Details</div>
      <div className="flex flex-wrap gap-3">
        <Field label="Squad (selection pool)" half>
          <PSelect value={draft.squad_team_id || ''} onChange={(v) => set('squad_team_id', v || null)}
            options={[['', '— Unassigned —'], ...teams.map((t) => [t.id, t.name])]} />
        </Field>
        <Field label="Role" half>
          <PSelect value={draft.player_role || ''} onChange={(v) => set('player_role', v || null)} options={ROLE_OPTS} />
        </Field>
        <Field label="Batting hand" half>
          <PSelect value={draft.batting_hand || ''} onChange={(v) => set('batting_hand', v || null)} options={BAT_HANDS} />
        </Field>
        <Field label="Bowling" half>
          <PSelect value={bowlingLabelVal}
            onChange={(label) => { const m = bowlingFromLabel(label); set('bowling_action', m.bowling_action); set('bowling_type', m.bowling_type) }}
            options={BOWLING_OPTS.map((o) => [o[0], o[0]])} />
        </Field>
        <Field label="Gender" half>
          <PSelect value={draft.gender || ''} onChange={(v) => set('gender', v || null)} options={GENDER_OPTS} />
        </Field>
        <Field label="Email" half>
          <PInput value={draft.email} onChange={(v) => set('email', v)} type="email" placeholder="—" />
        </Field>
        <Field label="Phone" half>
          <PInput value={draft.phone} onChange={(v) => set('phone', v)} placeholder="—" />
        </Field>
      </div>

      <div className="mt-1.5 border-t border-pb-hairline pt-1.5">
        <PToggle on={!!draft.is_opening_batsman} onChange={(v) => set('is_opening_batsman', v)} label="Opening batsman" />
        <PToggle on={!!draft.is_overseas} onChange={(v) => set('is_overseas', v)} label="Overseas player" />
        {draft.is_overseas && (
          <div className="pl-[47px] pb-1.5">
            <PInput value={draft.overseas_country} onChange={(v) => set('overseas_country', v)} placeholder="Country" />
          </div>
        )}
        <PToggle on={draft.status === 'inactive'} onChange={(v) => set('status', v ? 'inactive' : 'active')}
          label="Inactive — hide from availability & selection" />
      </div>

      {/* Tucked away */}
      <div className="mt-3 pt-3 border-t border-pb-hairline flex flex-wrap gap-3.5 items-center">
        <span className="font-mono text-[10px] text-pb-faintest">
          PlayHQ ID: {draft.playhq_id ? `${String(draft.playhq_id).slice(0, 18)}…` : '—'}
        </span>
        <label className="inline-flex items-center gap-1.5 text-[11px] text-pb-faintest cursor-pointer">
          <input type="checkbox" checked={!draft.is_player} onChange={(e) => set('is_player', !e.target.checked)}
            className="accent-pb-faint" />
          Non-player (coach/scorer)
        </label>
      </div>
    </div>
  )
}

/* ── Profile panel ────────────────────────────────────────────────────────── */
function Profile({ profile, draft, setDraft, dirty, saved, onSave, canEdit, onEditAvail, canEditAvail }) {
  const set = (k, v) => setDraft((d) => ({ ...d, [k]: v }))
  const squad = profile.squad
  const handLabel = (BAT_HANDS.find((h) => h[0] === (draft.batting_hand || '')) || [])[1]
  const showBowlMeta = bowls(draft.bowling_action, draft.bowling_type)

  return (
    <div className="overflow-auto h-full">
      {/* Header */}
      <div className="px-5 py-[18px] border-b border-pb-hairline"
        style={{ background: 'linear-gradient(140deg, color-mix(in srgb, var(--pb-accent) 8%, transparent), transparent 55%)' }}>
        <div className="flex items-center gap-4">
          <Avatar player={{ ...profile, skill_positions: draft.skill_positions }} size={56} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h2 className="m-0 font-display font-extrabold text-2xl truncate">{profile.display_name || profile.name}</h2>
              {squad && <Tag tone="accent">{squad.name} squad</Tag>}
              {draft.is_overseas && <Tag tone="amber">Overseas{draft.overseas_country ? ` · ${draft.overseas_country}` : ''}</Tag>}
              {draft.status === 'inactive' && <Tag tone="faint">Inactive</Tag>}
            </div>
            <div className="flex items-center gap-2.5 mt-1.5 text-pb-dim text-[13px] flex-wrap">
              {draft.player_role && <><span>{draft.player_role}</span><span className="text-pb-faintest">·</span></>}
              {handLabel && <span>{handLabel}</span>}
              {showBowlMeta && <><span className="text-pb-faintest">·</span><span>{bowlingLabel(draft.bowling_action, draft.bowling_type)}</span></>}
              {draft.is_opening_batsman && (
                <span className="font-mono text-[9.5px] text-pb-accent bg-pb-accent/10 px-1.5 py-px rounded">OPENER</span>
              )}
            </div>
          </div>
          {canEdit && (
            <Btn variant="primary" sm icon={saved ? 'check' : undefined} disabled={!dirty} onClick={onSave}>
              {saved ? 'Saved' : 'Save changes'}
            </Btn>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2">
        <Snapshot snapshot={profile.snapshot} squad={squad} draft={draft}
          player={profile} onEditAvail={onEditAvail} canEditAvail={canEditAvail} />
        <Details draft={draft} set={set} teams={profile._teams || []} />
      </div>
    </div>
  )
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
function PlayerList({ players, statusOf, squadNameOf, selectedId, onSelect, onOpenProfile, canEdit, teams, onBulkSquad, onBulkInactive, onEditAvail }) {
  const [q, setQ] = useState('')
  const [role, setRole] = useState(null)
  const [showInactive, setShowInactive] = useState(false)
  const [years, setYears] = useState(0)        // 0 = any time
  const [sel, setSel] = useState(() => new Set())
  const [bulkSquad, setBulkSquad] = useState('')

  const list = useMemo(() => players.filter((p) => {
    if (!showInactive && p.status === 'inactive') return false
    if (q.trim() && !nameMatchesSearch(p.display_name || p.name, q)) return false
    if (role && p.player_role !== role) return false
    if (!playedWithinYears(p.last_played, years)) return false
    return true
  }), [players, showInactive, q, role, years])

  const toggleSel = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const clearSel = () => setSel(new Set())

  return (
    <div className="pb-card bg-pb-surface flex flex-col min-h-0 h-full overflow-hidden">
      <div className="px-3.5 py-3 border-b border-pb-hairline flex items-center gap-2.5 flex-wrap">
        <Search value={q} onChange={setQ} placeholder="Search players…" className="w-[200px]" />
        <div className="flex gap-1.5">
          {ROLE_CHIPS.map(([label, value]) => (
            <Chip key={value} label={label} active={role === value} onClick={() => setRole(role === value ? null : value)} />
          ))}
        </div>
        <Chip label="Show inactive" active={showInactive} onClick={() => setShowInactive((v) => !v)} />
        <RecencySelect value={years} onChange={setYears} />
        <span className="ml-auto font-mono text-[11px] text-pb-faint">{list.length} players</span>
      </div>

      <div className="overflow-auto flex-1">
        {list.length === 0
          ? <div className="px-4 py-8"><Empty>No players match these filters.</Empty></div>
          : list.map((p) => (
            <PlayerRow key={p.id} p={p} active={p.id === selectedId} selected={sel.has(p.id)}
              status={statusOf(p.id)} squadName={squadNameOf(p)}
              onSelect={() => onSelect(p.id)} onOpenProfile={() => onOpenProfile(p.id)} onToggleSel={() => toggleSel(p.id)}
              onEditAvail={onEditAvail} canEditAvail={!!onEditAvail} />
          ))}
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

/* ── Build the editable draft from a profile payload ─────────────────────── */
function draftFromProfile(p) {
  return {
    display_name_override: p.display_name_override || '',
    player_role: p.player_role || '',
    batting_hand: p.batting_hand || '',
    bowling_action: p.bowling_action || null,
    bowling_type: p.bowling_type || null,
    is_opening_batsman: !!p.is_opening_batsman,
    gender: p.gender || '',
    is_player: p.is_player !== false,
    status: p.status || 'active',
    email: p.email || '',
    phone: p.phone || '',
    squad_team_id: p.squad_team_id || null,
    is_overseas: !!p.is_overseas,
    overseas_country: p.overseas_country || '',
    skill_positions: p.skill_positions || [],
    playhq_id: p.playhq_id || null,
  }
}

// Only the fields the PATCH endpoint accepts, normalised (empty string → null
// for the optional text/select fields so they clear cleanly).
function patchFromDraft(d) {
  const norm = (v) => (v === '' ? null : v)
  return {
    display_name_override: norm(d.display_name_override),
    player_role: norm(d.player_role),
    batting_hand: norm(d.batting_hand),
    bowling_action: d.bowling_action || null,
    bowling_type: d.bowling_type || null,
    is_opening_batsman: !!d.is_opening_batsman,
    gender: norm(d.gender),
    is_player: d.is_player !== false,
    status: d.status || 'active',
    email: norm(d.email),
    phone: norm(d.phone),
    squad_team_id: d.squad_team_id || null,
    is_overseas: !!d.is_overseas,
    overseas_country: norm(d.overseas_country),
  }
}

export default function BetterSelectPlayers() {
  const { hasCapability } = useAuth()
  const toast = useToast()
  const canEdit = hasCapability(CAP.MANAGE_PLAYERS)

  const [players, setPlayers] = useState(null)   // roster (adminListPlayers)
  const [teams, setTeams] = useState([])         // bsListTeams
  const [availability, setAvailability] = useState({}) // playerId → {date: {status}}
  const [firstDate, setFirstDate] = useState(null)     // next upcoming date

  const [selId, setSelId] = useState(null)
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
        if (rows.length && selId == null) setSelId(rows[0].id)
      })
      .catch((e) => { toast.error(e.message); setPlayers([]) })
  }, [toast, selId])

  useEffect(() => { loadRoster() }, [])  // eslint-disable-line react-hooks/exhaustive-deps

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
      <div className="grid gap-4 h-[calc(100vh-140px)]" style={{ gridTemplateColumns: 'minmax(420px, 1fr) 1.35fr' }}>
        <PlayerList
          players={players} statusOf={statusOf} squadNameOf={squadNameOf}
          selectedId={selId} onSelect={setSelId} onOpenProfile={setSelId}
          canEdit={canEdit} teams={teams} onBulkSquad={onBulkSquad} onBulkInactive={onBulkInactive}
          onEditAvail={canEdit ? (p) => openAvail(p, null) : undefined} />
        <div className="pb-card bg-pb-surface min-h-0 overflow-hidden">
          {!selId
            ? <div className="p-6"><Empty>Select a player</Empty></div>
            : (!profileForView || !draft)
              ? <PbSpinner message="Loading profile…" />
              : <Profile profile={profileForView} draft={draft} setDraft={setDraft}
                  dirty={dirty} saved={savedTick} onSave={onSave} canEdit={canEdit}
                  onEditAvail={openAvail} canEditAvail={canEdit} />}
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
