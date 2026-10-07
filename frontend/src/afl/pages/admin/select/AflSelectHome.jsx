import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import ModuleHub from '../../../../components/admin/ModuleHub'
import ModuleHero from '../../../../components/admin/ModuleHero'
import { GROUPS } from '../../../../components/admin/BetterSelectLayout'
import { PbSpinner } from '../../../../lib/presskit'
import { moduleBrand } from '../../../../lib/moduleBrand'
import { Icon, Btn, Empty } from '../../../../pages/admin/betterselect/ui'
import { aflApi } from '../../../aflApi'
import { shortDate } from './ui'

const BRAND = moduleBrand('select')
const BASE = '/admin/betterselect'

// PlayHQ files the round as "Round 9" (or "Semi Final"), so only a bare number
// needs the word in front of it.
const roundLabel = r => (/^\d+$/.test(String(r).trim()) ? `Round ${String(r).trim()}` : String(r))

// BetterSelect → Overview, football's version of the "this weekend" landing:
// the next day's games and which of them still need a side, the draw ahead,
// then the tools grouped as sub-modules (the BetterAdmin house style). Built
// from the fixtures the football sync already holds, so a club that has not
// synced yet sees the empty state and the two places to start.

function StatCell({ label, value, tone }) {
  const color = tone === 'positive' ? 'var(--pb-positive)' : tone === 'amber' ? 'var(--pb-amber)' : 'var(--pb-text)'
  return (
    <div className="flex-1 px-4 py-3.5 min-w-[90px]">
      <div className="font-display font-bold text-[26px] pb-num" style={{ color }}>{value}</div>
      <div className="text-xs text-pb-faint mt-0.5">{label}</div>
    </div>
  )
}

function NeedRow({ tone, children, action, onClick }) {
  const dot = tone === 'amber' ? 'var(--pb-amber)' : 'var(--pb-accent)'
  return (
    <button onClick={onClick} className="w-full flex items-center gap-3 py-3 border-b pb-hairline last:border-0 text-left">
      <span className="w-[7px] h-[7px] rounded-full shrink-0" style={{ background: dot }} />
      <span className="flex-1 text-[13.5px] text-pb-dim">{children}</span>
      {action && <span className="text-xs text-pb-accent inline-flex items-center gap-1 shrink-0">{action} <Icon name="chevron" size={13} /></span>}
    </button>
  )
}

export default function AflSelectHome() {
  const { group } = useParams()
  if (group) {
    return (
      <div className="max-w-3xl">
        <ModuleHub groups={GROUPS} basePath={BASE} groupKey={group} />
      </div>
    )
  }
  return <Overview />
}

