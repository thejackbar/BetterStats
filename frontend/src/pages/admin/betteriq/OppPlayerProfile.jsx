/* BetterIQ — Opposition player profile (v2 design).
 *
 * The closest thing to our own player deep-dive that the data supports for an
 * opponent: current-season batting & bowling, recent form, dismissal patterns
 * and their full record vs us — all built from the live dossier (we don't store
 * opponents' multi-season history). On top of the held data the club records
 * MANUAL scouting metadata that travels with the player:
 *   • handedness / bowler type / role / keeper / danger flag / free-text notes
 *   • scout-entered WAGON-WHEEL scoring zones (CA has no shot-direction data)
 * Plus a Radar built client-side from the dossier squad (opponents have no
 * /radar endpoint), so the profile normalises the player against their own team.
 *
 * Public interface preserved for OppositionScout.jsx:
 *   - buildOppPlayerIndex(dossier) → Map<player_id, {name, bat, bowl}>
 *   - <OppPlayerDetail entry enriched opponentName playerId tag onSaveTag />
 * New OPTIONAL props (safe defaults) extend it without breaking that call:
 *   - dossierBatting / dossierBowling — peer groups for the radar.
 */
import { useState, useEffect, useMemo, useRef } from 'react'
import { api } from '../../../lib/api'
import {
  Sparkline, Card, Stat, Note, Tag, Btn, Segmented, Initials, StackedBar, Bar, a2,
  LoadingBar, fmtCount, fmtOvers, fmtPct, oversToBalls,
} from './ui'
import { Radar, WagonWheel, ZONE_LABELS, buildRadar } from './viz'
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

/* ── Scoring-zones wagon wheel + scout editor ────────────────────────────── */
function ZonesEditor({ playerId, name, tag, battingHand, onSave }) {
  const seedZones = () => {
    const z = tag?.scoring_zones
    return Array.from({ length: 8 }, (_, i) => (Array.isArray(z) && z[i] != null ? Number(z[i]) : ''))
  }
  const [open, setOpen] = useState(false)
  const [zones, setZones] = useState(seedZones)
  const [hand, setHand] = useState(tag?.batting_hand || battingHand || '')
  const [notes, setNotes] = useState(tag?.notes || '')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  // Re-seed when switching players or when a fresh tag arrives.
  useEffect(() => {
    setZones(seedZones()); setHand(tag?.batting_hand || battingHand || ''); setNotes(tag?.notes || '')
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
      await onSave(playerId, { scoring_zones: arr, batting_hand: hand || null, notes, player_name: name })
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
        <div className="text-pb-faint text-[13px]">No scoring zones recorded yet — tap <b>Add zones</b> to plot where this batter scores (CA gives us no shot-direction data, so this is scout intel).</div>
      )}

      {open && (
        <div className="grid gap-5 lg:grid-cols-[230px_1fr] items-start">
          {/* Live preview */}
          <div className="flex justify-center">
            <WagonWheel sectors={zones.map(v => Number(v) || 0)} hand={wheelHand} color="var(--pb-red)" />
          </div>
          {/* 8 zone inputs + hand + notes */}
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
            <label className="block">
              <span className="iq-eyebrow block mb-1.5">Notes</span>
              <textarea value={notes} onChange={e => { setNotes(e.target.value); setSaved(false) }} rows={3}
                placeholder="e.g. dominant square of the wicket, quiet straight…"
                className="w-full p-3 text-[13.5px] leading-relaxed resize-y outline-none"
                style={{ background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)', borderRadius: 12, color: 'var(--pb-text)', fontFamily: 'var(--iq-font-body)' }} />
            </label>
            <div className="flex items-center gap-3">
              <Btn variant="primary" sm icon="check" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save zones'}</Btn>
              {saved && <span className="text-[12.5px]" style={{ color: 'var(--pb-brand)' }}>Saved.</span>}
            </div>
          </div>
        </div>
      )}

      {tag?.notes && !open && <div className="text-pb-dim text-[12.5px] mt-3 leading-relaxed">{tag.notes}</div>}
      <Note>Scout-entered — CA has no shot-direction data, so scoring zones are your own intel.</Note>
    </Card>
  )
}

/* ── Editable scouting tags (hand / bowler type / role / keeper / danger) ──── */
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
        <textarea value={f.notes} onChange={e => set('notes', e.target.value)} rows={3}
          placeholder="e.g. nervous starter, targets leg side, weak vs spin early…"
          className="w-full p-3.5 text-[13.5px] leading-relaxed resize-y outline-none"
          style={{ background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)', borderRadius: 12, color: 'var(--pb-text)', fontFamily: 'var(--iq-font-body)' }} />
      </div>
      <Note>Tags travel with the player and feed the danger/role badges across the scout.</Note>
    </Card>
  )
}

