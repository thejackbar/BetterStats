/* BetterIQ — Opposition player profile (v3 design: tabbed deep-dive).
 *
 * The closest thing to our own player deep-dive that the data supports for an
 * opponent, organised into tabs so each discipline can go deep:
 *   • Overview — radar, the auto scouting read, career snapshot, record vs us
 *   • Batting  — current form, scoring zones, dismissal patterns, conversion,
 *                reliability (floor/ceiling), style (accumulator vs hitter),
 *                by-position, season history + the manual batting scouting card
 *   • Bowling  — current form, how he takes wickets, wicket quality, season
 *                history, recent spells + the manual bowling scouting card
 *   • Fielding — catches (outfield / keeper split), stumpings, run-outs, by season
 *   • Notes    — editable scouting tags (hand / type / role / keeper / danger)
 *
 * Built from three layers: the live current-season dossier (entry.bat/bowl/vs_us),
 * CA season aggregates (career) and a scorecard deep pass (deep) — the last two
 * polled here and shared across tabs. On top of the held data the club records
 * MANUAL intel that travels with the player (scoring zones, batting/bowling
 * scouting cards, tags). The radar is built client-side from the dossier squad.
 *
 * Public interface preserved for OppositionScout.jsx / PlayerHub.jsx:
 *   - buildOppPlayerIndex(dossier) → Map<player_id, {name, bat, bowl}>
 *   - <OppPlayerDetail entry enriched opponentName playerId tag onSaveTag
 *       dossierBatting dossierBowling orgGuid />
 */
import { useState, useEffect, useMemo } from 'react'
import { api } from '../../../lib/api'
import {
  Sparkline, Card, Stat, Note, Tag, Btn, Segmented, Initials, StackedBar, Bar, a2,
  LoadingBar, fmtCount, fmtOvers, fmtPct, oversToBalls, Tabs,
} from './ui'
import { Radar, WagonWheel, ZONE_LABELS, buildRadar, AreaChart } from './viz'
import ScoutingCard from './ScoutingCard'

const num = (v, dash = '—') => (v === null || v === undefined ? dash : v)

/* Controlled vocab — mirrors our own players' attributes so the choices match. */
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
const ROLE_LABEL = { BAT: 'Batter', BOWL: 'Bowler', ALL: 'All-rounder', WK: 'Wicketkeeper' }
const sparkVals = (scores) => (scores || []).map(s => parseInt(String(s).replace(/[*+]/g, ''), 10) || 0)

/* Merge a dossier's batting + bowling lists into a per-player index. */
export function buildOppPlayerIndex(dossier) {
  const m = new Map()
  for (const b of dossier?.batting || []) m.set(b.player_id, { name: b.name, bat: b, bowl: null })
  for (const w of dossier?.bowling || []) {
    const e = m.get(w.player_id) || { name: w.name, bat: null, bowl: null }
    e.bowl = w; m.set(w.player_id, e)
  }
  return m
}

/* Read-only coloured badges from a saved tag. */
function TagBadges({ tag }) {
  if (!tag) return null
  const bowl = bowlingLabel(tag.bowling_action, tag.bowling_type)
  const badges = []
  if (handLabel(tag.batting_hand)) badges.push(['accent', handLabel(tag.batting_hand)])
  if (bowl) badges.push(['accent', bowl])
  if (tag.player_role && ROLE_LABEL[tag.player_role]) badges.push(['accent', ROLE_LABEL[tag.player_role]])
  if (tag.is_wicket_keeper && tag.player_role !== 'WK') badges.push(['accent', 'Keeper'])
  if (tag.is_danger) badges.push(['red', 'Danger'])
  return <>{badges.map(([tone, b], i) => <Tag key={i} tone={tone}>{b}</Tag>)}</>
}

/* ── Radar (built from the dossier squad — opponents have no /radar endpoint) ─
   Batting + bowling radars are built independently so a bowler isn't forced into
   a batting radar just because he's batted once down the order. The card shows a
   Bat/Bowl toggle when both exist, defaulting to the player's stronger side. */
function batRadarFor(bat, batPeers) {
  if (!(bat && bat.innings > 0 && (batPeers || []).length >= 2)) return null
  return buildRadar(batPeers, [
    { label: 'Volume', value: p => p.runs },
    { label: 'Average', value: p => p.average },
    { label: 'Strike rate', value: p => p.strike_rate },
    { label: 'Conversion', value: p => ((p.fifties || 0) + (p.hundreds || 0)) / Math.max(p.innings || 1, 1) },
    { label: 'Big score', value: p => p.high_score },
    { label: 'vs us', value: p => p.vs_us?.runs || 0 },
  ], bat)
}
function bowlRadarFor(bowl, bowlPeers) {
  if (!(bowl && bowl.wickets > 0 && (bowlPeers || []).length >= 2)) return null
  return buildRadar(bowlPeers, [
    { label: 'Wickets', value: p => p.wickets },
    { label: 'Economy', value: p => p.economy, lower: true },
    { label: 'Average', value: p => p.average, lower: true },
    { label: 'Strike rate', value: p => (p.overs ? oversToBalls(p.overs) / Math.max(p.wickets || 1, 1) : 0), lower: true },
    { label: 'Overs', value: p => p.overs },
    { label: 'vs us', value: p => p.vs_us?.wickets || 0 },
  ], bowl)
}

function OppRadarCard({ entry, batPeers, bowlPeers, prefer }) {
  const bat = useMemo(() => batRadarFor(entry.bat, batPeers), [entry, batPeers])
  const bowl = useMemo(() => bowlRadarFor(entry.bowl, bowlPeers), [entry, bowlPeers])
  const [side, setSide] = useState(prefer === 'bowl' && bowl ? 'bowl' : bat ? 'bat' : 'bowl')
  useEffect(() => { setSide(prefer === 'bowl' && bowl ? 'bowl' : bat ? 'bat' : 'bowl') }, [entry])  // eslint-disable-line react-hooks/exhaustive-deps
  if (!bat && !bowl) return null
  const r = side === 'bowl' && bowl ? bowl : bat || bowl
  const showBowl = side === 'bowl' && bowl
  return (
    <Card eyebrow="profile vs their squad" title="Player radar"
      right={bat && bowl ? <Segmented sm value={side} onChange={setSide} options={[{ value: 'bat', label: 'Bat' }, { value: 'bowl', label: 'Bowl' }]} /> : null}>
      <div className="flex justify-center">
        <Radar key={side} axes={r.axes} values={r.values} baseline={r.baseline} size={248} color={showBowl ? 'var(--pb-accent)' : 'var(--pb-red)'} />
      </div>
      <Note>Each axis normalised 0–100 against this club's squad ({showBowl ? 'bowlers' : 'batters'}; dashed ring = squad average). Bowling axes are inverted so the outer edge is always stronger.</Note>
    </Card>
  )
}

