import { useState, useEffect } from 'react'

// Shared opposition-player profile — the closest thing to our own player-trends
// deep-dive that the data supports for an opponent: current-season batting &
// bowling, recent form, dismissal patterns and their full record vs us. Built
// from the live dossier (we don't store opponents' multi-season history). Plus a
// manual scouting tag (handedness, bowler type, role, notes) the club can record.
const num = (v, dash = '—') => (v === null || v === undefined ? dash : v)
const fmt2 = (v) => (v === null || v === undefined || Number.isNaN(Number(v))) ? '—' : Number(v).toFixed(2)

// Controlled vocab — mirrors BetterSelect's player attributes so the choices
// match our own players' editor.
const BAT_HAND_OPTS = [['', '—'], ['RIGHT', 'Right-hand bat'], ['LEFT', 'Left-hand bat']]
const BOWL_ACTION_OPTS = [['', '—'], ['RIGHT_ARM', 'Right-arm'], ['LEFT_ARM', 'Left-arm']]
const BOWL_TYPE_OPTS = [['', '—'], ['FAST', 'Fast'], ['FAST_MEDIUM', 'Fast-medium'], ['MEDIUM', 'Medium'], ['MEDIUM_FAST', 'Medium-fast'], ['FINGER_SPIN', 'Finger spin'], ['WRIST_SPIN', 'Wrist spin']]
const ROLE_OPTS = [['', '—'], ['BAT', 'Batter'], ['BOWL', 'Bowler'], ['ALL', 'All-rounder'], ['WK', 'Wicketkeeper']]

const handLabel = (h) => (h === 'LEFT' ? 'LHB' : h === 'RIGHT' ? 'RHB' : null)
function bowlingLabel(action, type) {
  if (!type) return action === 'LEFT_ARM' ? 'Left-arm' : action === 'RIGHT_ARM' ? 'Right-arm' : null
  const left = action === 'LEFT_ARM'
  const arm = left ? 'Left-arm' : action === 'RIGHT_ARM' ? 'Right-arm' : ''
  if (type === 'FINGER_SPIN') return left ? 'Left-arm orthodox' : 'Off spin'
  if (type === 'WRIST_SPIN') return left ? 'Left-arm wrist spin' : 'Leg spin'
  const pace = { FAST: 'fast', FAST_MEDIUM: 'fast-medium', MEDIUM: 'medium', MEDIUM_FAST: 'medium-fast' }[type] || ''
  return `${arm} ${pace}`.trim() || null
}
const ROLE_LABEL = { BAT: 'Batter', BOWL: 'Bowler', ALL: 'All-rounder', WK: 'Keeper' }

export function MiniStat({ label, value }) {
  return (
    <div className="text-center px-2 py-1">
      <div className="font-display font-bold text-lg pb-num leading-none">{value}</div>
      <div className="text-pb-faintest text-[10px] uppercase tracking-wide2 mt-0.5">{label}</div>
    </div>
  )
}

// Merge a dossier's batting + bowling lists into a per-player index.
export function buildOppPlayerIndex(dossier) {
  const m = new Map()
  for (const b of dossier?.batting || []) m.set(b.player_id, { name: b.name, bat: b, bowl: null })
  for (const w of dossier?.bowling || []) {
    const e = m.get(w.player_id) || { name: w.name, bat: null, bowl: null }
    e.bowl = w; m.set(w.player_id, e)
  }
  return m
}

