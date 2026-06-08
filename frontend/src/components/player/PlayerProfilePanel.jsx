// Canonical player profile panel — the enriched master-detail profile first
// built for BetterSelect, lifted here so every admin surface (BetterSelect
// Players + Admin → Players) renders the *same* profile. It pairs a selection
// snapshot (availability / recent form / squad / last picked) with the full set
// of inline-editable management fields, and is a superset of the old cramped
// edit modal: display-name override, editable PlayHQ ID and photo management
// all live here too.
//
// Atoms come from the BetterSelect kit (Avatar/Tag/Btn/Dot); the attribute
// option-sets + labels come from lib/playerAttributes so the public profile
// shares the same vocabulary.
import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { validateImageFile } from '../../lib/validation'
import ImageEditorModal from '../ImageEditorModal'
import { Avatar, Tag, Btn, Dot, Icon } from '../../pages/admin/betterselect/ui'
import {
  ROLE_OPTS, ROLE_TO_SKILLS, BAT_HANDS, GENDER_OPTS, BOWLING_OPTS,
  bowlingLabel, bowlingFromLabel, bowls, normalizeGender,
} from '../../lib/playerAttributes'
import { splitDisplayName, joinDisplayName } from '../../lib/nameFormat'

const ROLE_LABEL = { '': '—' }

/* ── Inline field controls (match BetterSelect look via pb-* tokens) ──────── */
function Field({ label, half, children }) {
  return (
    <div className={half ? 'flex-1 min-w-0 basis-full sm:basis-[calc(50%-6px)]' : 'flex-1 min-w-0 basis-full'}>
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

/* ── Photo management (admin only) ────────────────────────────────────────── */
function PhotoRow({ playerId, photoUrl, onPhotoChange }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [editorSource, setEditorSource] = useState(null)

  const upload = async (file) => {
    setEditorSource(null)
    setBusy(true); setErr('')
    try {
      const r = await api.adminUploadPlayerPhoto(playerId, file)
      onPhotoChange?.(r.photo_url)
    } catch (e) { setErr(e.message || 'Upload failed') }
    finally { setBusy(false) }
  }
  const remove = async () => {
    setBusy(true); setErr('')
    try { await api.adminDeletePlayerPhoto(playerId); onPhotoChange?.(null) }
    catch (e) { setErr(e.message || 'Remove failed') }
    finally { setBusy(false) }
  }

  return (
    <div className="mt-3 pt-3 border-t border-pb-hairline">
      <div className="block text-[11.5px] text-pb-faint mb-[7px]">Photo</div>
      <div className="flex items-center gap-3 flex-wrap">
        {photoUrl
          ? <img src={photoUrl} alt="" className="w-11 h-11 rounded-lg object-cover border border-pb-hairline2" />
          : <span className="w-11 h-11 rounded-lg bg-pb-surface2 border border-pb-hairline2 flex items-center justify-center text-pb-faint"><Icon name="player" size={20} /></span>}
        <div className="flex items-center gap-2 flex-wrap">
          <label className={`font-mono text-[10px] px-2.5 py-1.5 rounded-lg border border-pb-hairline2 text-pb-dim hover:text-pb-text cursor-pointer transition ${busy ? 'opacity-50 pointer-events-none' : ''}`}>
            {busy ? '…' : (photoUrl ? 'Replace' : 'Upload photo')}
            <input type="file" accept=".jpg,.jpeg,.png,.webp,.gif" className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                e.target.value = ''
                if (!f) return
                const v = validateImageFile(f)
                if (v) { setErr(v); return }
                setEditorSource(f)
              }} />
          </label>
          {photoUrl && (
            <>
              <button type="button" onClick={() => setEditorSource(photoUrl)} disabled={busy}
                className="font-mono text-[10px] px-2.5 py-1.5 rounded-lg border border-pb-hairline2 text-pb-dim hover:text-pb-text transition disabled:opacity-50">Edit</button>
              <button type="button" onClick={remove} disabled={busy}
                className="font-mono text-[10px] px-2.5 py-1.5 rounded-lg border border-pb-hairline2 text-pb-faint hover:text-pb-red transition disabled:opacity-50">Remove</button>
            </>
          )}
        </div>
      </div>
      {err && <p className="font-mono text-[10px] text-pb-red mt-1.5">{err}</p>}
      <ImageEditorModal
        open={!!editorSource}
        source={editorSource}
        title="Edit Player Photo"
        aspect={1}
        outputType="image/png"
        outputName={`player-${playerId}.png`}
        onCancel={() => setEditorSource(null)}
        onApply={upload}
      />
    </div>
  )
}