/* ── 5-year history (CA aggregates + scorecard deep pass) ────────────────────
   Both ride the same build/poll contract as the dossier: the backend answers
   `{status:'building'}` until the cached payload is ready. The career slice is
   near-instant once the club's blob has been built once; the deep pass scans
   only the grades this player appeared in (a minute or two first time, then
   cached for a week). Needs the club's CA org GUID (dossier `opponent.org_id`),
   so these render for any club — including ones we've never played. */

const HIST_POLL_MS = 3000

function usePolledScout(fetcher, deps) {
  const [data, setData] = useState(null)
  const timerRef = useRef(null)
  useEffect(() => {
    setData(null)
    let alive = true
    const poll = () => {
      fetcher().then(d => {
        if (!alive) return
        setData(d)
        if (d?.status === 'building') timerRef.current = setTimeout(poll, HIST_POLL_MS)
      }).catch(() => { if (alive) setData({ status: 'error' }) })
    }
    poll()
    return () => { alive = false; if (timerRef.current) clearTimeout(timerRef.current) }
  }, deps)  // eslint-disable-line react-hooks/exhaustive-deps
  return data
}

function HistoryBuilding({ children, expectedMs = 10000 }) {
  return (
    <div className="py-2">
      <LoadingBar label={children} expectedMs={expectedMs} labelClassName="text-pb-faint text-[13px]" />
    </div>
  )
}

function PlayerCareerCard({ orgGuid, playerId, clubName }) {
  const data = usePolledScout(
    () => api.iqPlayerCareer({ org: orgGuid, player: playerId, clubName }),
    [orgGuid, playerId],
  )
  const windowLabel = data?.window ? `${data.window.from_year}–${data.window.to_year}` : 'recent seasons'
  const p = data?.player
  const showBowl = p && (p.totals?.wickets || 0) > 0
  return (
    <Card eyebrow={`career · ${windowLabel}`} title="Season by season"
      right={p ? <Tag tone="faint">{fmtCount(p.totals?.matches)} matches</Tag> : null}>
      {!data || data.status === 'building' ? (
        <HistoryBuilding>Pulling their season history from PlayHQ — quick the first time, instant after.</HistoryBuilding>
      ) : data.status === 'error' ? (
        <Note>Couldn't pull their career history just now — try again shortly.</Note>
      ) : data.status !== 'ready' ? (
        <Note>{data.message || 'No Cricket Australia history available for this club.'}</Note>
      ) : !p ? (
        <Note>No CA season records found for this player — they may be new, or recorded under a different club.</Note>
      ) : (
        <div className="overflow-x-auto iq-scroll -mx-1">
          <table className="w-full text-[13px]">
            <thead><tr className="iq-eyebrow text-left" style={{ fontSize: 9.5 }}>
              <th className="py-1.5 px-1.5 font-medium">Year</th>
              <th className="py-1.5 px-1.5 font-medium text-right">M</th>
              <th className="py-1.5 px-1.5 font-medium text-right">Runs</th>
              <th className="py-1.5 px-1.5 font-medium text-right">Avg</th>
              <th className="py-1.5 px-1.5 font-medium text-right">HS</th>
              <th className="py-1.5 px-1.5 font-medium text-right">50/100</th>
              {showBowl && <>
                <th className="py-1.5 px-1.5 font-medium text-right">Wkts</th>
                <th className="py-1.5 px-1.5 font-medium text-right">Avg</th>
                <th className="py-1.5 px-1.5 font-medium text-right">Econ</th>
              </>}
              <th className="py-1.5 px-1.5 font-medium text-right">Ct</th>
            </tr></thead>
            <tbody>
              {(p.seasons || []).map(s => (
                <tr key={s.year} style={{ borderTop: '1px solid var(--pb-hairline)' }}>
                  <td className="py-2 px-1.5 iq-num font-medium">{s.year}</td>
                  <td className="py-2 px-1.5 text-right iq-num text-pb-faint">{fmtCount(s.matches)}</td>
                  <td className="py-2 px-1.5 text-right iq-num font-semibold">{fmtCount(s.runs)}</td>
                  <td className="py-2 px-1.5 text-right iq-num">{a2(s.average)}</td>
                  <td className="py-2 px-1.5 text-right iq-num">{s.high_score ?? '—'}</td>
                  <td className="py-2 px-1.5 text-right iq-num text-pb-faint">{s.fifties || 0}/{s.hundreds || 0}</td>
                  {showBowl && <>
                    <td className="py-2 px-1.5 text-right iq-num font-semibold">{fmtCount(s.wickets)}</td>
                    <td className="py-2 px-1.5 text-right iq-num">{a2(s.bowling_average)}</td>
                    <td className="py-2 px-1.5 text-right iq-num text-pb-faint">{a2(s.economy)}</td>
                  </>}
                  <td className="py-2 px-1.5 text-right iq-num text-pb-faint">{fmtCount(s.catches)}</td>
                </tr>
              ))}
              <tr style={{ borderTop: '1px solid var(--pb-hairline2)' }} className="font-semibold">
                <td className="py-2 px-1.5">Total</td>
                <td className="py-2 px-1.5 text-right iq-num">{fmtCount(p.totals?.matches)}</td>
                <td className="py-2 px-1.5 text-right iq-num">{fmtCount(p.totals?.runs)}</td>
                <td className="py-2 px-1.5 text-right iq-num">{a2(p.totals?.average)}</td>
                <td className="py-2 px-1.5 text-right iq-num">{p.totals?.high_score ?? '—'}</td>
                <td className="py-2 px-1.5 text-right iq-num">{p.totals?.fifties || 0}/{p.totals?.hundreds || 0}</td>
                {showBowl && <>
                  <td className="py-2 px-1.5 text-right iq-num">{fmtCount(p.totals?.wickets)}</td>
                  <td className="py-2 px-1.5 text-right iq-num">{a2(p.totals?.bowling_average)}</td>
                  <td className="py-2 px-1.5 text-right iq-num">{a2(p.totals?.economy)}</td>
                </>}
                <td className="py-2 px-1.5 text-right iq-num">{fmtCount(p.totals?.catches)}</td>
              </tr>
            </tbody>
          </table>
          <Note>Season totals straight from Cricket Australia, for this club only — seasons at a previous club won't show here.</Note>
        </div>
      )}
    </Card>
  )
}