function Overview() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)

  useEffect(() => {
    let alive = true
    aflApi.selFixtures({ when: 'upcoming' })
      .then(d => { if (alive) setData(d) })
      .catch(() => { if (alive) setData({ fixtures: [], teams: [] }) })
    return () => { alive = false }
  }, [])

  const fixtures = data?.fixtures || []
  const nextDay = fixtures[0]?.played_on || null
  const weekend = useMemo(() => fixtures.filter(f => f.played_on === nextDay), [fixtures, nextDay])
  const unpicked = weekend.filter(f => !f.picked)
  const noSide = fixtures.filter(f => !f.team_id)
  // The side that most needs naming first: the first unpicked game of the day,
  // else the first game of the day (the draw is already in date and time order).
  const hero = unpicked[0] || weekend[0] || null
  const pick = f => `${BASE}/selection?fixture=${f.id}`

  const needs = []
  if (unpicked.length) {
    needs.push({ tone: 'accent', action: 'Pick', to: pick(unpicked[0]),
      node: <><b className="text-pb-text">{unpicked.length} of {weekend.length}</b> game{weekend.length === 1 ? '' : 's'} on {shortDate(nextDay)} still need{unpicked.length === 1 ? 's' : ''} a side</> })
  }
  if (noSide.length) {
    needs.push({ tone: 'amber', action: 'Review', to: `${BASE}/fixtures`,
      node: <><b className="text-pb-text">{noSide.length} fixture{noSide.length === 1 ? '' : 's'}</b> {noSide.length === 1 ? "isn't" : "aren't"} filed under a side yet</> })
  }

  if (!data) return <PbSpinner message="Loading…" />

  return (
    <>
      <ModuleHero
        name="BetterSelect"
        logo={BRAND.logo}
        blurb="Everything for match day: your squads, the draw, availability and the side you name each week."
      />
      {!hero ? (
        <div className="pb-card px-5 py-12 text-center">
          <Empty className="mb-4">No upcoming fixtures yet.</Empty>
          <div className="flex gap-2 justify-center">
            <Btn variant="primary" sm icon="fixtures" onClick={() => navigate(`${BASE}/fixtures`)}>Add or sync fixtures</Btn>
            <Btn variant="ghost" sm icon="teams" onClick={() => navigate(`${BASE}/squads`)}>Set up squads</Btn>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="pb-card overflow-hidden" style={{ background: 'linear-gradient(120deg, color-mix(in srgb, var(--pb-accent) 10%, transparent), transparent 55%)', borderColor: 'color-mix(in srgb, var(--pb-accent) 25%, transparent)' }}>
            <div className="px-[22px] py-5">
              <div className="font-mono text-[10px] uppercase tracking-wide3 text-pb-accent">
                {hero.picked ? 'This weekend' : 'Next to pick'}{hero.round ? ` · ${roundLabel(hero.round)}` : ''}
              </div>
              <div className="font-display font-bold text-[30px] mt-1.5 leading-tight">
                {hero.team_name || hero.grade_name || 'Our side'} vs {hero.opponent_name || hero.label || 'TBC'}
              </div>
              <div className="flex flex-wrap gap-4 mt-2.5 text-[13.5px] text-pb-dim">
                <span className="inline-flex items-center gap-1.5"><Icon name="fixtures" size={15} /> {shortDate(hero.played_on)}{hero.start_time ? `, ${hero.start_time}` : ''}</span>
                {hero.venue && <span className="inline-flex items-center gap-1.5"><Icon name="availability" size={15} /> {hero.venue}{hero.home_away === 'HOME' ? ' (H)' : hero.home_away === 'AWAY' ? ' (A)' : ''}</span>}
                {hero.grade_name && <span>{hero.grade_name}</span>}
              </div>
              <div className="flex flex-wrap items-center gap-2.5 mt-4">
                <Btn variant="primary" icon="selection" onClick={() => navigate(pick(hero))}>Pick this side</Btn>
                <Btn variant="soft" icon="availability" onClick={() => navigate(`${BASE}/availability`)}>Review availability</Btn>
              </div>
            </div>
          </div>

          <div className="pb-card flex items-stretch divide-x divide-pb-hairline overflow-x-auto">
            <StatCell label="Games that day" value={weekend.length} />
            <StatCell label="Sides named" value={weekend.length - unpicked.length} tone="positive" />
            <StatCell label="Still to pick" value={unpicked.length} tone={unpicked.length ? 'amber' : undefined} />
            <StatCell label="Upcoming games" value={fixtures.length} />
          </div>

          <div className="grid lg:grid-cols-2 gap-4">
            <div className="pb-card px-[18px] py-4 min-w-0">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="font-display font-bold text-[15px]">Needs attention</span>
                {needs.length > 0 && <span className="font-mono text-[10px] text-pb-amber bg-pb-amber/12 px-[7px] py-0.5 rounded-full">{needs.length}</span>}
              </div>
              {needs.length === 0
                ? <p className="text-pb-faint text-sm py-2">All set for {shortDate(nextDay)}.</p>
                : needs.map((n, i) => <NeedRow key={i} tone={n.tone} action={n.action} onClick={() => navigate(n.to)}>{n.node}</NeedRow>)}
            </div>

            <div className="pb-card px-[18px] py-4 min-w-0">
              <div className="flex items-center justify-between mb-2.5">
                <span className="font-display font-bold text-[15px]">Upcoming fixtures</span>
                <Link to={`${BASE}/fixtures`} className="font-mono text-[11px] text-pb-accent">All fixtures →</Link>
              </div>
              <div className="flex flex-col">
                {fixtures.slice(0, 5).map(f => (
                  <button key={f.id} onClick={() => navigate(pick(f))}
                    className="flex items-center gap-3 py-2 border-b pb-hairline last:border-0 text-left">
                    <span className="font-mono text-[11px] text-pb-faint w-[64px] shrink-0">{shortDate(f.played_on).replace(/^\w+,? /, '')}</span>
                    <span className="flex-1 text-[13px] truncate min-w-0">
                      <span className="text-pb-faint">{f.home_away === 'AWAY' ? '@ ' : 'vs '}</span>{f.opponent_name || f.label || 'TBC'}
                      {f.team_name && <span className="text-pb-faintest"> · {f.team_name}</span>}
                    </span>
                    <span className="font-mono text-[10px] shrink-0" style={{ color: f.picked ? 'var(--pb-positive)' : 'var(--pb-faintest)' }}>{f.picked ? 'named' : 'not picked'}</span>
                    <Icon name="chevron" size={14} />
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="mt-6 max-w-3xl">
        <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-2">BetterSelect tools</div>
        <ModuleHub groups={GROUPS} basePath={BASE} />
      </div>
    </>
  )
}
