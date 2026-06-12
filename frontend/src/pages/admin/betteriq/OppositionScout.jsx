/* BetterIQ — Opposition Scout (the flagship screen).
 *
 * Picker (upcoming fixtures + searchable opponent list) → a two-phase report:
 *   1. an INSTANT report from data we already hold (head-to-head, our record vs
 *      them, last meeting, by-venue, bowler×batter match-ups), shown immediately;
 *   2. a LIVE dossier (opponent squad + form + game plan + danger players),
 *      built on demand and polled until status === 'ready'.
 *
 * The high-fidelity v2 design is applied throughout, while the real wiring is
 * preserved verbatim: URL params (?fixture / ?opponent), dossier polling,
 * team/grade narrowing, opponent match-to-club, and the per-player scouting
 * tags surfaced through OppPlayerProfile.
 */
import { useState, useEffect, useRef, useMemo } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import IQLayout from '../../../components/admin/IQLayout'
import { api } from '../../../lib/api'
import {
  Icon, Bar, Gauge, ResultPills, SplitBar, StackedBar, Heatmap,
  Card, Stat, Note, Tag, Btn, Segmented, Search, Empty, PageIntro, a2,
  LoadingBar, LoadingCard,
  fmtCount, fmtOvers, runsPhrase, wktsPhrase,
} from './ui'
import { Radar, BAT_AXES, BOWL_AXES, PhaseStrip, buildRadar } from './viz'
import KeyPlayersCard from './KeyPlayersCard'
import AnyClubSearch from './AnyClubSearch'
import { OppPlayerDetail, buildOppPlayerIndex } from './OppPlayerProfile'
import { useClubPlayers, careerOnlyEntries, entryWithThreat } from './clubPlayers'
import { useIQFilter, seasonIdsInRange, seasonLabel } from './Context'
import Dropdown from '../../../components/Dropdown'

const POLL_MS = 2500
const num = (v, d = '—') => (v === null || v === undefined ? d : v)

/* ── Picker ──────────────────────────────────────────────────────────────── */