/* ── Scoring-zones wagon wheel + scout editor (a batting feature) ─────────────
   Hand sets the wheel orientation. Free-text notes live in the Notes tab, so this
   editor only writes scoring_zones + batting_hand (the present-aware backend
   upsert leaves the other tag fields, incl. notes, untouched). */
function ZonesEditor({ playerId, name, tag, battingHand, onSave }) {
  const seedZones = () => {
    const z = tag?.scoring_zones
    return Array.from({ length: 8 }, (_, i) => (Array.isArray(z) && z[i] != null ? Number(z[i]) : ''))
  }
  const [open, setOpen] = useState(false)
  const [zones, setZones] = useState(seedZones)
  const [hand, setHand] = useState(tag?.batting_hand || battingHand || '')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  // Re-seed when switching players or when a fresh tag arrives.
  useEffect(() => {
    setZones(seedZones()); setHand(tag?.batting_hand || battingHand || '')
    setSaved(false); setOpen(false)
  }, [playerId, tag])  // eslint-disable-line react-hooks/exhaustive-deps

  const setZone = (i, v) => {
    const n = v === '' ? '' : Math.max(0, Math.min(100, Number(v)))
    setZones(z => z.map((x, idx) => (idx === i ? n : x))); setSaved(false)
  }
  const save = async () => {
    setSaving(true)
    try {
      const arr = zones.map(v => (v === '' || Number.isNaN(Number(v)) ? 0 : Number(v)))
      await onSave(playerId, { scoring_zones: arr, batting_hand: hand || null, player_name: name })
      setSaved(true); setOpen(false)
    } finally { setSaving(false) }
  }

  const tagZones = Array.isArray(tag?.scoring_zones) ? tag.scoring_zones : null
  const hasZones = tagZones && tagZones.some(v => Number(v) > 0)
  const wheelHand = (hand || tag?.batting_hand) === 'LEFT' ? 'LH' : 'RH'

  return (
    <Card eyebrow="where he scores · scout-entered" title="Scoring zones"
      right={<Btn variant={open ? 'ghost' : 'soft'} sm icon={open ? undefined : 'edit'} onClick={() => setOpen(o => !o)}>{open ? 'Close' : (hasZones ? 'Edit' : 'Add zones')}</Btn>}>
      {hasZones && !open && (
        <div className="flex justify-center">
          <WagonWheel sectors={tagZones.map(v => Number(v) || 0)} hand={wheelHand} color="var(--pb-red)" />
        </div>
      )}
      {!hasZones && !open && (
        <div className="text-pb-faint text-[13px]">No scoring zones recorded yet. Tap <b>Add zones</b> to plot where this batter scores (CA gives us no shot-direction data, so this is scout intel).</div>
      )}

      {open && (
        <div className="grid gap-5 lg:grid-cols-[230px_1fr] items-start">
          {/* Live preview */}
          <div className="flex justify-center">
            <WagonWheel sectors={zones.map(v => Number(v) || 0)} hand={wheelHand} color="var(--pb-red)" />
          </div>
          {/* 8 zone inputs + hand */}
          <div className="space-y-3">
            <div>
              <div className="iq-eyebrow mb-2">% of runs by area (batter's view)</div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                {ZONE_LABELS.map((lab, i) => (
                  <label key={lab} className="block">
                    <span className="iq-mono uppercase text-pb-faint block mb-1" style={{ fontSize: 9, letterSpacing: '0.08em' }}>{lab}</span>
                    <input type="number" min={0} max={100} value={zones[i]} onChange={e => setZone(i, e.target.value)}
                      className="w-full px-2 h-9 iq-num outline-none"
                      style={{ background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)', borderRadius: 9, color: 'var(--pb-text)', fontSize: 14 }} />
                  </label>
                ))}
              </div>
            </div>
            <label className="block max-w-[220px]">
              <span className="iq-eyebrow block mb-1.5">Batting hand</span>
              <select value={hand} onChange={e => { setHand(e.target.value); setSaved(false) }}
                className="w-full px-2 h-9 outline-none" style={{ background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)', borderRadius: 9, color: 'var(--pb-text)', fontSize: 14 }}>
                {BAT_HAND_OPTS.map(([v, l]) => <option key={v} value={v} style={{ background: 'var(--pb-surface)' }}>{l}</option>)}
              </select>
            </label>
            <div className="flex items-center gap-3">
              <Btn variant="primary" sm icon="check" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save zones'}</Btn>
              {saved && <span className="text-[12.5px]" style={{ color: 'var(--pb-brand)' }}>Saved.</span>}
            </div>
          </div>
        </div>
      )}
      <Note>Scout-entered. CA has no shot-direction data, so scoring zones are your own intel.</Note>
    </Card>
  )
}