// Read-only coloured badges from a saved tag.
function TagBadges({ tag }) {
  if (!tag) return null
  const bowl = bowlingLabel(tag.bowling_action, tag.bowling_type)
  const badges = []
  if (handLabel(tag.batting_hand)) badges.push(handLabel(tag.batting_hand))
  if (bowl) badges.push(bowl)
  if (tag.player_role && ROLE_LABEL[tag.player_role]) badges.push(ROLE_LABEL[tag.player_role])
  if (tag.is_wicket_keeper && tag.player_role !== 'WK') badges.push('Keeper')
  return (
    <>
      {badges.map((b, i) => (
        <span key={i} className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded" style={{ background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)', color: 'var(--pb-accent)' }}>{b}</span>
      ))}
      {tag.is_danger && <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded" style={{ background: 'color-mix(in srgb, var(--pb-red) 16%, transparent)', color: 'var(--pb-red)' }}>Danger</span>}
    </>
  )
}

const selCls = "bg-pb-surface2 text-sm rounded-lg border px-2 h-[34px] text-pb-text border-pb-hairline focus:outline-none focus:border-pb-accent w-full"

// Editable scouting tag — handedness, bowler type, role, danger flag and notes.
function ScoutingTags({ playerId, name, tag, onSave }) {
  const seed = () => ({
    batting_hand: tag?.batting_hand || '',
    bowling_action: tag?.bowling_action || '',
    bowling_type: tag?.bowling_type || '',
    player_role: tag?.player_role || '',
    is_wicket_keeper: !!tag?.is_wicket_keeper,
    is_danger: !!tag?.is_danger,
    notes: tag?.notes || '',
  })
  const [open, setOpen] = useState(false)
  const [f, setF] = useState(seed)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  // Re-seed when switching players (or when a fresh tag arrives).
  useEffect(() => { setF(seed()); setSaved(false); setOpen(false) }, [playerId, tag])  // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k, v) => { setF(s => ({ ...s, [k]: v })); setSaved(false) }
  const save = async () => {
    setSaving(true)
    try { await onSave(playerId, { ...f, player_name: name }); setSaved(true); setOpen(false) }
    finally { setSaving(false) }
  }
  const Field = ({ label, k, opts }) => (
    <label className="block">
      <span className="text-pb-faint text-[11px] uppercase tracking-wide2">{label}</span>
      <select value={f[k]} onChange={e => set(k, e.target.value)} className={selCls + ' mt-1'}>
        {opts.map(([v, l]) => <option key={v} value={v} className="bg-pb-surface">{l}</option>)}
      </select>
    </label>
  )
  return (
    <div className="mt-3 pt-3 border-t pb-hairline">
      <div className="flex items-center justify-between gap-2">
        <div className="text-pb-faint text-[11px] uppercase tracking-wide2">Scouting tags</div>
        <button onClick={() => setOpen(o => !o)} className="text-[12px] text-pb-accent hover:underline">{open ? 'Close' : (tag ? 'Edit' : 'Add detail')}</button>
      </div>
      {!open && (
        <div className="mt-1.5 text-[12px] text-pb-faint">
          {tag ? (tag.notes || 'Tagged — click Edit to update.') : 'No scouting notes yet — add handedness, bowler type and intel.'}
        </div>
      )}
      {open && (
        <div className="mt-2 space-y-2.5">
          <div className="grid grid-cols-2 gap-2.5">
            <Field label="Bats" k="batting_hand" opts={BAT_HAND_OPTS} />
            <Field label="Role" k="player_role" opts={ROLE_OPTS} />
            <Field label="Bowling arm" k="bowling_action" opts={BOWL_ACTION_OPTS} />
            <Field label="Bowling type" k="bowling_type" opts={BOWL_TYPE_OPTS} />
          </div>
          <div className="flex flex-wrap gap-4">
            <label className="flex items-center gap-1.5 text-sm"><input type="checkbox" checked={f.is_wicket_keeper} onChange={e => set('is_wicket_keeper', e.target.checked)} /> Wicketkeeper</label>
            <label className="flex items-center gap-1.5 text-sm"><input type="checkbox" checked={f.is_danger} onChange={e => set('is_danger', e.target.checked)} /> Danger man</label>
          </div>
          <label className="block">
            <span className="text-pb-faint text-[11px] uppercase tracking-wide2">Notes</span>
            <textarea value={f.notes} onChange={e => set('notes', e.target.value)} rows={3} placeholder="e.g. nervous starter, targets leg side, weak vs spin early…"
              className="bg-pb-surface2 text-sm rounded-lg border px-2.5 py-1.5 text-pb-text border-pb-hairline focus:outline-none focus:border-pb-accent w-full mt-1 resize-y" />
          </label>
          <div className="flex items-center gap-3">
            <button onClick={save} disabled={saving} className="px-3 h-[34px] rounded-lg text-sm font-medium text-white disabled:opacity-60" style={{ background: 'var(--pb-accent)' }}>{saving ? 'Saving…' : 'Save'}</button>
            {saved && <span className="text-[12px]" style={{ color: 'var(--pb-brand)' }}>Saved.</span>}
          </div>
        </div>
      )}
    </div>
  )
}

export function OppPlayerDetail({ entry, enriched, opponentName, playerId, tag, onSaveTag }) {
  if (!entry) return null
  const { bat, bowl } = entry
  const formColor = bat?.form === 'hot' ? 'var(--pb-red)' : bat?.form === 'cold' ? 'var(--pb-faint)' : 'var(--pb-accent)'
  const dism = bat?.dismissals && Object.entries(bat.dismissals).sort((a, b) => b[1] - a[1])
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className="font-display font-bold text-xl">{entry.name}</span>
        {opponentName && <span className="text-pb-faint text-sm">· {opponentName}</span>}
        <TagBadges tag={tag} />
        {bat?.form && <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded" style={{ background: `color-mix(in srgb, ${formColor} 16%, transparent)`, color: formColor }}>{bat.form}</span>}
        {enriched?.alert?.level === 'danger' && <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded" style={{ background: 'color-mix(in srgb, var(--pb-red) 16%, transparent)', color: 'var(--pb-red)' }}>Danger</span>}
        {enriched?.alert?.level === 'caution' && <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded" style={{ background: 'color-mix(in srgb, var(--pb-amber) 16%, transparent)', color: 'var(--pb-amber)' }}>Paper tiger?</span>}
      </div>

      {enriched?.key_note && <div className="text-sm mb-3" style={{ color: 'var(--pb-accent)' }}>{enriched.key_note}</div>}
      {enriched?.plan && <div className="text-[13px] mb-3 text-pb-faint">Plan: {enriched.plan}</div>}

      {bat && bat.innings > 0 && (
        <div className="mb-3">
          <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-1">Batting · this season</div>
          <div className="flex flex-wrap items-center gap-1">
            <MiniStat label="Inns" value={num(bat.innings)} />
            <MiniStat label="Runs" value={num(bat.runs)} />
            <MiniStat label="Avg" value={fmt2(bat.average)} />
            <MiniStat label="SR" value={fmt2(bat.strike_rate)} />
            <MiniStat label="HS" value={num(bat.high_score)} />
            <MiniStat label="50/100" value={`${num(bat.fifties, 0)}/${num(bat.hundreds, 0)}`} />
            {bat.boundary_pct != null && <MiniStat label="Bndry%" value={`${bat.boundary_pct}%`} />}
          </div>
          {bat.recent_scores?.length > 0 && <div className="text-pb-faintest text-[12px] mt-1">Recent: <span className="pb-num">{bat.recent_scores.join(', ')}</span></div>}
          {dism?.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {dism.map(([k, v]) => <span key={k} className="text-[11px] px-1.5 py-0.5 rounded-full capitalize" style={{ background: 'var(--pb-surface2)' }}>{k} <span className="pb-num text-pb-faint">{v}</span></span>)}
            </div>
          )}
        </div>
      )}

      {bat?.vs_us && (
        <div className="mb-3 rounded-lg p-2.5" style={{ background: 'color-mix(in srgb, var(--pb-red) 8%, transparent)' }}>
          <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-1">Their batting vs us</div>
          <div className="text-sm pb-num">{bat.vs_us.innings} inns · {bat.vs_us.runs} runs @ <b>{fmt2(bat.vs_us.average)}</b> · HS {num(bat.vs_us.high_score)}{bat.vs_us.fifties ? ` · ${bat.vs_us.fifties}×50` : ''}{bat.vs_us.hundreds ? ` · ${bat.vs_us.hundreds}×100` : ''}</div>
        </div>
      )}

      {bowl && bowl.wickets > 0 && (
        <div className="mb-3">
          <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-1">Bowling · this season</div>
          <div className="flex flex-wrap items-center gap-1">
            <MiniStat label="Overs" value={num(bowl.overs)} />
            <MiniStat label="Wkts" value={num(bowl.wickets)} />
            <MiniStat label="Avg" value={fmt2(bowl.average)} />
            <MiniStat label="Econ" value={fmt2(bowl.economy)} />
            <MiniStat label="Best" value={num(bowl.best)} />
            {bowl.five_fors ? <MiniStat label="5wi" value={num(bowl.five_fors)} /> : null}
          </div>
          {bowl.recent_wickets?.length > 0 && <div className="text-pb-faintest text-[12px] mt-1">Recent wkts: <span className="pb-num">{bowl.recent_wickets.join(', ')}</span></div>}
        </div>
      )}

      {bowl?.vs_us && (
        <div className="rounded-lg p-2.5" style={{ background: 'color-mix(in srgb, var(--pb-accent) 8%, transparent)' }}>
          <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-1">Their bowling vs us</div>
          <div className="text-sm pb-num">{bowl.vs_us.wickets} wkts @ <b>{fmt2(bowl.vs_us.average)}</b> · econ {fmt2(bowl.vs_us.economy)}{bowl.vs_us.best ? ` · best ${bowl.vs_us.best}` : ''}</div>
        </div>
      )}

      {!bat?.innings && !bowl?.wickets && (
        <div className="text-pb-faintest text-sm">No current-season scorecard data for this player yet.</div>
      )}

      {playerId && onSaveTag && <ScoutingTags playerId={playerId} name={entry.name} tag={tag} onSave={onSaveTag} />}
    </div>
  )
}
