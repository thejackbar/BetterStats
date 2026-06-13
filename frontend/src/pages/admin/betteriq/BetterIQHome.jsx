/* BetterIQ — Overview hub.
   A true hub that surfaces the best insight from every area, composed entirely
   from real IQ endpoints (there is no single overview endpoint — everything is
   assembled client-side, fetched in parallel and guarded individually).
   Ported to high-fidelity from docs/design_handoff_betteriq_v2 (Overview.jsx). */
import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import IQLayout from '../../../components/admin/IQLayout'
import { api } from '../../../lib/api'
import {
  Icon, CountUp, Bar, ResultPills, Card, Note, Tag, Btn, Initials, Delta, a2,
  LoadingBar, fmtCount, runsPhrase, wktsPhrase,
} from './ui'
import { AreaChart, DonutStat } from './viz'
import { useIQFilter, effectiveSeasonId } from './Context'
import { formatSeason } from '../../../lib/cricketFormat'

/* ── helpers ──────────────────────────────────────────────────────────────── */
function fmtDate(iso) {
  if (!iso) return ''
  try {
    return new Date(iso + (iso.length <= 10 ? 'T00:00:00' : '')).toLocaleDateString(undefined, {
      weekday: 'short', day: 'numeric', month: 'short',
    })
  } catch { return iso }
}
// Review results come back as full words (WIN/LOSS/DRAW/TIE); ResultPills wants
// a single W/L/D/T letter.
function resultLetter(r) {
  if (!r) return null
  const c = String(r)[0].toUpperCase()
  return c === 'W' || c === 'L' || c === 'D' || c === 'T' ? c : null
}
function scoutQuery(fx) {
  if (!fx) return ''
  if (fx.fixture_id) return `?fixture=${encodeURIComponent(fx.fixture_id)}`
  if (fx.opp_key) return `?opponent=${encodeURIComponent(fx.opp_key)}`
  return ''
}