/* ── Editable scouting tags (hand / bowler type / role / keeper / danger / notes) */
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
  const [f, setF] = useState(seed)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  useEffect(() => { setF(seed()); setSaved(false) }, [playerId, tag])  // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k, v) => { setF(s => ({ ...s, [k]: v })); setSaved(false) }
  const save = async () => {
    setSaving(true)
    try { await onSave(playerId, { ...f, player_name: name }); setSaved(true) }
    finally { setSaving(false) }
  }
  const Field = ({ label, k, opts }) => (
    <label className="block">
      <span className="iq-eyebrow block mb-1.5">{label}</span>
      <select value={f[k]} onChange={e => set(k, e.target.value)}
        className="w-full px-2 h-9 outline-none" style={{ background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)', borderRadius: 9, color: 'var(--pb-text)', fontSize: 14 }}>
        {opts.map(([v, l]) => <option key={v} value={v} style={{ background: 'var(--pb-surface)' }}>{l}</option>)}
      </select>
    </label>
  )
  return (
    <Card eyebrow="manual scouting metadata" title="Scouting tags"
      right={<Btn variant="primary" sm icon="check" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save'}</Btn>}>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Bats" k="batting_hand" opts={BAT_HAND_OPTS} />
        <Field label="Bowling arm" k="bowling_action" opts={BOWL_ACTION_OPTS} />
        <Field label="Bowling type" k="bowling_type" opts={BOWL_TYPE_OPTS} />
        <Field label="Role" k="player_role" opts={ROLE_OPTS} />
      </div>
      <div className="flex flex-wrap items-center gap-5 mt-3">
        <label className="flex items-center gap-2 text-[13.5px] cursor-pointer"><input type="checkbox" checked={f.is_wicket_keeper} onChange={e => set('is_wicket_keeper', e.target.checked)} /> Wicketkeeper</label>
        <label className="flex items-center gap-2 text-[13.5px] cursor-pointer"><input type="checkbox" checked={f.is_danger} onChange={e => set('is_danger', e.target.checked)} /> Danger man</label>
        {saved && <span className="text-[12.5px] ml-auto" style={{ color: 'var(--pb-brand)' }}>Saved.</span>}
      </div>
      <div className="mt-3">
        <div className="iq-eyebrow mb-2">Scouting notes</div>
        <textarea value={f.notes} onChange={e => set('notes', e.target.value)} rows={4}
          placeholder="e.g. nervous starter, targets leg side, weak vs spin early…"
          className="w-full p-3.5 text-[13.5px] leading-relaxed resize-y outline-none"
          style={{ background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)', borderRadius: 12, color: 'var(--pb-text)', fontFamily: 'var(--iq-font-body)' }} />
      </div>
      <Note>Tags travel with the player and feed the danger/role badges across the scout.</Note>
    </Card>
  )
}

/* ── Polled scout sources (career + deep) ────────────────────────────────────
   Both ride the dossier build/poll contract: the backend answers
   `{status:'building'}` until the cached payload is ready. We start them as soon
   as a player is picked (at the OppPlayerDetail level) and share the result
   across tabs, so flicking between tabs is instant. */
const HIST_POLL_MS = 3000

function usePolledScout(fetcher, deps) {
  const [data, setData] = useState(null)
  useEffect(() => {
    setData(null)
    let alive = true
    let timer = null
    const poll = () => {
      fetcher().then(d => {
        if (!alive) return
        setData(d)
        if (d?.status === 'building') timer = setTimeout(poll, HIST_POLL_MS)
      }).catch(() => { if (alive) setData({ status: 'error' }) })
    }
    poll()
    return () => { alive = false; if (timer) clearTimeout(timer) }
  }, deps)  // eslint-disable-line react-hooks/exhaustive-deps
  return data
}

function Building({ children, ms = 12000 }) {
  return <div className="py-2"><LoadingBar label={children} expectedMs={ms} labelClassName="text-pb-faint text-[13px]" /></div>
}

/* ── Small shared renderers ──────────────────────────────────────────────── */

/* Generic season table from column defs. cols: [{key,label,align,strong,faint,fmt,totalFmt}] */
function SeasonTable({ cols, rows, total, note }) {
  return (
    <div className="overflow-x-auto iq-scroll -mx-1">
      <table className="w-full text-[13px]">
        <thead><tr className="iq-eyebrow text-left" style={{ fontSize: 9.5 }}>
          {cols.map(c => <th key={c.key} className={`py-1.5 px-1.5 font-medium ${c.align === 'right' ? 'text-right' : ''}`}>{c.label}</th>)}
        </tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} style={{ borderTop: '1px solid var(--pb-hairline)' }}>
              {cols.map(c => (
                <td key={c.key} className={`py-2 px-1.5 iq-num ${c.align === 'right' ? 'text-right' : ''} ${c.strong ? 'font-semibold' : ''} ${c.faint ? 'text-pb-faint' : ''}`}>
                  {c.fmt ? c.fmt(r) : (r[c.key] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
          {total && (
            <tr style={{ borderTop: '1px solid var(--pb-hairline2)' }} className="font-semibold">
              {cols.map(c => (
                <td key={c.key} className={`py-2 px-1.5 iq-num ${c.align === 'right' ? 'text-right' : ''}`}>
                  {c.key === cols[0].key
                    ? 'Total'
                    : c.totalFmt ? c.totalFmt(total)
                      : c.fmt ? c.fmt(total)
                        : (total[c.key] ?? '—')}
                </td>
              ))}
            </tr>
          )}
        </tbody>
      </table>
      {note && <Note>{note}</Note>}
    </div>
  )
}

/* A line trend across seasons (chronological), null/zero seasons dropped. */
function TrendChart({ seasons, pick, color, format = v => v }) {
  const rows = (seasons || []).slice().reverse()
    .map(s => ({ y: s.year, v: Number(pick(s)) }))
    .filter(r => Number.isFinite(r.v) && r.v > 0)
  if (rows.length < 3) return null
  return <AreaChart points={rows.map(r => r.v)} labels={rows.map(r => `'${String(r.y).slice(2)}`)} color={color} format={format} />
}

/* The deep-derived cards need the scorecard pass; this renders its build/empty
   state so each tab can short-circuit cleanly. Returns null when ready. */
function deepGate(deep) {
  if (!deep || deep.status === 'building') return <Card eyebrow="deep dive · building" title="Scanning scorecards"><Building ms={90000}>Scanning their recent scorecards for per-innings detail. A minute or two the first time, then cached for a week. Career numbers are ready now.</Building></Card>
  if (deep.status === 'error') return <Card eyebrow="deep dive" title="Scanning scorecards"><Note>Couldn't run the deep scan just now. Try again shortly.</Note></Card>
  return null
}

function VsUsCard({ bat, bowl }) {
  if (!(bat?.vs_us || bowl?.vs_us)) return null
  return (
    <Card accent eyebrow="our record on them" title="vs us">
      <div className="grid gap-6 sm:grid-cols-2">
        {bat?.vs_us && (
          <div>
            <div className="iq-eyebrow mb-2">Their batting vs us</div>
            <div className="flex flex-wrap items-end gap-6">
              <div><div className="iq-headline iq-num" style={{ fontSize: 30 }}>{fmtCount(bat.vs_us.runs)}</div><div className="iq-eyebrow mt-1">Runs</div></div>
              <div><div className="iq-headline iq-num" style={{ fontSize: 30, color: 'var(--pb-brand)' }}>{a2(bat.vs_us.average)}</div><div className="iq-eyebrow mt-1">Average</div></div>
              <div><div className="iq-headline iq-num" style={{ fontSize: 30 }}>{fmtCount(bat.vs_us.high_score)}</div><div className="iq-eyebrow mt-1">High score</div></div>
            </div>
            <div className="text-pb-faint text-[12px] mt-2 iq-num">{num(bat.vs_us.innings, 0)} inns{bat.vs_us.fifties ? ` · ${bat.vs_us.fifties}×50` : ''}{bat.vs_us.hundreds ? ` · ${bat.vs_us.hundreds}×100` : ''}{bat.vs_us.dismissed_by ? ` · out to ${bat.vs_us.dismissed_by}` : ''}</div>
          </div>
        )}
        {bowl?.vs_us && (
          <div>
            <div className="iq-eyebrow mb-2">Their bowling vs us</div>
            <div className="flex flex-wrap items-end gap-6">
              <div><div className="iq-headline iq-num" style={{ fontSize: 30 }}>{fmtCount(bowl.vs_us.wickets)}</div><div className="iq-eyebrow mt-1">Wickets</div></div>
              <div><div className="iq-headline iq-num" style={{ fontSize: 30, color: 'var(--pb-red)' }}>{a2(bowl.vs_us.average)}</div><div className="iq-eyebrow mt-1">Average</div></div>
              <div><div className="iq-headline iq-num" style={{ fontSize: 30 }}>{a2(bowl.vs_us.economy)}</div><div className="iq-eyebrow mt-1">Economy</div></div>
            </div>
            {bowl.vs_us.best && <div className="text-pb-faint text-[12px] mt-2 iq-num">Best vs us: {bowl.vs_us.best}</div>}
          </div>
        )}
      </div>
    </Card>
  )
}

function CareerSnapshot({ career }) {
  if (!career || career.status === 'building') {
    return <Card eyebrow="career" title="Career snapshot"><Building>Pulling their season history from PlayHQ. Quick the first time, instant after.</Building></Card>
  }
  if (career.status !== 'ready') return null
  const p = career.player
  if (!p) return <Card eyebrow="career" title="Career snapshot"><Note>No CA season records found. They may be new, or recorded under a different club.</Note></Card>
  const t = p.totals || {}
  const w = career.window
  const showBowl = (t.wickets || 0) > 0
  return (
    <Card eyebrow={`career · ${w ? `${w.from_year}–${w.to_year}` : 'recent seasons'}`} title="Career snapshot"
      right={<Tag tone="faint">{fmtCount(t.matches)} matches</Tag>}>
      <div className="grid grid-cols-3 gap-4">
        <Stat label="Runs" value={t.runs} />
        <Stat label="Average" value={a2(t.average)} count={false} />
        <Stat label="High score" value={num(t.high_score)} count={false} />
        {showBowl && <Stat label="Wickets" value={t.wickets} />}
        {showBowl && <Stat label="Bowl avg" value={a2(t.bowling_average)} count={false} />}
        <Stat label="Catches" value={t.catches} />
      </div>
      <div className="text-pb-faint text-[12px] mt-3 iq-num">{t.fifties || 0}×50 · {t.hundreds || 0}×100{showBowl && t.best ? ` · best ${t.best}` : ''}{(t.stumpings || 0) ? ` · ${t.stumpings} st` : ''}</div>
    </Card>
  )
}

/* ── Tabs ────────────────────────────────────────────────────────────────── */

function OverviewTab({ entry, deep, career, dossierBatting, dossierBowling, isBowler, bat, bowl }) {
  return (
    <div className="space-y-5">
      {deep?.status === 'ready' && deep.summary && (
        <Card accent eyebrow="scouting read · recent seasons" title="How he plays">
          <div className="text-[14px] leading-relaxed" style={{ color: 'var(--pb-accent)' }}>{deep.summary}</div>
        </Card>
      )}
      <div className="grid gap-5 lg:grid-cols-2 items-start">
        <OppRadarCard entry={entry} batPeers={dossierBatting} bowlPeers={dossierBowling} prefer={isBowler ? 'bowl' : 'bat'} />
        <CareerSnapshot career={career} />
      </div>
      <VsUsCard bat={bat} bowl={bowl} />
    </div>
  )
}

function BattingTab({ entry, bat, deep, career, tag, playerId, onSaveTag, formColor, dism, dismTotal, spark, battingHand, scoutStats, showCard }) {
  const db = deep?.status === 'ready' ? deep.batting : null
  const cp = career?.status === 'ready' ? career.player : null
  const batSeasons = (cp?.seasons || []).filter(s => (s.innings || s.runs))
  const conv = db?.conversion
  const bandsMax = Math.max(1, ...(db?.bands || []).map(x => x.count))
  const rel = db?.reliability
  const sty = db?.style
  // Dismissal mix: prefer the deeper scorecard pass, fall back to the dossier.
  const dismData = db?.dismissals?.length
    ? db.dismissals
    : (dism || []).map(([type, count]) => ({ type, count, pct: dismTotal ? Math.round((count / dismTotal) * 100) : 0 }))

  return (
    <div className="space-y-5">
      <div className="grid gap-5 lg:grid-cols-2 items-start">
        {bat && bat.innings > 0 && (
          <Card eyebrow="this season" title="Batting form">
            <div className="grid grid-cols-3 gap-4">
              <Stat label="Runs" value={bat.runs} />
              <Stat label="Average" value={a2(bat.average)} count={false} />
              <Stat label="Strike rate" value={a2(bat.strike_rate)} count={false} />
              <Stat label="High score" value={num(bat.high_score)} count={false} />
              <Stat label="50s / 100s" value={`${num(bat.fifties, 0)}/${num(bat.hundreds, 0)}`} count={false} />
              <Stat label="Innings" value={bat.innings} />
            </div>
            {bat.boundary_pct != null && <div className="text-pb-faint text-[12px] mt-3 iq-num">Boundary %: {fmtPct(bat.boundary_pct)}</div>}
            {spark.length >= 2 && (
              <div className="mt-5 px-3 pt-3 pb-2" style={{ background: 'var(--pb-surface2)', borderRadius: 12 }}>
                <div className="flex items-center justify-between mb-1">
                  <span className="iq-eyebrow" style={{ fontSize: 9 }}>Last {spark.length}</span>
                  <span className="iq-mono text-pb-faint" style={{ fontSize: 10.5 }}>{(bat.recent_scores || []).join(' · ')}</span>
                </div>
                <Sparkline key={playerId || entry.name} values={spark} h={46} stroke={formColor} dots />
              </div>
            )}
          </Card>
        )}
        {showCard && (bat?.innings > 0 || (Array.isArray(tag?.scoring_zones) && tag.scoring_zones.some(v => Number(v) > 0))) && (
          <ZonesEditor playerId={playerId} name={entry.name} tag={tag} battingHand={battingHand} onSave={onSaveTag} />
        )}
      </div>

      {/* Manual batting intel — how to get him out, blended with the held mix. */}
      {showCard && (
        <ScoutingCard only="bat" keyId={playerId}
          batting={tag?.batting_intel} stats={scoutStats}
          onSave={(body) => onSaveTag(playerId, { ...body, player_name: entry.name })} />
      )}

      {/* Deeper scorecard reads */}
      {deepGate(deep) || (db ? (
        <div className="grid gap-5 lg:grid-cols-2 items-start">
          {dismData.length > 0 && (
            <Card eyebrow="recent seasons" title="How he gets out">
              <StackedBar data={dismData} />
            </Card>
          )}
          {conv && db.innings_count >= 5 && (
            <Card eyebrow="recent seasons" title="Starts & conversion">
              <div className="grid grid-cols-3 gap-4">
                <Stat label="Reaches 25" value={conv.start_pct != null ? `${conv.start_pct}%` : '—'} count={false} />
                <Stat label="25 → 50" value={conv.fifty_conv_pct != null ? `${conv.fifty_conv_pct}%` : '—'} count={false} />
                <Stat label="50 → 100" value={conv.hundred_conv_pct != null ? `${conv.hundred_conv_pct}%` : '—'} count={false} />
              </div>
              {db.bands?.length > 0 && (
                <div className="space-y-1.5 mt-4">
                  {db.bands.map((band, i) => (
                    <div key={band.band} className="flex items-center gap-3 text-[12.5px]">
                      <span className="w-12 shrink-0 iq-mono text-pb-faint" style={{ fontSize: 10.5 }}>{band.band}</span>
                      <div className="flex-1"><Bar pct={(band.count / bandsMax) * 100} color="var(--pb-accent)" h={7} delay={i * 0.05} /></div>
                      <span className="w-6 text-right iq-num text-pb-dim shrink-0">{band.count}</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          )}
          {rel && (
            <Card eyebrow="recent seasons" title="Reliability"
              right={rel.profile ? <Tag tone={rel.profile === 'Steady' ? 'win' : rel.profile === 'Boom or bust' ? 'amber' : 'accent'}>{rel.profile}</Tag> : null}>
              <div className="grid grid-cols-3 gap-4">
                <Stat label="Floor" value={num(rel.floor)} sub="25th %ile" />
                <Stat label="Typical" value={num(rel.median)} sub="median" />
                <Stat label="Ceiling" value={num(rel.ceiling)} sub="90th %ile" />
              </div>
              <div className="grid grid-cols-2 gap-4 mt-4">
                <Stat label="Fails (<10)" value={rel.failure_rate != null ? `${rel.failure_rate}%` : '—'} count={false} tone="loss" />
                <Stat label="20+ contributions" value={rel.contribution_rate != null ? `${rel.contribution_rate}%` : '—'} count={false} tone="win" />
              </div>
              <Note>How dependable his score is, from the spread of his innings: floor to ceiling, how often he fails, and how often he makes 20+.</Note>
            </Card>
          )}
          {sty && (
            <Card eyebrow="recent seasons" title="Scoring style"
              right={sty.profile ? <Tag tone={sty.profile === 'Boundary hitter' ? 'red' : 'accent'}>{sty.profile}</Tag> : null}>
              <div className="grid grid-cols-3 gap-4">
                <Stat label="Strike rate" value={a2(sty.strike_rate)} count={false} />
                <Stat label="Boundary %" value={sty.boundary_pct != null ? `${sty.boundary_pct}%` : '—'} count={false} />
                <Stat label="Balls / bdry" value={num(sty.balls_per_boundary)} count={false} />
              </div>
              <div className="text-pb-faint text-[12px] mt-3 iq-num">{sty.fours} fours · {sty.sixes} sixes off {fmtCount(sty.balls)} balls faced</div>
            </Card>
          )}
          {db.by_position?.length > 0 && (
            <Card eyebrow="recent seasons" title="By batting position">
              <div className="space-y-2">
                {db.by_position.map(p => (
                  <div key={p.bucket} className="flex items-center justify-between gap-3 text-[13px]">
                    <span className="font-medium">{p.bucket}</span>
                    <span className="iq-num text-pb-dim whitespace-nowrap">{p.innings} inns · {fmtCount(p.runs)} runs{p.average != null ? ` @ ${a2(p.average)}` : ''}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      ) : null)}

      {/* Season-by-season batting (CA aggregates — the long view) */}
      {career?.status === 'building' && <Card eyebrow="career" title="Season by season"><Building>Pulling their season history…</Building></Card>}
      {batSeasons.length > 0 && (
        <Card eyebrow="career · season by season" title="Batting by season">
          <TrendChart seasons={batSeasons} pick={s => s.average} color="var(--pb-accent)" />
          <div className="mt-3">
            <SeasonTable
              rows={batSeasons}
              total={cp?.totals}
              note="Season totals straight from Cricket Australia, for this club only. Seasons at a previous club won't show here."
              cols={[
                { key: 'year', strong: true },
                { key: 'matches', label: 'M', align: 'right', faint: true, fmt: r => fmtCount(r.matches) },
                { key: 'innings', label: 'Inns', align: 'right', faint: true, fmt: r => fmtCount(r.innings) },
                { key: 'runs', label: 'Runs', align: 'right', strong: true, fmt: r => fmtCount(r.runs) },
                { key: 'average', label: 'Avg', align: 'right', fmt: r => a2(r.average) },
                { key: 'strike_rate', label: 'SR', align: 'right', faint: true, fmt: r => (r.strike_rate != null ? a2(r.strike_rate) : '—') },
                { key: 'high_score', label: 'HS', align: 'right', fmt: r => r.high_score ?? '—' },
                { key: 'fr', label: '50/100', align: 'right', faint: true, fmt: r => `${r.fifties || 0}/${r.hundreds || 0}`, totalFmt: t => `${t?.fifties || 0}/${t?.hundreds || 0}` },
              ]}
            />
          </div>
        </Card>
      )}

      {/* Recent innings (deep scan) */}
      {db?.recent?.length > 0 && (
        <Card eyebrow="most recent first" title="Recent innings">
          <SeasonTable
            rows={db.recent}
            cols={[
              { key: 'date', label: 'Date', faint: true, fmt: r => r.date || '—' },
              { key: 'runs', label: 'Score', align: 'right', strong: true, fmt: r => `${r.runs}${r.not_out ? '*' : ''}${r.balls ? ` (${r.balls})` : ''}` },
              { key: 'vs', label: 'vs', fmt: r => r.vs || '—' },
              { key: 'grade', label: 'Grade', faint: true, fmt: r => r.grade || '—' },
              { key: 'dismissal', label: 'Out', faint: true, fmt: r => (r.not_out ? 'not out' : (r.dismissal || '—')) },
            ]}
          />
        </Card>
      )}

      {db && deep?.coverage?.notes?.length > 0 && <Note>{deep.coverage.notes.join(' ')}</Note>}
      {!bat?.innings && !db && !batSeasons.length && career?.status !== 'building' && (
        <Card eyebrow="batting" title="At the crease"><Note>No batting records we can see for this player yet. Add scouting intel above to build a read.</Note></Card>
      )}
    </div>
  )
}

function BowlingTab({ entry, bowl, deep, career, tag, playerId, onSaveTag, bowlSpark, scoutStats, showCard }) {
  const dbw = deep?.status === 'ready' ? deep.bowling : null
  const cp = career?.status === 'ready' ? career.player : null
  const bowlSeasons = (cp?.seasons || []).filter(s => (s.wickets || s.overs))
  const q = dbw?.quality

  return (
    <div className="space-y-5">
      <div className="grid gap-5 lg:grid-cols-2 items-start">
        {bowl && bowl.wickets > 0 && (
          <Card eyebrow="this season" title="Bowling form">
            <div className="grid grid-cols-3 gap-4">
              <Stat label="Wickets" value={bowl.wickets} />
              <Stat label="Average" value={a2(bowl.average)} count={false} />
              <Stat label="Economy" value={a2(bowl.economy)} count={false} />
              <Stat label="Strike rate" value={a2(bowl.strike_rate)} count={false} />
              <Stat label="Best" value={num(bowl.best)} count={false} />
              <Stat label="Overs" value={fmtOvers(bowl.overs)} count={false} />
            </div>
            <div className="text-pb-faint text-[12px] mt-3 iq-num">
              {bowl.five_fors ? `${bowl.five_fors}× 5wi · ` : ''}{fmtCount(bowl.matches)} match{bowl.matches === 1 ? '' : 'es'}{bowl.maidens ? ` · ${bowl.maidens} maidens` : ''}
            </div>
            {bowlSpark.length >= 2 && (
              <div className="mt-4 px-3 pt-3 pb-2" style={{ background: 'var(--pb-surface2)', borderRadius: 12 }}>
                <div className="flex items-center justify-between mb-1">
                  <span className="iq-eyebrow" style={{ fontSize: 9 }}>Wickets · last {bowlSpark.length}</span>
                  <span className="iq-mono text-pb-faint" style={{ fontSize: 10.5 }}>{(bowl.recent_wickets || []).join(' · ')}</span>
                </div>
                <Sparkline key={`bw-${playerId || entry.name}`} values={bowlSpark} h={46} stroke="var(--pb-accent)" dots />
              </div>
            )}
          </Card>
        )}
        {/* How he takes wickets + wicket quality (deep scan) */}
        {dbw && (dbw.dismissals?.length > 0 || q) && (
          <Card eyebrow="recent seasons" title="How he takes wickets">
            {dbw.dismissals?.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {dbw.dismissals.map((d, i) => (
                  <span key={i} className="text-[12px] px-2.5 py-1 capitalize" style={{ background: 'var(--pb-surface2)', borderRadius: 99 }}>
                    {d.type} <span className="iq-num text-pb-faint">{d.count}{d.pct != null ? ` · ${d.pct}%` : ''}</span>
                  </span>
                ))}
              </div>
            )}
            {q && (
              <div className="mt-4 pt-4" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
                <div className="iq-eyebrow mb-2">Calibre of batter removed</div>
                <div className="grid grid-cols-3 gap-4">
                  <Stat label="Set (30+)" value={q.set != null ? `${q.set_pct}%` : '—'} count={false} tone="accent" />
                  <Stat label="New (<10)" value={q.new != null ? `${q.new_pct}%` : '—'} count={false} />
                  <Stat label="Avg scalp" value={a2(q.scalp_value)} count={false} />
                </div>
                {q.ducks ? <div className="text-pb-faint text-[12px] mt-3 iq-num">{q.ducks} duck{q.ducks === 1 ? '' : 's'} inflicted</div> : null}
              </div>
            )}
          </Card>
        )}
      </div>

      {/* Manual bowling intel — how to play him, blended with the held mix. */}
      {showCard && (
        <ScoutingCard only="bowl" keyId={playerId}
          bowling={tag?.bowling_intel} stats={scoutStats}
          onSave={(body) => onSaveTag(playerId, { ...body, player_name: entry.name })} />
      )}

      {deepGate(deep)}

      {/* Season-by-season bowling */}
      {career?.status === 'building' && <Card eyebrow="career" title="Bowling by season"><Building>Pulling their season history…</Building></Card>}
      {bowlSeasons.length > 0 && (
        <Card eyebrow="career · season by season" title="Bowling by season">
          <TrendChart seasons={bowlSeasons} pick={s => s.wickets} color="var(--pb-accent)" format={v => Math.round(v)} />
          <div className="mt-3">
            <SeasonTable
              rows={bowlSeasons}
              total={cp?.totals}
              note="Bowling totals straight from Cricket Australia, for this club only."
              cols={[
                { key: 'year', strong: true },
                { key: 'overs', label: 'Overs', align: 'right', faint: true, fmt: r => fmtOvers(r.overs) },
                { key: 'wickets', label: 'Wkts', align: 'right', strong: true, fmt: r => fmtCount(r.wickets) },
                { key: 'bowling_average', label: 'Avg', align: 'right', fmt: r => a2(r.bowling_average) },
                { key: 'economy', label: 'Econ', align: 'right', faint: true, fmt: r => a2(r.economy) },
                { key: 'best', label: 'Best', align: 'right', fmt: r => r.best ?? '—' },
                { key: 'five_fors', label: '5wi', align: 'right', faint: true, fmt: r => r.five_fors || 0 },
              ]}
            />
          </div>
        </Card>
      )}

      {/* Recent spells */}
      {dbw?.recent?.length > 0 && (
        <Card eyebrow="most recent first" title="Recent spells">
          <SeasonTable
            rows={dbw.recent}
            cols={[
              { key: 'date', label: 'Date', faint: true, fmt: r => r.date || '—' },
              { key: 'fig', label: 'Figures', align: 'right', strong: true, fmt: r => `${r.wickets}/${r.runs}` },
              { key: 'overs', label: 'Ov', align: 'right', faint: true, fmt: r => fmtOvers(r.overs) },
              { key: 'vs', label: 'vs', fmt: r => r.vs || '—' },
              { key: 'grade', label: 'Grade', faint: true, fmt: r => r.grade || '—' },
            ]}
          />
        </Card>
      )}

      {dbw && deep?.coverage?.notes?.length > 0 && <Note>{deep.coverage.notes.join(' ')}</Note>}
      {!bowl?.wickets && !dbw && !bowlSeasons.length && career?.status !== 'building' && (
        <Card eyebrow="bowling" title="With the ball"><Note>No bowling records we can see for this player. Add scouting intel above to build a read.</Note></Card>
      )}
    </div>
  )
}

function FieldingTab({ career, deep, tag }) {
  const cp = career?.status === 'ready' ? career.player : null
  const t = cp?.totals || null
  const df = deep?.status === 'ready' ? deep.fielding : null
  const fldSeasons = (cp?.seasons || []).filter(s => ((s.catches || 0) + (s.stumpings || 0) + (s.run_outs || 0)) > 0)
  const building = career?.status === 'building'

  const ctTotal = t?.catches || 0
  const ctWk = t?.catches_wk || 0
  const outfield = Math.max(ctTotal - ctWk, 0)
  const st = t?.stumpings || 0
  const ro = t?.run_outs || 0
  const dismissals = ctTotal + st + ro
  const keeps = ctWk > 0 || st > 0 || tag?.is_wicket_keeper || tag?.player_role === 'WK'
  const hasCareer = t && dismissals > 0
  const perMatch = t?.matches ? dismissals / t.matches : null

  if (building) return <Card eyebrow="fielding" title="In the field"><Building>Pulling their fielding history…</Building></Card>
  if (!hasCareer && !df) {
    return <Card eyebrow="fielding" title="In the field"><Note>No fielding records for this player in the seasons we can see.</Note></Card>
  }

  return (
    <div className="space-y-5">
      {hasCareer && (
        <Card eyebrow={`career · ${career.window ? `${career.window.from_year}–${career.window.to_year}` : 'recent seasons'}`} title="In the field"
          right={keeps ? <Tag tone="accent">Keeps wicket</Tag> : null}>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <Stat label="Dismissals" value={dismissals} />
            <Stat label="Catches (outfield)" value={outfield} />
            <Stat label="Catches (wk)" value={ctWk} />
            <Stat label="Stumpings" value={st} />
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-4">
            <Stat label="Run-outs" value={ro} />
            <Stat label="Total catches" value={ctTotal} />
            <Stat label="Per match" value={perMatch != null ? a2(perMatch) : '—'} count={false} />
            <Stat label="Matches" value={t.matches} />
          </div>
          <Note>Catches split into outfield vs behind the stumps where Cricket Australia records the keeper. A high keeper-catch or stumping count is the tell for a gloveman.</Note>
        </Card>
      )}

      {fldSeasons.length > 0 && (
        <Card eyebrow="career · season by season" title="Fielding by season">
          <SeasonTable
            rows={fldSeasons}
            total={t}
            cols={[
              { key: 'year', strong: true },
              { key: 'matches', label: 'M', align: 'right', faint: true, fmt: r => fmtCount(r.matches) },
              { key: 'catches', label: 'Ct', align: 'right', strong: true, fmt: r => fmtCount(r.catches) },
              { key: 'outfield', label: 'Outfield', align: 'right', fmt: r => Math.max((r.catches || 0) - (r.catches_wk || 0), 0), totalFmt: tt => Math.max((tt.catches || 0) - (tt.catches_wk || 0), 0) },
              { key: 'catches_wk', label: 'Ct (wk)', align: 'right', faint: true, fmt: r => r.catches_wk || 0 },
              { key: 'stumpings', label: 'St', align: 'right', fmt: r => r.stumpings || 0 },
              { key: 'run_outs', label: 'RO', align: 'right', faint: true, fmt: r => r.run_outs || 0 },
            ]}
          />
        </Card>
      )}

      {df && (df.catches || df.stumpings || df.run_outs) ? (
        <Card eyebrow="deep scan · games we scanned" title="In the games we scanned">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <Stat label="Catches" value={df.catches || 0} />
            <Stat label="Catches (wk)" value={df.catches_wk || 0} />
            <Stat label="Stumpings" value={df.stumpings || 0} />
            <Stat label="Run-outs" value={df.run_outs || 0} />
          </div>
          <Note>From the individual scorecards we pulled: a subset of the career totals above, shown for the games in the deep scan window.</Note>
        </Card>
      ) : null}
    </div>
  )
}

function NotesTab({ playerId, name, tag, onSaveTag, enriched }) {
  return (
    <div className="space-y-5">
      {(enriched?.key_note || enriched?.plan) && (
        <Card accent eyebrow="auto read" title="Quick read">
          {enriched?.key_note && <div className="text-[14px]" style={{ color: 'var(--pb-accent)' }}>{enriched.key_note}</div>}
          {enriched?.plan && <div className="text-[13px] mt-2 text-pb-dim">Plan: {enriched.plan}</div>}
        </Card>
      )}
      <ScoutingTags playerId={playerId} name={name} tag={tag} onSave={onSaveTag} />
    </div>
  )
}

/* ── The full per-player profile (tabbed) ─────────────────────────────────── */
export function OppPlayerDetail({ entry, enriched, opponentName, playerId, tag, onSaveTag, dossierBatting = [], dossierBowling = [], orgGuid = null }) {
  const [tab, setTab] = useState('overview')
  useEffect(() => { setTab('overview') }, [playerId])

  // Lift career + deep so they start as soon as a player is picked and are shared
  // across tabs. Hooks must run before any early return; the fetchers no-op (and
  // never poll) when there's no CA org GUID to scout with.
  const career = usePolledScout(
    () => ((orgGuid && playerId)
      ? api.iqPlayerCareer({ org: orgGuid, player: playerId, clubName: opponentName })
      : Promise.resolve({ status: 'unavailable' })),
    [orgGuid, playerId],
  )
  const deep = usePolledScout(
    () => ((orgGuid && playerId)
      ? api.iqPlayerDeep({ org: orgGuid, player: playerId, playerName: entry?.name, clubName: opponentName })
      : Promise.resolve({ status: 'unavailable' })),
    [orgGuid, playerId],
  )

  if (!entry) return null
  const { bat, bowl } = entry
  const battingHand = tag?.batting_hand || ''
  const role = (tag?.player_role && ROLE_LABEL[tag.player_role]) || (bat && bowl ? 'All-rounder' : bowl ? 'Bowler' : 'Batter')
  const formColor = bat?.form === 'hot' ? 'var(--pb-red)' : bat?.form === 'cold' ? 'var(--pb-faint)' : 'var(--pb-accent)'
  const dism = bat?.dismissals && Object.entries(bat.dismissals).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1])
  const dismTotal = dism ? dism.reduce((s, [, v]) => s + v, 0) : 0
  const spark = sparkVals(bat?.recent_scores)
  const bowlSpark = (bowl?.recent_wickets || []).map(v => Number(v) || 0)
  const isBowler = role === 'Bowler'
  const showCard = !!(playerId && onSaveTag)
  // Held mixes blended into the scouting cards' DNA read.
  const scoutStats = {
    dismissals: (dism || []).map(([type, count]) => ({ type, count })),
    wicketMethods: (deep?.status === 'ready' ? deep.bowling?.dismissals || [] : []).map(d => ({ type: d.type, count: d.count })),
  }

  const tabs = [
    { value: 'overview', label: 'Overview' },
    { value: 'batting', label: 'Batting' },
    { value: 'bowling', label: 'Bowling' },
    { value: 'fielding', label: 'Fielding' },
    { value: 'notes', label: 'Notes' },
  ]

  return (
    <div className="iq-fade space-y-5">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Initials name={entry.name} size={52} tone="accent" />
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="iq-headline truncate" style={{ fontSize: 28 }}>{entry.name}</h2>
            {bat?.form && <Tag tone={bat.form === 'hot' ? 'red' : bat.form === 'cold' ? 'faint' : 'accent'}>{bat.form}</Tag>}
            {enriched?.alert?.level === 'danger' && <Tag tone="red">Danger</Tag>}
            {enriched?.alert?.level === 'caution' && <Tag tone="amber">Paper tiger?</Tag>}
          </div>
          <div className="text-pb-faint text-[13px] mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
            <span>{role}{opponentName ? ` · ${opponentName}` : ''}</span>
            <TagBadges tag={tag} />
          </div>
        </div>
      </div>

      {/* Plan / key note from enrichment — the actionable headline, always shown */}
      {(enriched?.key_note || enriched?.plan) && (
        <Card accent eyebrow="scouting read" title="The plan">
          {enriched?.key_note && <div className="text-[14px]" style={{ color: 'var(--pb-accent)' }}>{enriched.key_note}</div>}
          {enriched?.plan && <div className="text-[13px] mt-2 text-pb-dim">Plan: {enriched.plan}</div>}
        </Card>
      )}

      <Tabs tabs={tabs} value={tab} onChange={setTab} />

      <div className="pt-1">
        {tab === 'overview' && (
          <OverviewTab entry={entry} deep={deep} career={career}
            dossierBatting={dossierBatting} dossierBowling={dossierBowling} isBowler={isBowler} bat={bat} bowl={bowl} />
        )}
        {tab === 'batting' && (
          <BattingTab entry={entry} bat={bat} deep={deep} career={career} tag={tag} playerId={playerId} onSaveTag={onSaveTag}
            formColor={formColor} dism={dism} dismTotal={dismTotal} spark={spark} battingHand={battingHand}
            scoutStats={scoutStats} showCard={showCard} />
        )}
        {tab === 'bowling' && (
          <BowlingTab entry={entry} bowl={bowl} deep={deep} career={career} tag={tag} playerId={playerId} onSaveTag={onSaveTag}
            bowlSpark={bowlSpark} scoutStats={scoutStats} showCard={showCard} />
        )}
        {tab === 'fielding' && <FieldingTab career={career} deep={deep} tag={tag} />}
        {tab === 'notes' && showCard && <NotesTab playerId={playerId} name={entry.name} tag={tag} onSaveTag={onSaveTag} enriched={enriched} />}
      </div>
    </div>
  )
}
