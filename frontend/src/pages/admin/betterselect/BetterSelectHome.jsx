// BetterSelect → Overview. The module landing, redesigned to the handoff's
// "this weekend" dashboard (docs/.../prototype/bs-overview.jsx): the next
// fixture, who's responded, what needs attention, and the upcoming fixtures —
// each a click into availability or selection. Built from the live API and
// defensive about every shape so the landing page degrades rather than breaks.
import { useState, useEffect, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { PbSpinner } from '../../../lib/presskit'
import { AVAILABILITY } from '../../../lib/availability'
import { Icon, Btn, AvailSummary, Empty } from './ui'

const SELECT = '/admin/betterselect/select/'

function fmtDate(d) {
  try { return new Date(d + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) }
  catch { return d || '' }
}

function StatCell({ label, value, tone }) {
  const color = tone === 'positive' ? 'var(--pb-positive)' : tone === 'amber' ? 'var(--pb-amber)' : tone === 'red' ? 'var(--pb-red)' : 'var(--pb-text)'
  return (
    <div className="flex-1 px-4 py-3.5 min-w-[90px]">
      <div className="font-display font-bold text-[26px] pb-num" style={{ color }}>{value}</div>
      <div className="text-xs text-pb-faint mt-0.5">{label}</div>
    </div>
  )
}

function NeedRow({ tone, children, action, onClick }) {
  const dot = tone === 'red' ? 'var(--pb-red)' : tone === 'amber' ? 'var(--pb-amber)' : 'var(--pb-positive)'
  return (
    <button onClick={onClick} className="w-full flex items-center gap-3 py-3 border-b pb-hairline last:border-0 text-left">
      <span className="w-[7px] h-[7px] rounded-full shrink-0" style={{ background: dot }} />
      <span className="flex-1 text-[13.5px] text-pb-dim">{children}</span>
      {action && <span className="text-xs text-pb-accent inline-flex items-center gap-1 shrink-0">{action} <Icon name="chevron" size={13} /></span>}
    </button>
  )
}

export default function BetterSelectHome() {
  const { hasCapability } = useAuth()
  const navigate = useNavigate()
  const [fixtures, setFixtures] = useState(null)
  const [overview, setOverview] = useState([])
  const [matrix, setMatrix] = useState({ dates: [], players: [], availability: {} })
  const [roster, setRoster] = useState([])

  useEffect(() => {
    let alive = true
    Promise.all([
      api.bsListFixtures(true).then((r) => r).catch(() => []),
      api.bsSelectionOverview().then((d) => d.fixtures || []).catch(() => []),
      api.bsAvailabilityMatrix().then((d) => d).catch(() => ({ dates: [], players: [], availability: {} })),
      api.adminListPlayers().then((r) => r).catch(() => []),
    ]).then(([fx, ov, mx, rs]) => {
      if (!alive) return
      setFixtures(Array.isArray(fx) ? fx : [])
      setOverview(Array.isArray(ov) ? ov : [])
      setMatrix(mx && mx.players ? mx : { dates: [], players: [], availability: {} })
      setRoster(Array.isArray(rs) ? rs : [])
    })
    return () => { alive = false }
  }, [])

  const playable = useMemo(
    () => (fixtures || []).filter((f) => f.home_away !== 'BYE' && f.played_on),
    [fixtures],
  )

  // Lineup size per fixture (for "needs an XI" + "named" markers). Prefer the
  // count the fixtures payload carries; fall back to the selection-overview join.
  const lineupLen = useMemo(() => {
    const m = {}
    overview.forEach((f) => { m[f.id] = (f.lineup || []).length })
    return m
  }, [overview])
  const lineupCountOf = (f) => (typeof f.lineup_count === 'number' ? f.lineup_count : (lineupLen[f.id] || 0))

  // Hero = the highest-ranked team that still needs an XI on the nearest
  // match-day. Lower team_sequence = more senior (1 = 1st XI); 0/blank ranks
  // last so an unranked side never outranks the firsts. If every team on that
  // day is already picked, fall back to the most senior game of the day.
  const hero = useMemo(() => {
    if (!playable.length) return null
    const rankOf = (f) => (f.team_sequence && f.team_sequence > 0 ? f.team_sequence : Infinity)
    const bySeniority = (a, b) => rankOf(a) - rankOf(b) || (a.start_time || '').localeCompare(b.start_time || '')
    const nextDate = playable[0].played_on              // playable is date-sorted asc
    const dayFixtures = playable.filter((f) => f.played_on === nextDate)
    const unpicked = dayFixtures.filter((f) => lineupCountOf(f) === 0)
    return (unpicked.length ? unpicked : dayFixtures).slice().sort(bySeniority)[0] || null
  }, [playable, lineupLen])
  const heroDate = hero?.played_on || null

  // Availability status for a player on the hero date.
  const statusOn = (pid, d) => matrix.availability?.[pid]?.[d]?.status || matrix.availability?.[pid]?.[d] || 'NO_RESPONSE'

  // Squad scoped to the hero fixture's team (squad_team_id), else all non-dormant
  // active players from the matrix roster.
  const squad = useMemo(() => {
    if (!heroDate) return []
    const matrixById = {}
    ;(matrix.players || []).forEach((p) => { matrixById[p.id] = p })
    let scoped = []
    if (hero?.team_id) {
      const assigned = roster.filter((p) => p.squad_team_id === hero.team_id)
      scoped = assigned.map((p) => matrixById[p.id] || p)
    }
    if (!scoped.length) scoped = (matrix.players || []).filter((p) => !p.is_dormant && p.status !== 'inactive')
    return scoped.map((p) => ({ ...p, availability: statusOn(p.id, heroDate) }))
  }, [hero, heroDate, roster, matrix])

  const tally = useMemo(() => {
    const t = { AVAILABLE: 0, MAYBE: 0, NO_RESPONSE: 0, UNAVAILABLE: 0 }
    squad.forEach((p) => { t[p.availability] = (t[p.availability] || 0) + 1 })
    return t
  }, [squad])
  const responded = squad.length - (tally.NO_RESPONSE || 0)

  // Needs-attention items.
  const needs = useMemo(() => {
    const items = []
    const keepersOut = squad.filter((p) => (p.skill_positions || []).includes('WKT') && (p.availability === 'NO_RESPONSE' || p.availability === 'MAYBE'))
    if (keepersOut.length) {
      const names = keepersOut.map((p) => p.display_name).slice(0, 2).join(', ')
      items.push({ tone: 'red', action: 'Review', to: '/admin/betterselect/availability',
        node: <>Your keeper{keepersOut.length > 1 ? 's' : ''} <b className="text-pb-text">{names}</b> {keepersOut.length > 1 ? "haven't" : "hasn't"} confirmed</> })
    }
    if (tally.NO_RESPONSE > 0) {
      items.push({ tone: 'amber', action: 'Review', to: '/admin/betterselect/availability',
        node: <><b className="text-pb-text">{tally.NO_RESPONSE} player{tally.NO_RESPONSE === 1 ? '' : 's'}</b> {tally.NO_RESPONSE === 1 ? "hasn't" : "haven't"} set availability</> })
    }
    const weekendFx = playable.filter((f) => f.played_on === heroDate)
    const needXI = weekendFx.filter((f) => lineupCountOf(f) === 0).length
    if (needXI > 0) {
      items.push({ tone: 'accent', action: 'Pick', to: SELECT + (weekendFx.find((f) => lineupCountOf(f) === 0)?.id || hero.id),
        node: <><b className="text-pb-text">{needXI} of {weekendFx.length}</b> weekend team{weekendFx.length === 1 ? '' : 's'} still need{needXI === 1 ? 's' : ''} an XI</> })
    }
    return items
  }, [squad, tally, playable, heroDate, lineupLen, hero])

  const heroTitle = hero ? `${hero.team_name || 'Our team'} vs ${hero.opponent_name || hero.label || 'TBC'}` : ''
  const canSelect = hasCapability(CAP.MANAGE_SELECTIONS)

  if (fixtures === null) return <BetterSelectLayout title="Overview"><PbSpinner message="Loading…" /></BetterSelectLayout>

  return (
    <BetterSelectLayout
      title="Overview"
      actions={hero && canSelect && <Btn variant="primary" sm icon="selection" onClick={() => navigate(SELECT + hero.id)}>Pick this team</Btn>}
    >
      {!hero ? (
        <div className="pb-card px-5 py-12 text-center">
          <Empty className="mb-4">No upcoming fixtures yet.</Empty>
          <div className="flex gap-2 justify-center">
            <Btn variant="primary" sm icon="fixtures" onClick={() => navigate('/admin/betterselect/fixtures')}>Add or sync fixtures</Btn>
            <Btn variant="ghost" sm icon="teams" onClick={() => navigate('/admin/betterselect/teams')}>Set up squads</Btn>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {/* Hero — this weekend (accent gradient = legit white-label) */}
          <div className="pb-card overflow-hidden" style={{ background: 'linear-gradient(120deg, color-mix(in srgb, var(--pb-accent) 10%, transparent), transparent 55%)', borderColor: 'color-mix(in srgb, var(--pb-accent) 25%, transparent)' }}>
            <div className="px-[22px] py-5">
              <div className="font-mono text-[10px] uppercase tracking-wide3 text-pb-accent">
                {lineupCountOf(hero) === 0 ? 'Next to pick' : 'This weekend'}{hero.round ? ` · Round ${hero.round}` : ''}
              </div>
              <div className="font-display font-bold text-[30px] mt-1.5 leading-tight">{heroTitle}</div>
              <div className="flex flex-wrap gap-4 mt-2.5 text-[13.5px] text-pb-dim">
                <span className="inline-flex items-center gap-1.5"><Icon name="fixtures" size={15} /> {fmtDate(hero.played_on)}{hero.start_time ? `, ${hero.start_time}` : ''}</span>
                {hero.venue && <span className="inline-flex items-center gap-1.5"><Icon name="availability" size={15} /> {hero.venue}{hero.home_away === 'HOME' ? ' (H)' : hero.home_away === 'AWAY' ? ' (A)' : ''}</span>}
                {hero.grade_name && <span className="inline-flex items-center gap-1.5">{hero.grade_name}</span>}
              </div>
              {squad.length > 0 && <div className="mt-4 max-w-[460px]"><AvailSummary players={squad} /></div>}
              <div className="flex flex-wrap items-center gap-2.5 mt-4">
                {canSelect && <Btn variant="primary" icon="selection" onClick={() => navigate(SELECT + hero.id)}>Pick this team</Btn>}
                <Btn variant="soft" icon="availability" onClick={() => navigate('/admin/betterselect/availability')}>Review availability</Btn>
                {squad.length > 0 && <span className="text-[13px] text-pb-faint">{Math.max(0, squad.length - responded)} still to respond</span>}
              </div>
            </div>
          </div>

          {/* Pulse stats */}
          {squad.length > 0 && (
            <div className="pb-card flex items-stretch divide-x divide-pb-hairline overflow-x-auto">
              <StatCell label="Responded" value={`${responded}/${squad.length}`} tone="positive" />
              <StatCell label="Available" value={tally.AVAILABLE || 0} tone="positive" />
              <StatCell label="Maybe" value={tally.MAYBE || 0} tone="amber" />
              <StatCell label="Unavailable" value={tally.UNAVAILABLE || 0} tone="red" />
              <StatCell label="No response" value={tally.NO_RESPONSE || 0} />
            </div>
          )}

          {/* Needs attention + upcoming */}
          <div className="grid lg:grid-cols-2 gap-4">
            <div className="pb-card px-[18px] py-4">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="font-display font-bold text-[15px]">Needs attention</span>
                {needs.length > 0 && <span className="font-mono text-[10px] text-pb-amber bg-pb-amber/12 px-[7px] py-0.5 rounded-full">{needs.length}</span>}
              </div>
              {needs.length === 0
                ? <p className="text-pb-faint text-sm py-2">All set for this weekend. 🎉</p>
                : needs.map((n, i) => <NeedRow key={i} tone={n.tone} action={n.action} onClick={() => navigate(n.to)}>{n.node}</NeedRow>)}
            </div>

            <div className="pb-card px-[18px] py-4">
              <div className="flex items-center justify-between mb-2.5">
                <span className="font-display font-bold text-[15px]">Upcoming fixtures</span>
                <Link to="/admin/betterselect/fixtures" className="font-mono text-[11px] text-pb-accent">All fixtures →</Link>
              </div>
              <div className="flex flex-col">
                {playable.slice(0, 5).map((f) => {
                  const named = lineupCountOf(f) > 0
                  return (
                    <button key={f.id} onClick={() => navigate(SELECT + f.id)}
                      className="flex items-center gap-3 py-2 border-b pb-hairline last:border-0 text-left">
                      <span className="font-mono text-[11px] text-pb-faint w-[64px] shrink-0">{fmtDate(f.played_on).replace(/^\w+ /, '')}</span>
                      <span className="flex-1 text-[13px] truncate">
                        <span className="text-pb-faint">{f.home_away === 'AWAY' ? '@ ' : 'vs '}</span>{f.opponent_name || f.label || 'TBC'}
                        {f.team_name && <span className="text-pb-faintest"> · {f.team_name}</span>}
                      </span>
                      <span className="font-mono text-[10px] shrink-0" style={{ color: named ? 'var(--pb-positive)' : 'var(--pb-faintest)' }}>{named ? 'named' : 'not picked'}</span>
                      <Icon name="chevron" size={14} />
                    </button>
                  )
                })}
                {playable.length === 0 && <Empty>No upcoming fixtures.</Empty>}
              </div>
            </div>
          </div>
        </div>
      )}
    </BetterSelectLayout>
  )
}