/* ── Net attendance (BetterSelect → Net Manager) ──────────────────────────────
 * A quiet line under the snapshot showing how often this player turns up to
 * nets. Self-contained fetch; renders nothing until there's something to show
 * (so clubs not running the Net Manager never see it), and swallows the 402 a
 * non-BetterSelect club would get. */
function NetAttendanceStat({ playerId }) {
  const [data, setData] = useState(null)
  useEffect(() => {
    let alive = true
    api.nmPlayerAttendance(playerId).then((r) => { if (alive) setData(r) }).catch(() => {})
    return () => { alive = false }
  }, [playerId])
  if (!data || !data.attended) return null
  return (
    <div className="mt-[18px] pt-[18px] border-t border-pb-hairline">
      <div className="text-xs text-pb-faint mb-2">Net attendance</div>
      <div className="flex items-center gap-4">
        <span><b className="pb-num font-display font-bold text-base text-pb-text">{data.attended}</b> <span className="text-[11.5px] text-pb-faintest">session{data.attended === 1 ? '' : 's'}</span></span>
        <span><b className="pb-num font-display font-bold text-base text-pb-accent">{data.batted}</b> <span className="text-[11.5px] text-pb-faintest">batted</span></span>
        {data.last_attended && <span className="text-[11.5px] text-pb-faintest ml-auto">last {new Date(data.last_attended + 'T00:00:00').toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}</span>}
      </div>
    </div>
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
    <div className="px-4 sm:px-5 py-[18px] border-b lg:border-b-0 lg:border-r border-pb-hairline">
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
            <span className="text-[11.5px] text-pb-faintest">
              this season{(snap.season_catches_wk ?? 0) > 0 ? ` · ${snap.season_catches_wk} wk` : ''}
            </span>
          </div>
        </div>
      </div>

      <div>
        <div className="text-xs text-pb-faint mb-1">Last picked</div>
        <div className={`text-[13.5px] ${lastPicked ? 'text-pb-text' : 'text-pb-faint'}`}>{lastPicked || 'Not recently'}</div>
      </div>

      {player?.id && <NetAttendanceStat playerId={player.id} />}
    </div>
  )
}

/* ── Details (right column, right half) — inline editable ─────────────────── */
function Details({ draft, set, teams, canEdit, playerId, playerName, photoUrl, onPhotoChange }) {
  const bowlingLabelVal = bowlingLabel(draft.bowling_action, draft.bowling_type)
  return (
    <div className="px-5 py-[18px]">
      <div className="font-mono text-[10px] uppercase tracking-wide3 text-pb-faint mb-3.5">Details</div>
      <div className="flex flex-wrap gap-3">
        <Field label="Display name (blank = synced)">
          <div className="grid grid-cols-2 gap-2">
            <PInput value={draft.display_first} onChange={(v) => set('display_first', v)}
              placeholder="First" />
            <PInput value={draft.display_last} onChange={(v) => set('display_last', v)}
              placeholder="Last" />
          </div>
        </Field>
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
          <PSelect value={normalizeGender(draft.gender)} onChange={(v) => set('gender', v || null)} options={GENDER_OPTS} />
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

      {canEdit && playerId && (
        <PhotoRow playerId={playerId} photoUrl={photoUrl} onPhotoChange={onPhotoChange} />
      )}

      {/* PlayHQ ID + non-player flag */}
      <div className="mt-3 pt-3 border-t border-pb-hairline flex flex-wrap gap-x-3.5 gap-y-2 items-end">
        <Field label="PlayHQ ID" half>
          <PInput value={draft.playhq_id} onChange={(v) => set('playhq_id', v)} placeholder="—" />
        </Field>
        <label className="inline-flex items-center gap-1.5 text-[11px] text-pb-faintest cursor-pointer pb-2.5">
          <input type="checkbox" checked={!draft.is_player} onChange={(e) => set('is_player', !e.target.checked)}
            className="accent-pb-faint" />
          Non-player (coach/scorer)
        </label>
      </div>
    </div>
  )
}