/* ── Hero — positioning + next fixture focus ──────────────────────────────── */
function Hero({ fx, h2h, onScout, onNavigate }) {
  return (
    <div className="iq-card iq-accent-card overflow-hidden iq-rise">
      <div className="relative grid md:grid-cols-[1.4fr_1fr]">
        {/* Left: statement + CTAs */}
        <div className="p-7 md:p-9">
          <div className="flex items-center gap-2 iq-eyebrow">
            <Icon name="bolt" size={13} style={{ color: 'var(--pb-accent)' }} />Your club's analytics brain
          </div>
          <h2 className="iq-headline mt-4" style={{ fontSize: 'clamp(28px,3.4vw,44px)', maxWidth: 560 }}>
            Read the game<br />before it's played.
          </h2>
          <p className="text-pb-dim mt-4 leading-relaxed" style={{ maxWidth: 460, fontSize: 14.5 }}>
            The deep-dive most clubs — and plenty of pro teams — don't have. BetterIQ reads the data your
            club already holds and pulls opponent form live from the same source. No manual entry.
          </p>
          <div className="flex flex-wrap items-center gap-2.5 mt-6">
            <Btn variant="primary" icon="search" onClick={() => onScout(fx)}>
              {fx?.opponent_name ? `Scout ${fx.opponent_name}` : 'Scout an opponent'}
            </Btn>
            <Btn variant="soft" icon="fixtures" onClick={() => onNavigate('preview')}>Match preview</Btn>
          </div>
        </div>

        {/* Right: next fixture */}
        <div className="relative p-7 md:p-9 md:border-l"
          style={{ borderColor: 'var(--pb-hairline)', background: 'color-mix(in srgb, var(--pb-accent) 4%, transparent)' }}>
          <div className="iq-eyebrow">Next fixture</div>
          {fx ? (
            <>
              <div className="flex items-baseline gap-2 mt-3">
                <span className="iq-mono text-pb-faint text-[13px]">vs</span>
                <span className="iq-headline" style={{ fontSize: 26 }}>{fx.opponent_name || 'TBC'}</span>
              </div>
              <div className="flex flex-wrap gap-x-5 gap-y-1.5 mt-3 text-[13px] text-pb-dim">
                {fx.played_on && (
                  <span className="inline-flex items-center gap-1.5">
                    <Icon name="fixtures" size={14} className="text-pb-faint" />{fmtDate(fx.played_on)}
                  </span>
                )}
                {(fx.home_away || fx.venue) && (
                  <span className="inline-flex items-center gap-1.5">
                    <Icon name="target" size={14} className="text-pb-faint" />
                    {[fx.home_away, fx.venue].filter(Boolean).join(' · ')}
                  </span>
                )}
              </div>
              {fx.team_name && <div className="iq-mono text-pb-faint text-[11px] mt-2">{fx.team_name}</div>}

              {/* Head-to-head (optional — only when we have history vs them) */}
              {h2h && (h2h.wins != null || h2h.losses != null) && (
                <div className="mt-5 pt-5" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
                  <div className="flex items-center justify-between">
                    <div className="iq-eyebrow">Head-to-head</div>
                    {h2h.meetings != null && <div className="text-[11px] text-pb-faint iq-num">{h2h.meetings} meetings</div>}
                  </div>
                  <div className="flex items-end gap-4 mt-2.5">
                    <div>
                      <div className="iq-headline iq-num" style={{ fontSize: 30, color: 'var(--pb-brand)' }}><CountUp value={h2h.wins || 0} /></div>
                      <div className="iq-eyebrow mt-1">Won</div>
                    </div>
                    <div className="text-pb-faintest pb-2 text-xl">–</div>
                    <div>
                      <div className="iq-headline iq-num" style={{ fontSize: 30, color: 'var(--pb-red)' }}><CountUp value={h2h.losses || 0} /></div>
                      <div className="iq-eyebrow mt-1">Lost</div>
                    </div>
                    {h2h.recent_form?.length > 0 && (
                      <div className="ml-auto flex flex-col items-end gap-1.5">
                        <div className="iq-eyebrow">Recent</div>
                        <ResultPills form={h2h.recent_form} size={20} />
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="mt-3 text-pb-dim text-[13.5px] leading-relaxed">
              No upcoming fixtures yet. Add fixtures in BetterSelect, or open Opposition analysis to scout any past opponent.
              <div className="mt-4"><Btn variant="soft" sm icon="search" onClick={() => onNavigate('opposition')}>Open Opposition analysis</Btn></div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/* ── Club pulse: win-rate + form + trajectory ─────────────────────────────── */
function ClubPulse({ record, last10, curve, seasonLbl }) {
  const labels = curve.map((_, i) => (curve.length <= 1 || i % Math.ceil(curve.length / 4) === 0 ? `G${i + 1}` : ''))
  const streakLen = (() => {
    if (!last10.length) return 0
    const first = last10[0]; let n = 0
    for (const r of last10) { if (r === first) n++; else break }
    return n
  })()
  const streakTone = last10[0] === 'W' ? 'win' : last10[0] === 'L' ? 'red' : 'amber'
  const streakLbl = last10[0] === 'W' ? `Won ${streakLen}` : last10[0] === 'L' ? `Lost ${streakLen}` : `Drew ${streakLen}`
  return (
    <Card eyebrow={seasonLbl ? `season ${seasonLbl}` : 'club form'} title="Club pulse" className="iq-rise"
      right={last10.length ? <Tag tone={streakTone}>{streakLbl}</Tag> : null}>
      <div className="flex flex-wrap items-center gap-5">
        {record?.win_pct != null
          ? <DonutStat value={record.win_pct} label="Win rate"
              sub={record.wins != null ? `${record.wins}W · ${record.losses}L${record.draws ? ` · ${record.draws}D` : ''}` : undefined} />
          : <div className="text-pb-faint text-[13px]">Win rate unavailable</div>}
        <div className="flex-1 min-w-[150px]">
          <div className="iq-eyebrow mb-2">Last {last10.length || 10}</div>
          {last10.length
            ? <ResultPills form={last10} size={20} />
            : <div className="text-pb-faintest text-[12px]">No results yet</div>}
          {record?.matches != null && (
            <div className="text-pb-faint text-[12px] mt-2.5 iq-num">
              {fmtCount(record.matches)} game{record.matches === 1 ? '' : 's'} this season
            </div>
          )}
        </div>
      </div>
      {curve.length > 1 && (
        <div className="mt-5 pt-4" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
          <div className="iq-eyebrow mb-1.5">Form trajectory · cumulative wins</div>
          <AreaChart points={curve} labels={labels} h={140} format={v => v} />
        </div>
      )}
    </Card>
  )
}

/* ── This-week workflow loop ──────────────────────────────────────────────── */
const WEEK_STATE = {
  ready:      { c: 'var(--pb-accent)', label: 'Ready' },
  'needs-you':{ c: 'var(--pb-amber)',  label: 'Needs you' },
  upcoming:   { c: 'var(--pb-faint)',  label: 'Upcoming' },
  'after-match': { c: 'var(--pb-brand)', label: 'After match' },
}
function WeeklyLoop({ steps, onNavigate }) {
  const idle = steps.every(s => s.state === 'upcoming')
  return (
    <Card eyebrow="your week" title="Match-week workflow" className="iq-rise" style={{ animationDelay: '60ms' }}>
      {idle && (
        <div className="flex items-center gap-2 mb-3 text-[12.5px]" style={{ color: 'var(--pb-faint)' }}>
          <Icon name="check" size={14} />No action required right now — no upcoming fixture or recent match for this view.
        </div>
      )}
      <div className="space-y-1">
        {steps.map((s, i) => {
          const st = WEEK_STATE[s.state] || WEEK_STATE.upcoming
          const clickable = !!s.route
          return (
            <button key={i} disabled={!clickable} onClick={() => clickable && onNavigate(s.route)}
              className="w-full flex items-center gap-3.5 px-2 py-2.5 text-left transition"
              style={{ borderRadius: 10, cursor: clickable ? 'pointer' : 'default' }}
              onMouseEnter={e => { if (clickable) e.currentTarget.style.background = 'var(--pb-surface2)' }}
              onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}>
              <div className="relative flex flex-col items-center shrink-0">
                <span className="flex items-center justify-center iq-mono font-bold"
                  style={{ width: 26, height: 26, borderRadius: 99, fontSize: 11, color: st.c,
                    background: `color-mix(in srgb, ${st.c} 16%, transparent)`,
                    border: `1px solid color-mix(in srgb, ${st.c} 40%, transparent)` }}>{i + 1}</span>
                {i < steps.length - 1 && <span style={{ position: 'absolute', top: 26, height: 18, width: 1.5, background: 'var(--pb-hairline2)' }} />}
              </div>
              <div className="min-w-0 flex-1">
                <div className="font-semibold text-[14px]">{s.step}</div>
                <div className="text-pb-faint text-[12px]">{s.label}</div>
              </div>
              <span className="iq-mono shrink-0"
                style={{ fontSize: 9.5, padding: '2px 7px', borderRadius: 6, color: st.c, background: `color-mix(in srgb, ${st.c} 14%, transparent)` }}>{st.label}</span>
              {clickable && <Icon name="chevron" size={14} className="text-pb-faint shrink-0" />}
            </button>
          )
        })}
      </div>
    </Card>
  )
}

/* ── Last result mini ─────────────────────────────────────────────────────── */
function LastResult({ game, onOpen }) {
  const letter = resultLetter(game.result)
  const c = letter === 'W' ? 'var(--pb-brand)' : letter === 'L' ? 'var(--pb-red)' : 'var(--pb-amber)'
  const word = { W: 'WON', L: 'LOST', D: 'DREW', T: 'TIED' }[letter] || (game.result || '—')
  return (
    <button onClick={onOpen} className="iq-card iq-accent-card text-left p-5 transition iq-rise w-full" style={{ animationDelay: '120ms' }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = 'color-mix(in srgb, var(--pb-accent) 45%, transparent)' }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = '' }}>
      <div className="flex items-center justify-between">
        <div className="iq-eyebrow">Last result</div>
        <Icon name="chevron" size={15} className="text-pb-faint" />
      </div>
      <div className="flex items-baseline gap-2.5 mt-2.5 flex-wrap">
        <span className="iq-headline" style={{ fontSize: 22, color: c }}>{word}</span>
        <span className="iq-headline" style={{ fontSize: 19 }}>vs {game.opponent}</span>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-[12.5px] text-pb-dim">
        {game.date && <span>{fmtDate(game.date)}</span>}
        {game.grade && <span className="iq-mono text-pb-faint">{game.grade}</span>}
        {game.is_final && <Tag tone="amber">Final</Tag>}
      </div>
      <div className="mt-3 pt-3 text-[12px] text-pb-faint" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
        Open the full match review →
      </div>
    </button>
  )
}

/* ── Scout fixture card ───────────────────────────────────────────────────── */
function FixtureCard({ fx, onScout, i }) {
  const known = !!fx.opp_key
  return (
    <button onClick={() => onScout(fx)}
      className="iq-card text-left p-4 transition group iq-rise"
      style={{ animationDelay: `${80 + i * 60}ms`, cursor: 'pointer' }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = 'color-mix(in srgb, var(--pb-accent) 45%, transparent)' }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = '' }}>
      <div className="flex items-center justify-between gap-2">
        <span className="iq-mono text-[10px] uppercase tracking-wider text-pb-faint">{fmtDate(fx.played_on) || 'TBC'}</span>
        <Tag tone={known ? 'accent' : 'faint'}>{known ? 'History' : 'New'}</Tag>
      </div>
      <div className="iq-display font-bold text-[18px] mt-2.5 leading-tight">{fx.opponent_name || 'TBC'}</div>
      <div className="text-pb-faint text-[12px] mt-1">{[fx.home_away, fx.venue].filter(Boolean).join(' · ') || '—'}</div>
      <div className="flex items-center justify-between mt-3.5 pt-3" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
        <span className="iq-mono text-[10.5px] text-pb-faint">{fx.team_name || ''}</span>
        <span className="inline-flex items-center gap-1 text-[12px] font-semibold" style={{ color: 'var(--pb-accent)' }}>
          Scout <Icon name="arrow" size={13} className="transition-transform group-hover:translate-x-0.5" />
        </span>
      </div>
    </button>
  )
}

/* ── Club MVP row ─────────────────────────────────────────────────────────── */
function MvpRow({ p, rank, max, onOpen }) {
  const pct = max > 0 ? (p.impact / max) * 100 : 0
  const top = rank === 1
  const sub = [
    p.runs != null ? runsPhrase(p.runs) : null,
    p.wickets ? wktsPhrase(p.wickets) : null,
    p.dismissals ? `${fmtCount(p.dismissals)} dismissals` : null,
  ].filter(Boolean).join(' · ')
  return (
    <button onClick={onOpen} className="w-full flex items-center gap-4 px-2 py-3 text-left transition rounded-xl hover:bg-pb-surface2 iq-rise"
      style={{ animationDelay: `${rank * 45}ms` }}>
      <div className="iq-headline iq-num shrink-0 text-center"
        style={{ width: 30, fontSize: top ? 22 : 18, color: top ? 'var(--pb-accent)' : 'var(--pb-faint)' }}>{rank}</div>
      <Initials name={p.name} size={38} tone={top ? 'accent' : undefined} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="iq-display font-semibold text-[14.5px] truncate">{p.name}</span>
          <span className="iq-headline iq-num shrink-0" style={{ fontSize: 17, color: top ? 'var(--pb-accent)' : 'var(--pb-text)' }}>{p.impact}</span>
        </div>
        <div className="mt-1.5">
          <Bar pct={pct} delay={rank * 0.05} h={5}
            color={top ? 'var(--pb-accent)' : 'color-mix(in srgb, var(--pb-accent) 55%, var(--pb-faint))'} />
        </div>
        <div className="flex items-center justify-between gap-2 mt-1.5">
          {p.role && <span className="text-pb-faint text-[11px]">{p.role}</span>}
          {sub && <span className="text-pb-faint text-[11.5px] iq-num truncate">{sub}</span>}
        </div>
      </div>
    </button>
  )
}

/* ── Form movers teaser ───────────────────────────────────────────────────── */
function MoversTeaser({ trends, onNavigate }) {
  const rows = useMemo(() => {
    const bat = trends?.batting || {}, bowl = trends?.bowling || {}
    return [
      ...(bat.risers || []).slice(0, 2).map(p => ({ ...p, kind: 'bat' })),
      ...(bowl.risers || []).slice(0, 1).map(p => ({ ...p, kind: 'bowl' })),
      ...(bat.fallers || []).slice(0, 1).map(p => ({ ...p, kind: 'bat' })),
    ]
  }, [trends])
  return (
    <Card eyebrow="this season vs career" title="Form movers"
      right={<Btn variant="ghost" sm onClick={() => onNavigate('trends')}>All trends</Btn>}>
      {rows.length === 0 ? (
        <div className="text-pb-faintest text-[13px] py-2">Not enough recent data to detect movers yet.</div>
      ) : (
        <div className="space-y-1">
          {rows.map((p, i) => {
            // Batting: higher avg is up. Bowling: lower avg is up — flip the sign.
            const raw = Number(p.latest) - Number(p.baseline)
            const value = p.kind === 'bowl' ? -raw : raw
            const up = value >= 0
            return (
              <button key={`${p.player_id}-${i}`} onClick={() => onNavigate(`trends?player=${encodeURIComponent(p.player_id)}`)}
                className="w-full flex items-center justify-between gap-3 px-2 py-2.5 transition rounded-lg hover:bg-pb-surface2 text-left"
                style={{ background: i % 2 ? 'transparent' : 'var(--pb-surface2)' }}>
                <div className="flex items-center gap-3 min-w-0">
                  <Initials name={p.name} size={32} tone={up ? 'accent' : undefined} />
                  <div className="min-w-0">
                    <div className="font-semibold text-[13.5px] truncate">{p.name}</div>
                    <div className="text-pb-faint text-[11px]">
                      {p.kind === 'bat' ? 'Batting avg' : 'Bowling avg'} {a2(p.baseline)} → {a2(p.latest)}
                    </div>
                  </div>
                </div>
                <Delta value={value} decimals={2} />
              </button>
            )
          })}
        </div>
      )}
      <Note>Trend = latest season vs prior-career baseline. Bowling improvement means a lower average.</Note>
    </Card>
  )
}

/* ── Capability cards ─────────────────────────────────────────────────────── */
const CAPS = [
  { icon: 'search', title: 'Opposition analysis', desc: 'Full scouting dossiers — danger men, game plans, match-ups.', route: 'opposition' },
  { icon: 'selection', title: 'Selection analysis', desc: 'Check the balance of a saved XI and justify the pick.', route: 'selection' },
  { icon: 'trend', title: 'Player trends', desc: 'Form movers, development and statistical deep-dives.', route: 'trends' },
  { icon: 'teams', title: 'Team analysis', desc: 'How your club itself wins and loses, season by season.', route: 'team' },
]
function CapCard({ c, i, onNavigate }) {
  return (
    <button onClick={() => onNavigate(c.route)} className="iq-card text-left p-5 iq-rise transition w-full" style={{ animationDelay: `${i * 50}ms` }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = 'color-mix(in srgb, var(--pb-accent) 45%, transparent)' }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = '' }}>
      <div className="flex items-center justify-between">
        <div className="flex items-center justify-center"
          style={{ width: 36, height: 36, borderRadius: 10, background: 'color-mix(in srgb, var(--pb-accent) 12%, transparent)', color: 'var(--pb-accent)' }}>
          <Icon name={c.icon} size={18} />
        </div>
        <Icon name="arrow" size={15} className="text-pb-faint" />
      </div>
      <div className="iq-display font-bold text-[15px] mt-3.5">{c.title}</div>
      <div className="text-pb-faint text-[12.5px] mt-1.5 leading-relaxed">{c.desc}</div>
    </button>
  )
}

/* ── Section header ───────────────────────────────────────────────────────── */
function SectionHead({ children, sub }) {
  return (
    <div className="flex items-end justify-between gap-3 mb-4 mt-10">
      <h2 className="iq-display font-bold text-[19px]" style={{ letterSpacing: '-0.01em' }}>{children}</h2>
      {sub && <span className="text-pb-faint text-[12.5px]">{sub}</span>}
    </div>
  )
}

/* ── Loading skeleton ─────────────────────────────────────────────────────── */
function Skeleton({ h = 120 }) {
  return (
    <div className="iq-card flex items-center px-6" style={{ height: h }}>
      <LoadingBar label="Loading…" expectedMs={6000} className="w-full" />
    </div>
  )
}

/* ── Page ─────────────────────────────────────────────────────────────────── */
export default function BetterIQHome() {
  const navigate = useNavigate()
  const { ctx } = useIQFilter()
  const seasonId = effectiveSeasonId(ctx)
  const gradeId = ctx?.team?.id || undefined

  const [opponents, setOpponents] = useState(undefined) // undefined = loading
  const [mvp, setMvp] = useState(undefined)
  const [trends, setTrends] = useState(undefined)
  const [reviewGames, setReviewGames] = useState(undefined)
  const [overview, setOverview] = useState(undefined)
  const [h2h, setH2h] = useState(undefined)
  const [lineups, setLineups] = useState(undefined)

  // Filter-independent reads: fetch once (fixtures + saved lineups span grades;
  // we scope fixtures to the chosen grade client-side below).
  useEffect(() => {
    let alive = true
    api.iqListOpponents()
      .then(d => { if (alive) setOpponents(d || { upcoming: [], opponents: [] }) })
      .catch(() => { if (alive) setOpponents({ upcoming: [], opponents: [] }) })
    api.iqSelectionLineups()
      .then(d => { if (alive) setLineups(Array.isArray(d) ? d : []) })
      .catch(() => { if (alive) setLineups([]) })
    return () => { alive = false }
  }, [])

  // Filter-dependent reads: re-fetch when the global Season/Team filter changes —
  // MVP, team overview, form movers and recent results all follow the filter.
  useEffect(() => {
    let alive = true
    setMvp(undefined); setOverview(undefined); setTrends(undefined); setReviewGames(undefined)
    api.iqTeamMvp(seasonId, gradeId)
      .then(d => { if (alive) setMvp(d || { players: [] }) })
      .catch(() => { if (alive) setMvp({ players: [] }) })
    api.iqTeamOverview(seasonId, gradeId)
      .then(d => { if (alive) setOverview(d || {}) })
      .catch(() => { if (alive) setOverview({}) })
    api.iqTrendsOverview(seasonId, gradeId)
      .then(d => { if (alive) setTrends(d || {}) })
      .catch(() => { if (alive) setTrends({}) })
    api.iqReviewGames(seasonId, gradeId)
      .then(d => { if (alive) setReviewGames(Array.isArray(d) ? d : []) })
      .catch(() => { if (alive) setReviewGames([]) })
    return () => { alive = false }
  }, [seasonId, gradeId])

  // Next fixture + scout cards scope to the selected grade (by grade name); the
  // fixtures feed spans all grades.
  const allUpcoming = opponents?.upcoming || []
  const upcoming = gradeId ? allUpcoming.filter(f => f.grade_name === gradeId) : allUpcoming
  const nextFx = upcoming[0] || null
  const scoutCards = upcoming.slice(0, 4)

  // Head-to-head for the hero's next fixture (optional; guard if it fails).
  useEffect(() => {
    let alive = true
    setH2h(undefined)
    if (!nextFx?.fixture_id) { setH2h(null); return }
    api.iqOppositionReport({ fixtureId: nextFx.fixture_id })
      .then(d => { if (alive) setH2h(d?.head_to_head || null) })
      .catch(() => { if (alive) setH2h(null) })
    return () => { alive = false }
  }, [nextFx?.fixture_id])

  const scout = (fx) => navigate(`/admin/betteriq/opposition${scoutQuery(fx)}`)
  const go = (route) => navigate(`/admin/betteriq/${route}`)

  // Review games come newest-first. Last-10 pills (mapped to letters, newest
  // first) + a cumulative-wins trajectory in chronological order.
  const last10 = useMemo(
    () => (reviewGames || []).map(g => resultLetter(g.result)).filter(Boolean).slice(0, 10),
    [reviewGames],
  )
  const winsCurve = useMemo(() => {
    const chrono = [...(reviewGames || [])].reverse() // oldest → newest
    let cum = 0
    return chrono.map(g => { if (resultLetter(g.result) === 'W') cum += 1; return cum })
  }, [reviewGames])
  const lastGame = (reviewGames || [])[0] || null

  const seasonLbl = mvp?.season?.name || ctx?.season?.to?.label || undefined

  const mvpPlayers = mvp?.players || []
  const maxMvp = useMemo(() => Math.max(1, ...mvpPlayers.map(p => p.impact || 0)), [mvpPlayers])

  // WeeklyLoop: Select step is "ready" when the next fixture already has a saved XI.
  const selectReady = !!(nextFx?.fixture_id && (lineups || []).some(l => l.fixture_id === nextFx.fixture_id && (l.lineup_count || 0) > 0))
  const weekSteps = [
    { step: 'Preview', label: nextFx?.opponent_name ? `Scout ${nextFx.opponent_name}` : 'Scout the opponent', state: nextFx ? 'ready' : 'upcoming', route: 'preview' },
    { step: 'Select', label: selectReady ? 'XI confirmed' : 'Confirm the XI', state: nextFx ? (selectReady ? 'ready' : 'needs-you') : 'upcoming', route: 'selection' },
    { step: 'Match day', label: nextFx?.played_on ? fmtDate(nextFx.played_on) : 'This week', state: 'upcoming', route: null },
    { step: 'Review', label: lastGame ? `Last vs ${lastGame.opponent}` : 'Auto post-match', state: lastGame ? 'after-match' : 'upcoming', route: 'review' },
  ]

  return (
    <IQLayout title="BetterIQ">
      {/* Hero */}
      {opponents === undefined ? (
        <Skeleton h={220} />
      ) : (
        <Hero fx={nextFx} h2h={h2h} onScout={scout} onNavigate={go} />
      )}

      {/* Club pulse row */}
      <div className="grid gap-5 lg:grid-cols-[1.5fr_1fr] items-start mt-6">
        {overview === undefined || reviewGames === undefined ? (
          <Skeleton h={300} />
        ) : (
          <ClubPulse record={overview?.record} last10={last10} curve={winsCurve} seasonLbl={seasonLbl} />
        )}
        <div className="space-y-5">
          {reviewGames === undefined ? (
            <Skeleton h={150} />
          ) : lastGame ? (
            <LastResult game={lastGame} onOpen={() => navigate(`/admin/betteriq/review?game=${encodeURIComponent(lastGame.game_id)}`)} />
          ) : null}
          <WeeklyLoop steps={weekSteps} onNavigate={go} />
        </div>
      </div>

      {/* Scout next opponent */}
      <SectionHead sub="Tap to open a full dossier">Scout your next opponent</SectionHead>
      {opponents === undefined ? (
        <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map(i => <Skeleton key={i} h={140} />)}
        </div>
      ) : scoutCards.length === 0 ? (
        <Card>
          <div className="text-pb-faint text-sm">No upcoming fixtures yet. Add fixtures in BetterSelect, or open Opposition analysis to scout any past opponent.</div>
          <div className="mt-3"><Btn variant="primary" sm icon="search" onClick={() => go('opposition')}>Open Opposition analysis</Btn></div>
        </Card>
      ) : (
        <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
          {scoutCards.map((fx, i) => <FixtureCard key={fx.fixture_id || i} fx={fx} onScout={scout} i={i} />)}
        </div>
      )}

      {/* MVPs + movers + capabilities */}
      <div className="grid gap-6 lg:grid-cols-[1.15fr_1fr] items-start">
        <div>
          <SectionHead sub={`season impact · 0–100${mvp?.season?.name ? ` · ${formatSeason(mvp.season)}` : ''}`}>Club MVPs</SectionHead>
          {mvp === undefined ? (
            <Skeleton h={360} />
          ) : mvpPlayers.length === 0 ? (
            <Card><div className="text-pb-faint text-sm">No player-impact ratings for this season yet.</div></Card>
          ) : (
            <Card>
              <div className="-mx-2 -my-1">
                {mvpPlayers.map((p, i) => (
                  <MvpRow key={p.player_id} p={p} rank={i + 1} max={maxMvp}
                    onOpen={() => navigate(`/admin/betteriq/trends?player=${encodeURIComponent(p.player_id)}`)} />
                ))}
              </div>
              <Note>A blended whole-season value measure — runs, wickets and fielding, z-scored across the squad and scaled 0–100. Not current form (see Player trends for that).</Note>
            </Card>
          )}
        </div>
        <div>
          <SectionHead sub="who's trending">Form movers</SectionHead>
          {trends === undefined ? <Skeleton h={220} /> : <MoversTeaser trends={trends} onNavigate={go} />}

          <SectionHead sub="jump in">Explore</SectionHead>
          <div className="grid gap-3.5 sm:grid-cols-2">
            {CAPS.map((c, i) => <CapCard key={c.route} c={c} i={i} onNavigate={go} />)}
          </div>
        </div>
      </div>
    </IQLayout>
  )
}