function ScoutPicker({ data, onPick, onMatch }) {
  const [q, setQ] = useState('')
  const opponents = data?.opponents || []
  const upcoming = data?.upcoming || []
  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase()
    return t ? opponents.filter(o => (o.name || '').toLowerCase().includes(t)) : opponents
  }, [q, opponents])

  return (
    <div className="iq-fade">
      <PageIntro>Pick an upcoming fixture, a club you've met, or search any club in the country — we'll pull a broadcast-grade scouting report from your scorecards and their live form.</PageIntro>

      {upcoming.length > 0 && (
        <>
          <div className="iq-eyebrow mb-3">Upcoming</div>
          <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-4 mb-9">
            {upcoming.slice(0, 8).map((fx, i) => (
              <div key={fx.fixture_id} className="iq-card text-left p-4 transition iq-rise" style={{ animationDelay: `${i * 55}ms` }}>
                <div className="flex items-center justify-between gap-2">
                  <span className="iq-mono uppercase tracking-wider text-pb-faint" style={{ fontSize: 10 }}>{fx.played_on || ''}</span>
                  {fx.opp_key
                    ? <Tag tone={fx.coverage === 'rich' ? 'accent' : 'faint'}>{fx.coverage === 'rich' ? 'History' : 'Partial'}</Tag>
                    : <Tag tone="faint">Not linked</Tag>}
                </div>
                <div className="iq-display font-bold text-[18px] mt-2.5 truncate">{fx.opponent_name}</div>
                <div className="text-pb-faint text-[12px] mt-1 truncate">{[fx.home_away, fx.venue].filter(Boolean).join(' · ') || '—'}</div>
                {fx.opp_key ? (
                  <Btn variant="soft" sm icon="arrow" className="mt-3 w-full"
                    onClick={() => onPick({ fixtureId: fx.fixture_id, opponent: fx.opp_key, name: fx.opponent_name })}>Scout</Btn>
                ) : (
                  <div className="flex gap-1.5 mt-3">
                    <Btn variant="soft" sm icon="search" onClick={() => onMatch(fx)}>Match club</Btn>
                    <Btn variant="ghost" sm onClick={() => onPick({ fixtureId: fx.fixture_id, name: fx.opponent_name })}>New</Btn>
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {/* Scout ANY club — the whole CA registry, not just clubs in our history.
          Relegated into a new grade, a different association, never met them:
          all scoutable from the org GUID alone. */}
      <div className="iq-eyebrow mb-3">Scout any club</div>
      <div className="iq-card p-4 mb-9">
        <div className="text-pb-faint text-[12.5px] mb-3 leading-relaxed">
          Never played them? Search every club on PlayHQ — new opposition after relegation or promotion,
          a side from another association, anyone. We'll build their squad and form live, with a
          five-year history for any of their players.
        </div>
        <AnyClubSearch className="max-w-md" onPick={(org) => onPick({ opponent: org.id, name: org.name })} />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <div className="iq-eyebrow">All opponents ({opponents.length})</div>
        <Search value={q} onChange={setQ} placeholder="Search opponents…" className="w-full max-w-xs" />
      </div>
      {filtered.length === 0 ? (
        <Empty>No opponents found{q ? ` for “${q}”` : ' yet — play some games or sync history'}.</Empty>
      ) : (
        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((o, i) => (
            <button key={o.opp_key} onClick={() => onPick({ opponent: o.opp_key, name: o.name })}
              className="iq-card text-left px-4 py-3.5 transition flex items-center justify-between gap-2 iq-rise"
              style={{ animationDelay: `${i * 24}ms` }}
              onMouseEnter={e => e.currentTarget.style.borderColor = 'color-mix(in srgb, var(--pb-accent) 45%, transparent)'}
              onMouseLeave={e => e.currentTarget.style.borderColor = ''}>
              <div className="min-w-0">
                <div className="iq-display font-semibold truncate">{o.name}</div>
                <div className="text-pb-faint text-[11.5px] mt-0.5 iq-num">{o.meetings} meetings{o.last_played ? ` · last ${o.last_played.slice(0, 4)}` : ''}</div>
              </div>
              {o.coverage === 'rich' && <Tag tone="accent">Synced</Tag>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/* ── Command strip — the instant report hero ─────────────────────────────── */

/* The scope toggle on the record card — All-time / Season / Grade. Reflects the
   top filter bar's season + grade so the user can flip the record (and our
   record / bowler match-ups) between the impressive all-time number and the
   selected slice, without it silently overriding the headline. */
function ScopeToggle({ scope, onScope, options }) {
  if (options.length < 2) return null
  return <Segmented sm value={scope} onChange={onScope} options={options} />
}

function CommandStrip({ h2h, lm, scope, onScope, scopeOptions, filterLabel }) {
  const drawn = (h2h?.draws || 0) + (h2h?.ties || 0)
  const lmColor = lm?.result === 'WIN' ? 'var(--pb-brand)' : lm?.result === 'LOSS' ? 'var(--pb-red)' : 'var(--pb-amber)'
  const eyebrow = scope === 'selected' ? `Record · ${filterLabel}` : 'All-time record'

  // No history at all (unfiltered) → render nothing; the page's empty states cover it.
  if ((!h2h || !h2h.meetings) && scope === 'all') return null
  // Filtered to nothing → keep the card (and the toggle) so the user can switch back.
  if (!h2h || !h2h.meetings) {
    return (
      <div className="iq-card iq-accent-card overflow-hidden iq-rise p-6 md:p-7">
        <div className="iq-eyebrow mb-3 flex flex-wrap items-center justify-between gap-2">
          <span>{eyebrow}</span><ScopeToggle scope={scope} onScope={onScope} options={scopeOptions} />
        </div>
        <Empty>No meetings for {filterLabel} — switch to All-time.</Empty>
      </div>
    )
  }
  return (
    <div className="iq-card iq-accent-card overflow-hidden iq-rise">
      <div className="relative grid lg:grid-cols-[auto_1fr_auto]">
        {/* Gauge */}
        <div className="flex flex-col items-center justify-center p-6 md:p-7 lg:border-r" style={{ borderColor: 'var(--pb-hairline)' }}>
          <Gauge value={h2h.win_pct ?? 0} size={138} label="Win rate" color="var(--pb-accent)" />
          <div className="text-pb-faint text-[11.5px] mt-2 iq-num">{h2h.meetings} meetings</div>
        </div>
        {/* W-L-D */}
        <div className="p-6 md:p-7 flex flex-col justify-center">
          <div className="iq-eyebrow mb-3 flex flex-wrap items-center justify-between gap-2">
            <span>{eyebrow}</span><ScopeToggle scope={scope} onScope={onScope} options={scopeOptions} />
          </div>
          <div className="flex items-end gap-6">
            <Stat label="Won" value={h2h.wins} tone="win" big />
            <Stat label="Lost" value={h2h.losses} tone="loss" big />
            <Stat label="Drawn" value={drawn} tone="draw" big />
          </div>
          <div className="mt-4 max-w-md">
            <SplitBar h={10} segments={[
              { label: 'Won', value: h2h.wins, color: 'var(--pb-brand)' },
              { label: 'Lost', value: h2h.losses, color: 'var(--pb-red)' },
              { label: 'Drawn', value: drawn, color: 'var(--pb-amber)' },
            ]} />
          </div>
          <div className="flex flex-wrap items-center gap-3 mt-5">
            <span className="iq-eyebrow">Home {h2h.home?.wins ?? 0}/{h2h.home?.played ?? 0}</span>
            <span className="iq-eyebrow">Away {h2h.away?.wins ?? 0}/{h2h.away?.played ?? 0}</span>
            {h2h.recent_form?.length > 0 && (
              <>
                <span className="iq-eyebrow ml-1">Recent</span>
                <ResultPills form={h2h.recent_form} size={22} />
                <span className="text-pb-faint text-[11.5px]">most recent right</span>
              </>
            )}
          </div>
        </div>
        {/* Last meeting */}
        {lm && (
          <div className="p-6 md:p-7 lg:border-l flex flex-col justify-center"
            style={{ borderColor: 'var(--pb-hairline)', background: 'color-mix(in srgb, var(--pb-accent) 4%, transparent)', minWidth: 220 }}>
            <div className="flex items-center justify-between gap-2"><div className="iq-eyebrow">Last meeting</div><span className="text-pb-faint text-[11px]">{lm.played_at || ''}</span></div>
            <div className="iq-headline mt-2.5" style={{ fontSize: 30, color: lmColor }}>{lm.result || '—'}</div>
            <div className="iq-num text-pb-dim text-[13px] mt-1">{num(lm.our_runs)} vs {num(lm.opp_runs)}</div>
            {lm.venue && <div className="text-[11.5px] text-pb-faintest mt-0.5">{lm.venue}</div>}
            {(lm.our_top_bat || lm.our_top_bowl) && (
              <div className="mt-3 pt-3 space-y-1 text-[12.5px]" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
                {lm.our_top_bat && <div><span className="text-pb-faint">Top bat:</span> {lm.our_top_bat.name} <span className="iq-num font-semibold">{fmtCount(lm.our_top_bat.runs)}</span></div>}
                {lm.our_top_bowl && <div><span className="text-pb-faint">Top bowl:</span> {lm.our_top_bowl.name} <span className="iq-num font-semibold">{lm.our_top_bowl.wickets}/{lm.our_top_bowl.runs}</span></div>}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

/* ── Recent meetings (instant) ───────────────────────────────────────────── */

function RecentMeetings({ recent }) {
  if (!recent?.length) return null
  const pill = (r) => {
    const c = r === 'WIN' ? 'var(--pb-brand)' : r === 'LOSS' ? 'var(--pb-red)' : 'var(--pb-amber)'
    return <span className="iq-mono inline-flex items-center justify-center font-bold" style={{ width: 20, height: 20, fontSize: 10, borderRadius: 5, color: c, background: `color-mix(in srgb, ${c} 16%, transparent)` }}>{(r || '·')[0]}</span>
  }
  return (
    <Card eyebrow="head-to-head" title="Recent meetings">
      <div className="overflow-x-auto iq-scroll -mx-1">
        <table className="w-full text-[13px]">
          <thead><tr className="iq-eyebrow text-left" style={{ fontSize: 9.5 }}>
            <th className="py-1.5 px-1 font-medium">Date</th>
            <th className="py-1.5 px-1 font-medium">Grade</th>
            <th className="py-1.5 px-1 font-medium">H/A</th>
            <th className="py-1.5 px-1 font-medium">Result</th>
          </tr></thead>
          <tbody>
            {recent.map((m, i) => (
              <tr key={i} style={{ borderTop: '1px solid var(--pb-hairline)' }}>
                <td className="py-2 px-1 iq-num whitespace-nowrap">{m.played_at || '—'}</td>
                <td className="py-2 px-1 text-pb-faint truncate max-w-[160px]">{m.grade_name || '—'}</td>
                <td className="py-2 px-1 iq-mono text-[11px]">{m.our_venue || '—'}</td>
                <td className="py-2 px-1">{m.result ? pill(m.result) : '—'}<span className="text-pb-faint text-[11.5px] ml-1.5">{m.winning_team || ''}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

/* ── Game plan (synthesis, from dossier + the instant report's edge) ─────── */

function PlanTile({ label, name, sub, tone }) {
  const color = tone === 'remove' ? 'var(--pb-red)' : tone === 'see' ? 'var(--pb-amber)' : 'var(--pb-brand)'
  return (
    <div className="p-4" style={{ background: 'var(--pb-surface2)', borderRadius: 12, border: '1px solid var(--pb-hairline)' }}>
      <div className="iq-eyebrow" style={{ color }}>{label}</div>
      <div className="iq-display font-bold text-[16px] mt-2 truncate">{name || '—'}</div>
      {sub && <div className="text-pb-faint text-[11.5px] mt-1 leading-snug">{sub}</div>}
    </div>
  )
}

function GamePlan({ plan, report }) {
  if (!plan) return null
  const h2h = report?.head_to_head
  const ourBat = report?.our_performers?.batting?.[0]
  const ourBowl = report?.our_performers?.bowling?.[0]
  const bestVenue = (report?.venues || []).filter(v => v.wins > (v.losses || 0)).sort((a, b) => b.played - a.played)[0]
  return (
    <Card accent eyebrow="The game plan" title="How to beat them" right={<Tag tone="accent">Synthesised</Tag>}>
      {plan.one_liner && (
        <div className="iq-display font-bold leading-snug mb-5" style={{ fontSize: 'clamp(18px,2.2vw,24px)', letterSpacing: '-0.01em', maxWidth: 640 }}>{plan.one_liner}</div>
      )}
      <div className="grid sm:grid-cols-3 gap-3 mb-5">
        <PlanTile label="Remove early" tone="remove" name={plan.remove_early?.name} sub={plan.remove_early?.why} />
        <PlanTile label="See off" tone="see" name={plan.see_off?.name} sub={plan.see_off?.why} />
        <PlanTile label="Target" tone="target" name={plan.target_bowler?.name || 'No clear weak link'}
          sub={plan.target_bowler ? `leaks at econ ${a2(plan.target_bowler.economy)}` : 'nobody’s really leaking'} />
      </div>
      <div className="space-y-2 text-[13.5px]">
        {plan.key_warning && (
          <div className="flex gap-2.5"><Icon name="info" size={16} className="mt-0.5 shrink-0" style={{ color: 'var(--pb-red)' }} />
            <span><span className="text-pb-faint">Watch:</span> {plan.key_warning}</span></div>
        )}
        {h2h?.meetings ? (
          <div className="flex gap-2.5"><Icon name="info" size={16} className="mt-0.5 shrink-0 text-pb-faint" />
            <span><span className="text-pb-faint">Record vs them:</span> {h2h.wins}–{h2h.losses}{bestVenue ? ` · strongest at ${bestVenue.venue}` : ''}</span></div>
        ) : null}
        {(ourBat || ourBowl) && (
          <div className="flex gap-2.5"><Icon name="check" size={16} className="mt-0.5 shrink-0" style={{ color: 'var(--pb-brand)' }} />
            <span><span className="text-pb-faint">Our edge:</span> {ourBat ? `${ourBat.name} (${runsPhrase(ourBat.runs, ourBat.average)})` : ''}{ourBat && ourBowl ? ', ' : ''}{ourBowl ? `${ourBowl.name} (${wktsPhrase(ourBowl.wickets, ourBowl.average)})` : ''} — own this match-up.</span></div>
        )}
      </div>
      <Note>Synthesised from scorecards — a starting plan, not gospel.</Note>
    </Card>
  )
}

/* ── Innings phases (estimated, from ball-by-ball games) ──────────────────── */
/* Only recent live-scored games carry ball-by-ball data; older games are
   scorecard-only. The endpoint reports `available:false` when there's nothing
   to break down, in which case we render nothing. */
function InningsPhases({ selected }) {
  const [ph, setPh] = useState(null)
  useEffect(() => {
    setPh(null)
    if (!selected) return
    let alive = true
    api.iqOppositionPhases({ opponent: selected.opponent, fixtureId: selected.fixtureId })
      .then(d => { if (alive) setPh(d) })
      .catch(() => { if (alive) setPh(null) })
    return () => { alive = false }
  }, [selected])
  if (!ph?.available) return null
  return (
    <Card eyebrow="per-innings averages · estimated" title="How they pace an innings"
      right={ph.innings ? <Tag tone="faint">{ph.innings} inns{ph.total != null ? ` · ${ph.total} games` : ''}</Tag> : null}>
      <div className="text-pb-faint text-[12px] mb-4 leading-relaxed">
        Average <span className="text-pb-dim">run rate</span> in each third of their innings, from recent ball-by-ball games — where they accelerate and where they can be squeezed.
      </div>
      <PhaseStrip phases={ph.phases} />
      {ph.insight && (
        <div className="flex gap-2.5 text-[13px] mt-4 leading-relaxed">
          <Icon name="info" size={15} className="mt-0.5 shrink-0" style={{ color: 'var(--pb-accent)' }} />
          <span className="text-pb-dim">{ph.insight}</span>
        </div>
      )}
      {ph.note && <Note>{ph.note}</Note>}
    </Card>
  )
}

/* ── Threat radars — top danger batter & bowler, normalised vs their squad ─── */
/* Opponent stats live only in the live dossier (not our DB), so we build the
   0–100 axes client-side from the dossier squad arrays with buildRadar — the
   peer group is the dossier's own batting/bowling list. */
const surname = (name) => (name || '').trim().split(/\s+/).slice(-1)[0] || name

const BAT_RADAR_AXES = [
  { label: 'Volume', value: p => p.runs },
  { label: 'Average', value: p => p.average },
  { label: 'Strike rate', value: p => p.strike_rate },
  { label: 'Conversion', value: p => ((p.fifties || 0) + (p.hundreds || 0)) / Math.max(p.innings || 1, 1) },
  { label: 'Big score', value: p => p.high_score },
  { label: 'vs us', value: p => p.vs_us?.runs || 0 },
]
const BOWL_RADAR_AXES = [
  { label: 'Wickets', value: p => p.wickets },
  { label: 'Average', value: p => p.average, lower: true },
  { label: 'Economy', value: p => p.economy, lower: true },
  { label: 'Best', value: p => parseInt(String(p.best || '0/0')) },
  { label: 'vs us', value: p => p.vs_us?.wickets || 0 },
  { label: 'Workload', value: p => p.overs },
]

function ThreatRadars({ dossier }) {
  const batList = dossier.batting || []
  const bowlList = dossier.bowling || []
  const dBat = (dossier.danger_batters || [])[0]
  const dBowl = (dossier.danger_bowlers || [])[0]
  const batTarget = dBat ? (batList.find(p => p.player_id === dBat.player_id) || dBat) : null
  const bowlTarget = dBowl ? (bowlList.find(p => p.player_id === dBowl.player_id) || dBowl) : null

  const cards = []
  if (batList.length && batTarget) cards.push({ key: 'bat', name: batTarget.name, tag: 'Danger batter', radar: buildRadar(batList, BAT_RADAR_AXES, batTarget) })
  if (bowlList.length && bowlTarget) cards.push({ key: 'bowl', name: bowlTarget.name, tag: 'Danger bowler', radar: buildRadar(bowlList, BOWL_RADAR_AXES, bowlTarget) })
  if (!cards.length) return null

  return (
    <Card eyebrow="threat profiles vs their squad" title="Threat profiles">
      <div className="grid gap-6 sm:grid-cols-2">
        {cards.map(c => (
          <div key={c.key} className="flex flex-col items-center">
            <div className="text-center mb-1"><div className="iq-display font-bold text-[15px]">{surname(c.name)}</div><div className="iq-eyebrow">{c.tag}</div></div>
            <Radar axes={c.radar.axes} values={c.radar.values} baseline={c.radar.baseline} size={236} color="var(--pb-red)" />
          </div>
        ))}
      </div>
      <Note>Each axis normalised 0–100 against this squad's average (dashed ring). The further the shape reaches, the bigger the threat.</Note>
    </Card>
  )
}

/* ── Our record + venue (instant) ────────────────────────────────────────── */

function OurRecord({ performers }) {
  const bat = performers?.batting || []
  const bowl = performers?.bowling || []
  if (!bat.length && !bowl.length) return null
  return (
    <Card eyebrow="selection intel" title="Our record against them">
      <div className="grid gap-5 sm:grid-cols-2">
        <div>
          <div className="iq-eyebrow mb-2.5">Bat well vs them</div>
          <div className="space-y-2">
            {bat.length ? bat.slice(0, 6).map(p => (
              <div key={p.player_id} className="flex items-center justify-between gap-3">
                <span className={`text-[13.5px] whitespace-nowrap ${p.active ? '' : 'text-pb-faint'}`}>{p.name}{!p.active && ' ·'}</span>
                <span className="iq-num text-pb-dim text-[12.5px] whitespace-nowrap shrink-0">{runsPhrase(p.runs, p.average)}</span>
              </div>
            )) : <Empty>—</Empty>}
          </div>
        </div>
        <div>
          <div className="iq-eyebrow mb-2.5">Bowl well vs them</div>
          <div className="space-y-2">
            {bowl.length ? bowl.slice(0, 6).map(p => (
              <div key={p.player_id} className="flex items-center justify-between gap-3">
                <span className={`text-[13.5px] whitespace-nowrap ${p.active ? '' : 'text-pb-faint'}`}>{p.name}{!p.active && ' ·'}</span>
                <span className="iq-num text-pb-dim text-[12.5px] whitespace-nowrap shrink-0">{wktsPhrase(p.wickets, p.average)}</span>
              </div>
            )) : <Empty>—</Empty>}
          </div>
        </div>
      </div>
      <div className="text-pb-faintest text-[11px] mt-4">· = no longer active</div>
    </Card>
  )
}

function VenueCard({ venues }) {
  if (!venues?.length) return null
  return (
    <Card eyebrow="vs this opponent" title="By venue">
      <div className="space-y-3">
        {venues.map((v, idx) => {
          const losses = v.losses || 0
          const tone = v.wins > losses ? 'var(--pb-brand)' : v.wins < losses ? 'var(--pb-red)' : 'var(--pb-amber)'
          const pct = v.played ? (v.wins / v.played) * 100 : 0
          return (
            <div key={idx}>
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <span className="text-[13px] truncate">{v.venue}</span>
                <span className="iq-num text-[12.5px] whitespace-nowrap" style={{ color: tone }}>{v.wins}–{losses}<span className="text-pb-faintest">/{v.played}</span></span>
              </div>
              <Bar pct={pct} color={tone} h={6} delay={idx * 0.08} />
            </div>
          )
        })}
      </div>
    </Card>
  )
}

/* ── Bowler match-up heatmap (instant) ───────────────────────────────────── */

function Matchups({ matchups }) {
  const rows = matchups?.bowler_dominance || []
  const canMatrix = new Set(rows.map(r => r.bowler)).size >= 2 && new Set(rows.map(r => r.batter)).size >= 2
  const [view, setView] = useState('matrix')
  if (!rows.length) return null
  const showMatrix = canMatrix && view === 'matrix'
  return (
    <Card eyebrow="our hold over their batters" title="Bowler match-ups"
      right={canMatrix
        ? <Segmented sm value={view} onChange={setView} options={[{ value: 'matrix', label: 'Matrix' }, { value: 'list', label: 'List' }]} />
        : null}>
      <div className="text-pb-faint text-[12px] mb-3">Times our bowlers have dismissed their batters — a selection edge. Darker = stronger hold.</div>
      {showMatrix ? <Heatmap rows={rows} /> : (
        <div className="overflow-x-auto iq-scroll -mx-1">
          <table className="w-full text-[13px]">
            <thead><tr className="iq-eyebrow text-left" style={{ fontSize: 9.5 }}>
              <th className="py-1.5 px-1 font-medium">Our bowler</th>
              <th className="py-1.5 px-1 font-medium">Their batter</th>
              <th className="py-1.5 px-1 font-medium text-right">Out</th>
              <th className="py-1.5 px-1 font-medium">How</th>
              <th className="py-1.5 px-1 font-medium text-right">Runs off us</th>
            </tr></thead>
            <tbody>
              {rows.map((m, idx) => (
                <tr key={idx} style={{ borderTop: '1px solid var(--pb-hairline)' }}>
                  <td className="py-2 px-1 font-medium whitespace-nowrap">{m.bowler}{!m.active && <span className="text-pb-faint" title="no longer active"> ·</span>}</td>
                  <td className="py-2 px-1 whitespace-nowrap">{m.batter}</td>
                  <td className="py-2 px-1 text-right iq-num font-semibold">{m.dismissals}×</td>
                  <td className="py-2 px-1 text-pb-faint text-[11.5px] capitalize">{(m.how || []).join(', ') || '—'}</td>
                  <td className="py-2 px-1 text-right iq-num text-pb-faint">{fmtCount(m.runs_made)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

/* ── How they win / lose (dossier) ───────────────────────────────────────── */

function WinLose({ win, lose }) {
  if (!win?.length && !lose?.length) return null
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card eyebrow="patterns" title="How they win">
        {win?.length ? <ul className="space-y-2.5">{win.map((b, i) => <li key={i} className="flex gap-2.5 text-[13.5px] leading-snug"><span style={{ color: 'var(--pb-brand)' }}>▲</span><span>{b}</span></li>)}</ul> : <Empty>—</Empty>}
      </Card>
      <Card eyebrow="patterns" title="How they lose">
        {lose?.length ? <ul className="space-y-2.5">{lose.map((b, i) => <li key={i} className="flex gap-2.5 text-[13.5px] leading-snug"><span style={{ color: 'var(--pb-red)' }}>▼</span><span>{b}</span></li>)}</ul> : <Empty>—</Empty>}
      </Card>
    </div>
  )
}

/* ── Partnerships — where they wobble (dossier) ──────────────────────────── */

function Partnerships({ partnerships, insight }) {
  if (!partnerships?.length) return null
  const max = Math.max(1, ...partnerships.map(p => p.avg_partnership || 0))
  const ord = k => ({ 1: '1st', 2: '2nd', 3: '3rd' }[k] || `${k}th`)
  const anyWeak = partnerships.some(p => p.weak)
  return (
    <Card accent eyebrow="avg partnership by wicket" title="Where they build & wobble">
      <div className="space-y-2.5">
        {partnerships.map((p, idx) => {
          // `weak` = a genuine TOP/MIDDLE-order soft spot (backend-flagged); `tail`
          // = 8th wicket on, naturally low and never a real insight, so it's muted
          // rather than reddened (the old rule reddened every sub-20 stand).
          const barColor = p.weak ? 'var(--pb-red)' : p.tail ? 'var(--pb-hairline2)' : 'var(--pb-accent)'
          const valColor = p.weak ? 'var(--pb-red)' : p.tail ? 'var(--pb-faintest)' : 'var(--pb-text)'
          return (
            <div key={p.wicket} className="flex items-center gap-3 text-[13px]">
              <span className={`w-7 shrink-0 iq-mono text-[11px] ${p.tail ? 'text-pb-faintest' : 'text-pb-faint'}`}>{ord(p.wicket)}</span>
              <div className="flex-1"><Bar pct={(p.avg_partnership / max) * 100} color={barColor} h={9} delay={idx * 0.06} /></div>
              <span className="w-8 text-right iq-num shrink-0 font-semibold" style={{ color: valColor }}>{p.avg_partnership}</span>
            </div>
          )
        })}
      </div>
      {insight && <div className="text-pb-dim text-[12.5px] mt-4 leading-relaxed">{insight}</div>}
      {anyWeak && <Note>Red marks a genuine top/middle-order soft spot. The tail (8th wicket on) is greyed — a low last-wicket stand is normal, not a weakness.</Note>}
    </Card>
  )
}

/* ── Squad tables (dossier) ──────────────────────────────────────────────── */

/* "vs us" cells — runs bold, "@ avg" muted, full detail on hover. A dash when
   we've no record of facing them (was a cramped "142@35.5" before). */
function VsUsBat({ vs }) {
  if (!vs || !vs.innings) return <span className="text-pb-faintest">—</span>
  return (
    <span className="iq-num whitespace-nowrap"
      title={`${vs.innings} inns · ${runsPhrase(vs.runs)}${vs.high_score != null ? ` · HS ${vs.high_score}` : ''} against us`}>
      <span className="font-semibold">{fmtCount(vs.runs)}</span>
      <span className="text-pb-faint"> @ {a2(vs.average)}</span>
    </span>
  )
}
function VsUsBowl({ vs }) {
  if (!vs || !vs.wickets) return <span className="text-pb-faintest">—</span>
  return (
    <span className="iq-num whitespace-nowrap"
      title={`${wktsPhrase(vs.wickets, vs.average)}${vs.best ? ` · best ${vs.best}` : ''} against us`}>
      <span className="font-semibold">{wktsPhrase(vs.wickets)}</span>
      <span className="text-pb-faint"> @ {a2(vs.average)}</span>
    </span>
  )
}

function SquadTable({ dossier }) {
  const [tab, setTab] = useState('batting')
  const bat = dossier.batting || []
  const bowl = dossier.bowling || []
  return (
    <Card eyebrow={dossier.selected_team_name ? `squad · ${dossier.selected_team_name}` : 'squad'} title="Their squad"
      right={<Segmented sm value={tab} onChange={setTab} options={[{ value: 'batting', label: 'Batting' }, { value: 'bowling', label: 'Bowling' }]} />}>
      <div className="overflow-x-auto iq-scroll -mx-1">
        {tab === 'batting' ? (
          bat.length === 0 ? <Empty>No batting data found.</Empty> : (
            <table className="w-full text-[13px]">
              <thead><tr className="iq-eyebrow text-left" style={{ fontSize: 9.5 }}>
                <th className="py-2 px-1.5 font-medium">Batter</th><th className="py-2 px-1.5 font-medium text-right">Inns</th><th className="py-2 px-1.5 font-medium text-right">Runs</th>
                <th className="py-2 px-1.5 font-medium text-right">Avg</th><th className="py-2 px-1.5 font-medium text-right">SR</th><th className="py-2 px-1.5 font-medium text-right">HS</th>
                <th className="py-2 px-1.5 font-medium text-right">50/100</th><th className="py-2 px-1.5 font-medium text-right">vs us</th>
              </tr></thead>
              <tbody>
                {bat.map(p => (
                  <tr key={p.player_id} style={{ borderTop: '1px solid var(--pb-hairline)' }} className="transition-colors hover:bg-pb-surface2">
                    <td className="py-2.5 px-1.5 font-medium whitespace-nowrap">{p.name} {p.form === 'hot' && <Icon name="flame" size={13} className="inline" style={{ color: 'var(--pb-red)' }} />}</td>
                    <td className="py-2.5 px-1.5 text-right iq-num text-pb-faint">{fmtCount(p.innings)}</td>
                    <td className="py-2.5 px-1.5 text-right iq-num font-semibold">{fmtCount(p.runs)}</td>
                    <td className="py-2.5 px-1.5 text-right iq-num">{a2(p.average)}</td>
                    <td className="py-2.5 px-1.5 text-right iq-num text-pb-faint">{a2(p.strike_rate)}</td>
                    <td className="py-2.5 px-1.5 text-right iq-num">{fmtCount(p.high_score)}</td>
                    <td className="py-2.5 px-1.5 text-right iq-num text-pb-faint">{p.fifties}/{p.hundreds}</td>
                    <td className="py-2.5 px-1.5 text-right text-[11.5px]"><VsUsBat vs={p.vs_us} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        ) : (
          bowl.length === 0 ? <Empty>No bowling data found.</Empty> : (
            <table className="w-full text-[13px]">
              <thead><tr className="iq-eyebrow text-left" style={{ fontSize: 9.5 }}>
                <th className="py-2 px-1.5 font-medium">Bowler</th><th className="py-2 px-1.5 font-medium text-right">Ov</th><th className="py-2 px-1.5 font-medium text-right">Wkts</th>
                <th className="py-2 px-1.5 font-medium text-right">Avg</th><th className="py-2 px-1.5 font-medium text-right">Econ</th><th className="py-2 px-1.5 font-medium text-right">Best</th><th className="py-2 px-1.5 font-medium text-right">vs us</th>
              </tr></thead>
              <tbody>
                {bowl.map(p => (
                  <tr key={p.player_id} style={{ borderTop: '1px solid var(--pb-hairline)' }} className="transition-colors hover:bg-pb-surface2">
                    <td className="py-2.5 px-1.5 font-medium whitespace-nowrap">{p.name}</td>
                    <td className="py-2.5 px-1.5 text-right iq-num text-pb-faint">{fmtOvers(p.overs)}</td>
                    <td className="py-2.5 px-1.5 text-right iq-num font-semibold">{fmtCount(p.wickets)}</td>
                    <td className="py-2.5 px-1.5 text-right iq-num">{a2(p.average)}</td>
                    <td className="py-2.5 px-1.5 text-right iq-num text-pb-faint">{a2(p.economy)}</td>
                    <td className="py-2.5 px-1.5 text-right iq-num">{num(p.best)}</td>
                    <td className="py-2.5 px-1.5 text-right text-[11.5px]"><VsUsBowl vs={p.vs_us} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        )}
      </div>
    </Card>
  )
}

/* ── Opposition player scout — search any of their squad for a full profile ─ */

function OppPlayerScout({ dossier, tags, onSaveTag, orgGuid }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [sel, setSel] = useState(null)
  const ref = useRef(null)
  const index = useMemo(() => buildOppPlayerIndex(dossier), [dossier])
  const enriched = useMemo(() => {
    const m = new Map()
    for (const d of [...(dossier.danger_batters || []), ...(dossier.danger_bowlers || [])]) m.set(d.player_id, d)
    return m
  }, [dossier])
  // Current-season squad + everyone else CA's aggregates have seen at this
  // club in the last five years, so a player who hasn't appeared this season
  // is still searchable (their profile leans on the career/deep cards).
  const clubPlayers = useClubPlayers(orgGuid, dossier.opponent?.name)
  const careerOnly = useMemo(() => careerOnlyEntries(index, clubPlayers), [index, clubPlayers])
  const all = useMemo(() => [...index.entries()].map(([id, v]) => ({ id, ...v })), [index])
  const everyone = useMemo(() => [...all, ...careerOnly], [all, careerOnly])
  if (!everyone.length) return null
  const t = q.trim().toLowerCase()
  const matches = (t ? everyone.filter(p => p.name.toLowerCase().includes(t)) : everyone).slice(0, 30)
  const selected = sel ? entryWithThreat(index.get(sel) || careerOnly.find(p => p.id === sel) || null, dossier) : null
  return (
    <Card eyebrow="search anyone at this club" title="Scout a player">
      <div ref={ref} className="relative max-w-sm" onFocusCapture={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}>
        <Search value={q} onChange={(v) => { setQ(v); setOpen(true) }} placeholder="Search an opponent player…" className="w-full" />
        <Dropdown
          anchorRef={ref}
          open={open}
          onClose={() => setOpen(false)}
          maxHeight={288}
          className="iq-card p-1 iq-scroll shadow-lg"
          style={{ background: 'var(--pb-surface)' }}
        >
          {matches.length === 0 ? <div className="px-2.5 py-2 text-pb-faint text-sm">No match.</div> : matches.map(p => (
            <button key={p.id} type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => { setSel(p.id); setQ(''); setOpen(false) }}
              className="w-full flex items-center justify-between gap-3 px-2.5 py-1.5 rounded-lg hover:bg-pb-surface2 text-left">
              <span className="font-medium truncate">{p.name}</span>
              <span className="text-pb-faintest text-[11px] iq-num whitespace-nowrap">
                {p.careerOnly
                  ? `${p.career?.runs ? runsPhrase(p.career.runs, p.career.average) : ''}${p.career?.wickets ? ` · ${wktsPhrase(p.career.wickets)}` : ''}${(p.career?.runs || p.career?.wickets) ? ' · 5yr' : '5yr'}`
                  : `${p.bat?.runs ? runsPhrase(p.bat.runs, p.bat.average) : ''}${p.bowl?.wickets ? ` · ${wktsPhrase(p.bowl.wickets)}` : ''}`}
              </span>
            </button>
          ))}
        </Dropdown>
      </div>
      {selected
        ? <div className="mt-4"><OppPlayerDetail entry={selected} enriched={enriched.get(sel)} opponentName={dossier.opponent?.name} playerId={sel} tag={tags?.[sel]} onSaveTag={onSaveTag} orgGuid={orgGuid} /></div>
        : <div className="text-pb-faintest text-[12px] mt-3">Pick a player for their season form, dismissal patterns, five-year history, scouting tags and full record against us.</div>}
    </Card>
  )
}

/* ── match-to-club modal (unlinked fixture → known club) ─────────────────── */

function MatchOpponentModal({ opponents, fixture, onPick, onClose }) {
  const [q, setQ] = useState('')
  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase()
    const base = t ? opponents.filter(o => (o.name || '').toLowerCase().includes(t)) : opponents
    return base.slice(0, 50)
  }, [q, opponents])
  return (
    <div onClick={onClose} className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,.6)', backdropFilter: 'blur(4px)' }}>
      <div onClick={e => e.stopPropagation()} className="iq-card w-[440px] max-w-full overflow-hidden flex flex-col max-h-[80vh]" style={{ background: 'var(--pb-surface)' }}>
        <div className="px-5 py-4" style={{ borderBottom: '1px solid var(--pb-hairline)' }}>
          <div className="iq-eyebrow" style={{ color: 'var(--pb-accent)' }}>Match opponent to a club</div>
          <div className="iq-display font-bold text-[15px] mt-1 truncate">{fixture?.name || 'Opponent'}</div>
          <div className="text-pb-faintest text-[11px] mt-0.5">Link this fixture to a club in your history to unlock head-to-head and your record vs them.</div>
        </div>
        <div className="p-3"><Search value={q} onChange={setQ} placeholder="Search your clubs…" /></div>
        <div className="px-3 pb-2 overflow-y-auto iq-scroll">
          {filtered.length === 0 ? <div className="px-2"><Empty>No clubs found.</Empty></div> : (
            <div className="space-y-1">
              {filtered.map(o => (
                <button key={o.opp_key} onClick={() => onPick(o)}
                  className="w-full flex items-center justify-between gap-2 px-3 py-2 rounded-lg hover:bg-pb-surface2 text-left">
                  <div className="min-w-0">
                    <div className="font-medium truncate">{o.name}</div>
                    <div className="text-pb-faintest text-[11px]">{o.meetings} meetings{o.last_played ? ` · last ${o.last_played.slice(0, 4)}` : ''}</div>
                  </div>
                  {o.coverage === 'rich' && <Tag tone="accent">Synced</Tag>}
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="px-5 py-3 flex justify-end" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
          <Btn variant="ghost" sm onClick={onClose}>Cancel</Btn>
        </div>
      </div>
    </div>
  )
}

/* ── Building state ──────────────────────────────────────────────────────── */

function BuildingCard({ oppName }) {
  return (
    <div className="iq-card iq-accent-card p-8 text-center iq-fade">
      <div className="iq-display font-bold text-[16px]">Building their dossier…</div>
      <div className="text-pb-faint text-[13px] mt-1.5 max-w-md mx-auto">Pulling {oppName}'s recent scorecards and their record against us. The head-to-head above is ready now — this can take up to a minute the first time.</div>
      <div className="max-w-md mx-auto mt-5"><LoadingBar expectedMs={35000} /></div>
    </div>
  )
}

/* ── Main ────────────────────────────────────────────────────────────────── */

export default function OppositionScout() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const [list, setList] = useState(null)             // {opponents, upcoming}
  const [selected, setSelected] = useState(null)     // {opponent?, fixtureId?, name?}
  const [report, setReport] = useState(null)         // instant held-data report
  const [dossier, setDossier] = useState(null)       // live dossier (status/payload)
  const [teamsList, setTeamsList] = useState([])     // their teams, held stable across rebuilds
  const [matching, setMatching] = useState(null)     // fixture being matched to a club
  const [tags, setTags] = useState({})               // participant_id → scouting tag
  const [scope, setScope] = useState('all')          // record card: 'all' | 'selected'
  const pollRef = useRef(null)

  // The GLOBAL BetterIQ filter bar (top of the page) is the single source of
  // truth — no separate "Scout team" control. `ctx.team.id` is a grade NAME (the
  // IQ-wide convention); the season can be a single year or a cross-season range.
  const { ctx, seasons } = useIQFilter()
  const ctxGradeName = ctx?.team?.id || null
  const seasonIds = useMemo(() => seasonIdsInRange(ctx, seasons), [ctx, seasons])
  const seasonIdsKey = seasonIds.join(',')
  const seasonText = ctx ? seasonLabel(ctx, seasons) : ''
  const isAllSeasons = seasons.length > 0 && seasonIds.length === seasons.length
  // The newest single season is the global *default*, so treat it as "no season
  // filter" (the all-time landing the user wants). Only an older single season or
  // a multi-season range counts as an actively-chosen season filter.
  const newestId = seasons.length ? seasons[seasons.length - 1].id : null
  const seasonActive = !isAllSeasons && seasonIds.length > 0 && !(seasonIds.length === 1 && seasonIds[0] === newestId)
  const hasFilter = !!ctxGradeName || seasonActive
  const filterLabel = [ctxGradeName, seasonActive ? seasonText : null].filter(Boolean).join(' · ') || 'Filtered'
  // Map the selected grade NAME onto THIS opponent's grade_id for the live scout
  // (their grade ids carry the competition-wide grade name).
  const teamGradeId = useMemo(() => {
    if (!ctxGradeName) return null
    const lc = ctxGradeName.toLowerCase()
    const t = teamsList.find(x => (x.team_name || '').toLowerCase() === lc || (x.grade_name || '').toLowerCase() === lc)
    return t?.grade_id || null
  }, [ctxGradeName, teamsList])
  // Record-card toggle: All-time vs the active top-bar filter. Only shown when a
  // filter is actually active (otherwise the report is all-time anyway).
  const scopeOptions = hasFilter
    ? [{ value: 'all', label: 'All-time' }, { value: 'selected', label: filterLabel }]
    : []

  // Pull opponent list + saved scouting tags once.
  useEffect(() => {
    api.iqListOpponents().then(setList).catch(() => setList({ opponents: [], upcoming: [] }))
  }, [])
  useEffect(() => { api.iqOpponentTags().then(d => setTags(d || {})).catch(() => setTags({})) }, [])
  const saveTag = async (playerId, body) => {
    const saved = await api.iqSaveOpponentTag(playerId, body)
    setTags(t => ({ ...t, [playerId]: saved }))
    return saved
  }

  // Seed selection from the URL (?fixture= or ?opponent=, plus ?name= for a
  // club outside our history — without it an external pick reloads as a GUID).
  useEffect(() => {
    const fixtureId = searchParams.get('fixture')
    const opponent = searchParams.get('opponent')
    const name = searchParams.get('name') || undefined
    if (fixtureId) setSelected({ fixtureId, name })
    else if (opponent) setSelected({ opponent, name })
  }, [])  // once, on mount

  const stopPoll = () => { if (pollRef.current) { clearTimeout(pollRef.current); pollRef.current = null } }

  // Auto-apply the top filter: the record-card scope follows whether a filter is
  // active, so setting a grade/season immediately scopes the WHOLE report (record,
  // our performers, venues, bowler match-ups) — the previous design quietly needed
  // a second click on a card toggle, which is why the filter "wasn't working". The
  // user can still flip to All-time to override; changing the filter re-applies it.
  const filterSig = `${ctxGradeName || ''}|${seasonActive ? seasonIdsKey : ''}`
  const filterBaseline = useRef(undefined)
  useEffect(() => {
    if (!ctx) return
    if (filterBaseline.current !== filterSig) {
      filterBaseline.current = filterSig
      setScope(hasFilter ? 'selected' : 'all')
    }
  }, [ctx, filterSig, hasFilter])

  // Instant report — historical record vs them, scoped to the active top-bar
  // filter when scope === 'selected', else all-time.
  const applyFilter = scope === 'selected' && hasFilter
  const effGrade = applyFilter && ctxGradeName ? ctxGradeName : null
  const effSeasonIds = applyFilter && seasonActive ? seasonIds : null
  const effSeasonKey = effSeasonIds ? effSeasonIds.join(',') : ''
  const reportSel = useRef(null)
  useEffect(() => {
    if (!selected) { setReport(null); return }
    let alive = true
    // Blank the report only when the opponent itself changed (first load); a
    // scope change refetches in place so the card/toggle doesn't flicker.
    if (reportSel.current !== selected) { setReport(null); reportSel.current = selected }
    api.iqOppositionReport({
      opponent: selected.opponent, fixtureId: selected.fixtureId, name: selected.name,
      grade: effGrade || undefined, seasonIds: effSeasonIds || undefined,
    })
      .then(r => { if (alive) setReport(r) }).catch(() => { if (alive) setReport({ error: true }) })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, effGrade, effSeasonKey])

  // Live dossier — re-polled when the opponent OR chosen grade (top bar) changes.
  useEffect(() => {
    stopPoll()
    setDossier(null)
    if (!selected) return
    let alive = true
    const params = { opponent: selected.opponent, fixtureId: selected.fixtureId, team: teamGradeId, name: selected.name }
    const poll = () => {
      api.iqOppositionDossier(params).then(d => {
        if (!alive) return
        setDossier(d)
        if (d.teams?.length) setTeamsList(d.teams)
        if (d.status === 'building') pollRef.current = setTimeout(poll, POLL_MS)
      }).catch(() => { if (alive) setDossier({ status: 'error' }) })
    }
    poll()
    return () => { alive = false; stopPoll() }
  }, [selected, teamGradeId])

  const pick = (sel) => {
    setSelected(sel)
    setTeamsList([])
    // Keep the active filter applied to the new opponent (scope is governed by the
    // filter-follow effect); only reset the All-time override when nothing's filtered.
    setScope(hasFilter ? 'selected' : 'all')
    const sp = {}
    if (sel.fixtureId) sp.fixture = sel.fixtureId
    else if (sel.opponent) sp.opponent = sel.opponent
    if (sel.name) sp.name = sel.name
    setSearchParams(sp, { replace: true })
  }
  const clearSelection = () => { setSelected(null); setTeamsList([]); setSearchParams({}, { replace: true }) }

  // Manually match an unlinked fixture to a known club entity.
  const startMatch = (fx) => setMatching({ fixtureId: fx.fixture_id, name: fx.opponent_name })
  const applyMatch = (opp) => {
    const m = matching
    setMatching(null)
    if (!m) return
    if (m.name && opp.opp_key) {
      api.iqMatchOpponent({ opponentName: m.name, oppKey: opp.opp_key, displayName: opp.name })
        .then(() => api.iqListOpponents()).then(setList).catch(() => {})
    }
    pick({ fixtureId: m.fixtureId, opponent: opp.opp_key, name: opp.name })
  }

  const refresh = () => {
    if (!selected) return
    setDossier({ status: 'building' })
    const params = { opponent: selected.opponent, fixtureId: selected.fixtureId, team: teamGradeId, name: selected.name }
    api.iqRefreshDossier(params)
      .then(d => {
        setDossier(d)
        if (d.teams?.length) setTeamsList(d.teams)
        if (d.status === 'building') {
          stopPoll()
          pollRef.current = setTimeout(function p() {
            api.iqOppositionDossier(params).then(d2 => {
              setDossier(d2); if (d2.teams?.length) setTeamsList(d2.teams); if (d2.status === 'building') pollRef.current = setTimeout(p, POLL_MS)
            }).catch(() => setDossier({ status: 'error' }))
          }, POLL_MS)
        }
      }).catch(() => setDossier({ status: 'error' }))
  }

  const oppName = report?.opponent?.name || dossier?.opponent?.name || selected?.name || 'Opponent'
  const building = dossier?.status === 'building'
  const ready = dossier && dossier.status !== 'building' && dossier.status !== 'error' && dossier.status !== 'unavailable'
  const teamName = dossier?.selected_team_name || teamsList.find(t => t.grade_id === teamGradeId)?.team_name || null
  const teamMatches = teamsList.find(t => t.grade_id === (teamGradeId || teamsList[0]?.grade_id))?.matches

  const goCheatSheet = () => {
    const qs = new URLSearchParams()
    if (selected.opponent) qs.set('opponent', selected.opponent)
    if (selected.fixtureId) qs.set('fixture', selected.fixtureId)
    if (teamGradeId) qs.set('team', teamGradeId)
    navigate(`/admin/betteriq/opposition/cheatsheet?${qs}`)
  }

  // ── Picker view ──
  if (!selected) {
    return (
      <IQLayout title="Opposition analysis">
        {list === null
          ? <LoadingCard label="Loading opponents…" expectedMs={4500} />
          : <ScoutPicker data={list} onPick={pick} onMatch={startMatch} />}
        {matching && <MatchOpponentModal opponents={list?.opponents || []} fixture={matching} onPick={applyMatch} onClose={() => setMatching(null)} />}
      </IQLayout>
    )
  }

  // A fixture was picked but its opponent didn't resolve to club history.
  const unresolved = !!selected?.fixtureId && report && !report.error && report.opponent && !report.opponent.opp_key

  // ── Report view ──
  return (
    <IQLayout
      title="Opposition analysis"
      actions={
        <div className="flex items-center gap-2.5">
          <Btn variant="ghost" sm icon="back" onClick={clearSelection}>Change opponent</Btn>
          <Btn variant="ghost" sm icon="print" onClick={goCheatSheet}>Cheat sheet</Btn>
          <Btn variant="soft" sm icon="bolt" onClick={refresh} disabled={building}>{building ? 'Building…' : 'Refresh'}</Btn>
        </div>
      }
    >
      {/* Opponent header */}
      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <div className="iq-eyebrow" style={{ color: 'var(--pb-accent)' }}>Scouting report</div>
          <h2 className="iq-headline mt-2" style={{ fontSize: 'clamp(28px,3.4vw,40px)' }}>{oppName}</h2>
          {(teamName || teamMatches) && (
            <div className="text-pb-faint text-[12.5px] mt-1.5 iq-num">{[teamName, teamMatches ? `${teamMatches} matches this season` : null].filter(Boolean).join(' · ')}</div>
          )}
        </div>
      </div>

      {unresolved && (
        <div className="iq-card p-4 mb-5 flex flex-wrap items-center justify-between gap-3"
          style={{ borderColor: 'color-mix(in srgb, var(--pb-accent) 30%, transparent)' }}>
          <div className="text-sm">
            <span className="font-medium">No history matched for “{oppName}”.</span>{' '}
            <span className="text-pb-faint">Link this fixture to a club to unlock head-to-head and your record against them.</span>
          </div>
          <Btn sm variant="soft" icon="search" onClick={() => startMatch({ fixture_id: selected.fixtureId, opponent_name: oppName })}>Match club</Btn>
        </div>
      )}

      <div className="space-y-5">
        {/* Instant: command strip */}
        {report === null ? (
          <LoadingCard label="Loading head-to-head…" expectedMs={5500} />
        ) : report.error ? (
          <div className="iq-card p-6"><Empty>Couldn't load the head-to-head just now.</Empty></div>
        ) : (
          <>
            <CommandStrip h2h={report.head_to_head} lm={report.last_meeting}
              scope={scope} onScope={setScope} scopeOptions={scopeOptions} filterLabel={filterLabel} />

            {/* Instant: our record + venue */}
            <div className="grid gap-5 lg:grid-cols-2">
              <OurRecord performers={report.our_performers} />
              <VenueCard venues={report.venues} />
            </div>

            {/* Instant: recent meetings + bowler match-ups */}
            {report.head_to_head?.recent?.length > 0 && report.matchups?.bowler_dominance?.length > 0 ? (
              <div className="grid gap-5 lg:grid-cols-2 items-start">
                <RecentMeetings recent={report.head_to_head.recent} />
                <Matchups matchups={report.matchups} />
              </div>
            ) : (
              <>
                <RecentMeetings recent={report.head_to_head?.recent} />
                <Matchups matchups={report.matchups} />
              </>
            )}
          </>
        )}

        {/* The live squad scout below follows the top "Their grade" filter — when
            it's narrowed to a grade this club doesn't field, fall back to the
            whole club rather than show nothing. */}
        {ctxGradeName && teamsList.length > 0 && !teamGradeId && (
          <Note>They don't field a side in “{ctxGradeName}” — showing their whole club below. Pick a different grade in the top bar to narrow it.</Note>
        )}

        {/* Live dossier — phase 2 */}
        {building && <BuildingCard oppName={oppName} />}

        {dossier?.status === 'unavailable' && (
          <Note>{dossier.message || 'No live data available for this opponent yet — the head-to-head above still applies.'}</Note>
        )}
        {dossier?.status === 'error' && (
          <Note>Couldn't build the live dossier just now. The head-to-head above still applies — try Refresh in a moment.</Note>
        )}

        {ready && (
          <div className="space-y-5 iq-fade">
            <GamePlan plan={dossier.game_plan} report={report} />

            {/* Key players — the signature flick-through showcase cards */}
            {(dossier.danger_batters?.length > 0 || dossier.danger_bowlers?.length > 0) && (
              <div className="grid gap-5 lg:grid-cols-2">
                <KeyPlayersCard title="Danger batters" subtitle="their top run-scorers this season" players={dossier.danger_batters} kind="bat" />
                <KeyPlayersCard title="Danger bowlers" subtitle="their leading wicket-takers" players={dossier.danger_bowlers} kind="bowl" />
              </div>
            )}

            {/* Threat radars — top danger batter/bowler, built from the dossier squad */}
            <ThreatRadars dossier={dossier} />

            {/* Innings phases — estimated from ball-by-ball games (recent only) */}
            <InningsPhases selected={selected} />

            {/* Scout any of their players — full profile + 5-year history + tags */}
            <OppPlayerScout dossier={dossier} tags={tags} onSaveTag={saveTag} orgGuid={dossier.opponent?.org_id || null} />

            <WinLose win={dossier.how_they_win} lose={dossier.how_they_lose} />

            {/* How they get out + where they wobble (from their scorecards) */}
            {(dossier.dismissal_breakdown?.length > 0 || dossier.partnerships?.length > 0) && (
              <div className="grid gap-5 lg:grid-cols-2 items-start">
                {dossier.dismissal_breakdown?.length > 0 && (
                  <Card eyebrow="this season" title="How they get out"><StackedBar data={dossier.dismissal_breakdown} /></Card>
                )}
                <Partnerships partnerships={dossier.partnerships} insight={dossier.partnership_insight} />
              </div>
            )}

            <SquadTable dossier={dossier} />

            {dossier.historical_threats?.length > 0 && (
              <Card eyebrow="not in their current squad · watch for a recall" title="Historically hurt us">
                <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
                  {dossier.historical_threats.map(p => (
                    <div key={p.player_id} className="flex items-center justify-between gap-3 px-3.5 py-2.5"
                      style={{ background: 'var(--pb-surface2)', borderRadius: 10 }}
                      title={`${p.innings || 0} inns${p.high_score != null ? ` · HS ${p.high_score}` : ''} against us`}>
                      <span className="text-[13.5px] font-medium truncate">{p.name}</span>
                      <span className="iq-num text-[12.5px] whitespace-nowrap shrink-0">
                        <span className="font-semibold">{fmtCount(p.runs)}</span>
                        <span className="text-pb-faint"> @ {a2(p.average)}</span>
                      </span>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {dossier.coverage?.notes?.length > 0 && (
              <Note>{dossier.coverage.notes.join(' ')}{dossier.built_at ? ` · built ${new Date(dossier.built_at).toLocaleString()}` : ''}</Note>
            )}
          </div>
        )}
      </div>

      {matching && <MatchOpponentModal opponents={list?.opponents || []} fixture={matching} onPick={applyMatch} onClose={() => setMatching(null)} />}
    </IQLayout>
  )
}