/* ── Profile panel ────────────────────────────────────────────────────────── */
export function Profile({ profile, draft, setDraft, dirty, saved, onSave, canEdit, onEditAvail, canEditAvail, onClose, onPhotoChange }) {
  const set = (k, v) => setDraft((d) => ({ ...d, [k]: v }))
  const squad = profile.squad
  const handLabel = (BAT_HANDS.find((h) => h[0] === (draft.batting_hand || '')) || [])[1]
  const showBowlMeta = bowls(draft.bowling_action, draft.bowling_type)
  const playerName = profile.display_name || profile.name

  return (
    <div className="overflow-auto h-full">
      {/* Header */}
      <div className="px-5 py-[18px] border-b border-pb-hairline"
        style={{ background: 'linear-gradient(140deg, color-mix(in srgb, var(--pb-accent) 8%, transparent), transparent 55%)' }}>
        <div className="flex items-center gap-4">
          <Avatar player={{ ...profile, skill_positions: draft.skill_positions }} size={56} noLink />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h2 className="m-0 font-display font-extrabold text-2xl truncate">{playerName}</h2>
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
            <Link to={`/players/${profile.id}`} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-1 mt-2 font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-accent transition">
              View public profile <Icon name="arrow" size={12} />
            </Link>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {canEdit && (
              <Btn variant="primary" sm icon={saved ? 'check' : undefined} disabled={!dirty} onClick={onSave}>
                {saved ? 'Saved' : 'Save changes'}
              </Btn>
            )}
            {onClose && (
              <button type="button" onClick={onClose} aria-label="Close"
                className="text-pb-faint hover:text-pb-text p-1.5 rounded-lg hover:bg-pb-surface2 transition"><Icon name="close" size={18} /></button>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2">
        <Snapshot snapshot={profile.snapshot} squad={squad} draft={draft}
          player={profile} onEditAvail={onEditAvail} canEditAvail={canEditAvail} />
        <Details draft={draft} set={set} teams={profile._teams || []}
          canEdit={canEdit} playerId={profile.id} playerName={profile.name}
          photoUrl={profile.photo_url} onPhotoChange={onPhotoChange} />
      </div>
    </div>
  )
}

/* ── Build the editable draft from a profile payload ─────────────────────── */
export function draftFromProfile(p) {
  // Edit the override as separate first/last fields so it can be stored
  // canonically as "Last, First" (sorts by surname, respects the club name
  // format). Legacy free-text overrides are best-effort split for editing.
  const dn = splitDisplayName(p.display_name_override)
  return {
    display_first: dn.first,
    display_last: dn.last,
    player_role: p.player_role || '',
    batting_hand: p.batting_hand || '',
    bowling_action: p.bowling_action || null,
    bowling_type: p.bowling_type || null,
    is_opening_batsman: !!p.is_opening_batsman,
    gender: normalizeGender(p.gender),
    is_player: p.is_player !== false,
    status: p.status || 'active',
    email: p.email || '',
    phone: p.phone || '',
    squad_team_id: p.squad_team_id || null,
    is_overseas: !!p.is_overseas,
    overseas_country: p.overseas_country || '',
    skill_positions: p.skill_positions || [],
    playhq_id: p.playhq_id || '',
  }
}

// Only the fields the PATCH endpoint accepts, normalised (empty string → null
// for the optional text/select fields so they clear cleanly).
export function patchFromDraft(d) {
  const norm = (v) => (v === '' ? null : v)
  return {
    display_name_override: norm(joinDisplayName(d.display_first, d.display_last)),
    playhq_id: norm(d.playhq_id),
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
    // Role is canonical — derive the skill codes the filters + chips read from
    // it (fall back to whatever was on the player when no role is set).
    skill_positions: ROLE_TO_SKILLS[d.player_role] || d.skill_positions || [],
  }
}