function PlayerDeepDive({ orgGuid, playerId, playerName, clubName }) {
  const data = usePolledScout(
    () => api.iqPlayerDeep({ org: orgGuid, player: playerId, playerName, clubName }),
    [orgGuid, playerId],
  )
  if (!data || data.status === 'building') {
    return (
      <Card eyebrow="deep dive · building" title="How he plays">
        <HistoryBuilding expectedMs={90000}>Scanning their recent scorecards for dismissal patterns and batting positions — a minute or two the first time, then cached for a week. The rest of the profile is ready now.</HistoryBuilding>
      </Card>
    )
  }
  if (data.status === 'error') {
    return <Card eyebrow="deep dive" title="How he plays"><Note>Couldn't run the deep scan just now — try again shortly.</Note></Card>
  }
  if (data.status === 'unavailable') return null
  if (!data.batting && !data.bowling) {
    return (
      <Card eyebrow="deep dive · recent seasons" title="How he plays">
        <Note>None of the scorecards we scanned ({data.coverage?.scorecards ?? 0}) had this player on a team sheet — the career table above still stands.</Note>
      </Card>
    )
  }
  const b = data.batting
  const bw = data.bowling
  const conv = b?.conversion
  const bandsMax = Math.max(1, ...(b?.bands || []).map(x => x.count))
  return (
    <div className="space-y-5">
      {data.summary && (
        <Card accent eyebrow="deep dive · recent seasons" title="How he plays">
          <div className="text-[14px] leading-relaxed" style={{ color: 'var(--pb-accent)' }}>{data.summary}</div>
        </Card>
      )}
      <div className="grid gap-5 lg:grid-cols-2 items-start">
        {b?.dismissals?.length > 0 && (
          <Card eyebrow="recent seasons" title="How he gets out">
            <StackedBar data={b.dismissals.map(d => ({ type: d.type, count: d.count, pct: d.pct }))} />
          </Card>
        )}
        {b?.by_position?.length > 0 && (
          <Card eyebrow="recent seasons" title="By batting position">
            <div className="space-y-2">
              {b.by_position.map(p => (
                <div key={p.bucket} className="flex items-center justify-between gap-3 text-[13px]">
                  <span className="font-medium">{p.bucket}</span>
                  <span className="iq-num text-pb-dim whitespace-nowrap">{p.innings} inns · {fmtCount(p.runs)} runs{p.average != null ? ` @ ${a2(p.average)}` : ''}</span>
                </div>
              ))}
            </div>
          </Card>
        )}
        {conv && b?.innings_count >= 5 && (
          <Card eyebrow="recent seasons" title="Starts & conversion">
            <div className="grid grid-cols-3 gap-4">
              <Stat label="Reaches 25" value={conv.start_pct != null ? `${conv.start_pct}%` : '—'} count={false} />
              <Stat label="25 → 50" value={conv.fifty_conv_pct != null ? `${conv.fifty_conv_pct}%` : '—'} count={false} />
              <Stat label="50 → 100" value={conv.hundred_conv_pct != null ? `${conv.hundred_conv_pct}%` : '—'} count={false} />
            </div>
            {b?.bands?.length > 0 && (
              <div className="space-y-1.5 mt-4">
                {b.bands.map((band, i) => (
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
        {bw && bw.wickets > 0 && (
          <Card eyebrow="recent seasons" title="Bowling by year">
            <div className="overflow-x-auto iq-scroll -mx-1">
              <table className="w-full text-[13px]">
                <thead><tr className="iq-eyebrow text-left" style={{ fontSize: 9.5 }}>
                  <th className="py-1.5 px-1.5 font-medium">Year</th>
                  <th className="py-1.5 px-1.5 font-medium text-right">Ov</th>
                  <th className="py-1.5 px-1.5 font-medium text-right">Wkts</th>
                  <th className="py-1.5 px-1.5 font-medium text-right">Avg</th>
                  <th className="py-1.5 px-1.5 font-medium text-right">Econ</th>
                </tr></thead>
                <tbody>
                  {(bw.by_year || []).map(y => (
                    <tr key={y.year} style={{ borderTop: '1px solid var(--pb-hairline)' }}>
                      <td className="py-2 px-1.5 iq-num font-medium">{y.year}</td>
                      <td className="py-2 px-1.5 text-right iq-num text-pb-faint">{fmtOvers(y.overs)}</td>
                      <td className="py-2 px-1.5 text-right iq-num font-semibold">{fmtCount(y.wickets)}</td>
                      <td className="py-2 px-1.5 text-right iq-num">{a2(y.average)}</td>
                      <td className="py-2 px-1.5 text-right iq-num text-pb-faint">{a2(y.economy)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {bw.best && <div className="text-pb-faint text-[12px] mt-3 iq-num">Best in window: {bw.best}</div>}
            {bw.dismissals?.length > 0 && (
              <div className="mt-4 pt-4" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
                <div className="iq-eyebrow mb-2">How he takes wickets</div>
                <div className="flex flex-wrap gap-2">
                  {bw.dismissals.map((d, i) => (
                    <span key={i} className="text-[12px] px-2.5 py-1 capitalize" style={{ background: 'var(--pb-surface2)', borderRadius: 99 }}>
                      {d.type} <span className="iq-num text-pb-faint">{d.count}{d.pct != null ? ` · ${d.pct}%` : ''}</span>
                    </span>
                  ))}
                </div>
                {bw.quality && (
                  <div className="text-pb-faint text-[12px] mt-3 iq-num">
                    Removes set batters {bw.quality.set_pct}% of the time · avg scalp {a2(bw.quality.scalp_value)} runs{bw.quality.ducks ? ` · ${bw.quality.ducks} duck${bw.quality.ducks === 1 ? '' : 's'}` : ''}
                  </div>
                )}
              </div>
            )}
          </Card>
        )}
      </div>
      {b?.recent?.length > 0 && (
        <Card eyebrow="most recent first" title="Recent innings">
          <div className="overflow-x-auto iq-scroll -mx-1">
            <table className="w-full text-[13px]">
              <thead><tr className="iq-eyebrow text-left" style={{ fontSize: 9.5 }}>
                <th className="py-1.5 px-1.5 font-medium">Date</th>
                <th className="py-1.5 px-1.5 font-medium text-right">Score</th>
                <th className="py-1.5 px-1.5 font-medium">vs</th>
                <th className="py-1.5 px-1.5 font-medium">Grade</th>
                <th className="py-1.5 px-1.5 font-medium">Out</th>
              </tr></thead>
              <tbody>
                {b.recent.map((inn, i) => (
                  <tr key={i} style={{ borderTop: '1px solid var(--pb-hairline)' }}>
                    <td className="py-2 px-1.5 iq-num whitespace-nowrap text-pb-faint">{inn.date || '—'}</td>
                    <td className="py-2 px-1.5 text-right iq-num font-semibold whitespace-nowrap">{inn.runs}{inn.not_out ? '*' : ''}{inn.balls ? <span className="text-pb-faintest font-normal"> ({inn.balls})</span> : null}</td>
                    <td className="py-2 px-1.5 truncate max-w-[160px]">{inn.vs || '—'}</td>
                    <td className="py-2 px-1.5 text-pb-faint truncate max-w-[140px]">{inn.grade || '—'}</td>
                    <td className="py-2 px-1.5 text-pb-faint text-[11.5px] capitalize">{inn.not_out ? 'not out' : (inn.dismissal || '—')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {data.coverage?.notes?.length > 0 && <Note>{data.coverage.notes.join(' ')}</Note>}
    </div>
  )
}

/* The full per-player profile. */
export function OppPlayerDetail({ entry, enriched, opponentName, playerId, tag, onSaveTag, dossierBatting = [], dossierBowling = [], orgGuid = null }) {
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
  // Scoring zones (where he scores) is a batting feature — show only for players
  // who've batted (or who already have zones plotted); a pure bowler skips it.
  const batted = !!(bat && bat.innings > 0)
  const hasScoringZones = Array.isArray(tag?.scoring_zones) && tag.scoring_zones.some(v => Number(v) > 0)
  const showZones = showCard && (batted || hasScoringZones)
  // Held dismissal mix → blended into the batting "DNA" read on the scouting card.
  const scoutStats = { dismissals: (dism || []).map(([type, count]) => ({ type, count })) }

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

      {/* Plan / key note from enrichment */}
      {(enriched?.key_note || enriched?.plan) && (
        <Card accent eyebrow="scouting read" title="The plan">
          {enriched?.key_note && <div className="text-[14px]" style={{ color: 'var(--pb-accent)' }}>{enriched.key_note}</div>}
          {enriched?.plan && <div className="text-[13px] mt-2 text-pb-dim">Plan: {enriched.plan}</div>}
        </Card>
      )}

      {/* Signature viz: radar (bat/bowl) + scout-entered scoring zones */}
      <div className="grid gap-5 lg:grid-cols-2 items-start">
        <OppRadarCard entry={entry} batPeers={dossierBatting} bowlPeers={dossierBowling} prefer={isBowler ? 'bowl' : 'bat'} />
        {showZones && <ZonesEditor playerId={playerId} name={entry.name} tag={tag} battingHand={battingHand} onSave={onSaveTag} />}
      </div>

      {/* Stat clusters */}
      <div className="grid gap-5 lg:grid-cols-2 items-start">
        {bat && bat.innings > 0 && (
          <Card eyebrow="this season" title="Batting">
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
        {bowl && bowl.wickets > 0 && (
          <Card eyebrow="this season" title="Bowling">
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
        {dism?.length > 0 && (
          <Card eyebrow="dismissal patterns" title="How he gets out">
            <StackedBar data={dism.map(([type, count]) => ({ type, count, pct: dismTotal ? Math.round((count / dismTotal) * 100) : 0 }))} />
          </Card>
        )}
      </div>

      {/* Record vs us — batting + bowling */}
      {(bat?.vs_us || bowl?.vs_us) && (
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
      )}

      {!bat?.innings && !bowl?.wickets && (
        <Note>{orgGuid
          ? 'Not seen in the current-season matches we scanned — their season history below is the read.'
          : 'No current-season scorecard data for this player yet — only their scouting tags below apply.'}</Note>
      )}

      {/* Scouting card — the ball-level read CA can't give us: how to get him out
          (batting) and how to play him (bowling), scout-entered, blended with the
          dismissal mix we do hold. */}
      {showCard && (
        <ScoutingCard keyId={playerId}
          batting={tag?.batting_intel} bowling={tag?.bowling_intel}
          stats={scoutStats} defaultSide={isBowler ? 'bowl' : 'bat'}
          onSave={(body) => onSaveTag(playerId, { ...body, player_name: entry.name })} />
      )}

      {/* 5-year history — career aggregates first (near-instant), then the
          scorecard deep pass (built in the background, cached a week). Renders
          for any club with a CA org GUID, played before or not. */}
      {orgGuid && playerId && (
        <>
          <PlayerCareerCard orgGuid={orgGuid} playerId={playerId} clubName={opponentName} />
          <PlayerDeepDive orgGuid={orgGuid} playerId={playerId} playerName={entry.name} clubName={opponentName} />
        </>
      )}

      {/* Editable scouting tags */}
      {playerId && onSaveTag && <ScoutingTags playerId={playerId} name={entry.name} tag={tag} onSave={onSaveTag} />}
    </div>
  )
}
