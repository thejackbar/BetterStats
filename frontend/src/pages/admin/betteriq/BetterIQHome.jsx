import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import IQLayout from '../../../components/admin/IQLayout'
import { api } from '../../../lib/api'
import { Icon, Btn, Tag, Empty } from '../betterselect/ui'

// The four BetterIQ capability areas (master-plan build order). Opposition is
// live; the rest are sequenced next and show as "soon".
const CAPABILITIES = [
  { key: 'opposition', title: 'Opposition analysis', to: '/admin/betteriq/opposition', live: true,
    blurb: 'Scout an upcoming opponent — squad & form pulled live, danger men, and deep head-to-head vs us.' },
  { key: 'selection', title: 'Selection analysis', to: '/admin/betteriq/selection', live: true,
    blurb: 'Form trends, batting/bowling balance of a proposed XI, who to promote or rest, fairness across grades.' },
  { key: 'trends', title: 'Player trends & development', to: '/admin/betteriq/trends', live: true,
    blurb: 'Individual trajectories, breakout / decline detection and milestone forecasting.' },
  { key: 'team', title: 'Team analysis', to: '/admin/betteriq/team', live: true,
    blurb: 'How we win and lose — batting & bowling shape, chasing vs defending, partnerships and venues.' },
  { key: 'qa', title: 'Natural-language Q&A', live: false,
    blurb: 'Ask your club’s data in plain English and get an answer grounded in the actual numbers.' },
]

function fmtDate(iso) {
  if (!iso) return ''
  try {
    return new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })
  } catch { return iso }
}

export default function BetterIQHome() {
  const navigate = useNavigate()
  const [upcoming, setUpcoming] = useState(null)
  const [mvp, setMvp] = useState(null)

  useEffect(() => {
    let alive = true
    api.iqListOpponents()
      .then(d => { if (alive) setUpcoming(Array.isArray(d?.upcoming) ? d.upcoming : []) })
      .catch(() => { if (alive) setUpcoming([]) })
    api.iqTeamMvp()
      .then(d => { if (alive) setMvp(d || { players: [] }) })
      .catch(() => { if (alive) setMvp({ players: [] }) })
    return () => { alive = false }
  }, [])

  const nextFixtures = (upcoming || []).slice(0, 4)

  const scout = (fx) => {
    const q = fx.fixture_id ? `fixture=${encodeURIComponent(fx.fixture_id)}`
      : fx.opp_key ? `opponent=${encodeURIComponent(fx.opp_key)}` : ''
    navigate(`/admin/betteriq/opposition${q ? `?${q}` : ''}`)
  }

  return (
    <IQLayout title="BetterIQ">
      {/* Hero */}
      <div className="pb-card p-6 mb-6" style={{ background: 'color-mix(in srgb, var(--pb-accent) 7%, transparent)', borderColor: 'color-mix(in srgb, var(--pb-accent) 30%, transparent)' }}>
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0" style={{ background: 'color-mix(in srgb, var(--pb-accent) 18%, transparent)', color: 'var(--pb-accent)' }}>
            <Icon name="bolt" size={22} />
          </div>
          <div>
            <h2 className="font-display font-bold text-xl">Your club's analytics brain</h2>
            <p className="text-pb-faint text-sm mt-1 max-w-2xl">
              The deep-dive most clubs — and plenty of pro teams — don't have. BetterIQ reads the data the
              Core already holds and pulls opponent data live from the same source, no manual entry.
            </p>
          </div>
        </div>
      </div>

      {/* Next opponent quick-scout */}
      <div className="mb-7">
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-display font-bold text-sm uppercase tracking-wide2 text-pb-faint">Scout your next opponent</h3>
        </div>
        {upcoming === null ? (
          <div className="pb-card p-5 animate-pulse text-pb-faint text-sm">Loading fixtures…</div>
        ) : nextFixtures.length === 0 ? (
          <div className="pb-card p-5">
            <Empty>No upcoming fixtures yet. Add fixtures in BetterSelect, or open Opposition analysis to scout any past opponent.</Empty>
            <div className="mt-3"><Btn variant="primary" sm icon="search" onClick={() => navigate('/admin/betteriq/opposition')}>Open Opposition analysis</Btn></div>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {nextFixtures.map(fx => (
              <button key={fx.fixture_id} onClick={() => scout(fx)}
                className="pb-card p-4 text-left hover:border-pb-accent/50 transition-colors group">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-display font-bold truncate">{fx.opponent_name || 'TBC'}</div>
                    <div className="text-pb-faint text-xs mt-0.5 flex flex-wrap items-center gap-x-2">
                      {fx.played_on && <span>{fmtDate(fx.played_on)}</span>}
                      {fx.home_away && <span className="font-mono uppercase">{fx.home_away}</span>}
                      {fx.team_name && <span>· {fx.team_name}</span>}
                      {fx.venue && <span className="truncate">· {fx.venue}</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {fx.opp_key
                      ? <Tag tone="accent">History</Tag>
                      : <Tag tone="faint">New</Tag>}
                    <span className="text-xl group-hover:translate-x-0.5 transition-transform" style={{ color: 'var(--pb-accent)' }}>→</span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Club MVPs — blended player-impact rating from scorecard data */}
      {mvp?.players?.length > 0 && (
        <div className="mb-7">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-display font-bold text-sm uppercase tracking-wide2 text-pb-faint">
              Club MVPs{mvp.season?.name ? ` · ${mvp.season.name}` : ''}
            </h3>
            <span className="text-pb-faintest text-[11px]">blended impact rating</span>
          </div>
          <div className="pb-card p-4">
            <div className="space-y-1.5">
              {mvp.players.map((p, i) => (
                <button key={p.player_id} onClick={() => navigate(`/admin/betteriq/trends?player=${encodeURIComponent(p.player_id)}`)}
                  className="w-full flex items-center gap-3 text-left group">
                  <span className="w-5 text-pb-faint font-mono text-xs shrink-0 text-right">{i + 1}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2">
                      <span className="truncate font-medium group-hover:text-pb-accent transition-colors">{p.name}</span>
                      <span className="text-pb-faintest text-[11px] shrink-0">{p.role}</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-pb-surface2 overflow-hidden mt-1">
                      <div className="h-full rounded-full" style={{ width: `${p.impact}%`, background: 'var(--pb-accent)' }} />
                    </div>
                  </div>
                  <div className="text-right shrink-0 w-24">
                    <div className="font-display font-bold pb-num leading-none" style={{ color: 'var(--pb-accent)' }}>{p.impact}</div>
                    <div className="text-pb-faintest text-[10px] pb-num whitespace-nowrap mt-0.5">{p.runs}r · {p.wickets}w{p.dismissals ? ` · ${p.dismissals}f` : ''}</div>
                  </div>
                </button>
              ))}
            </div>
            <div className="text-pb-faintest text-[11px] mt-3 pt-3 border-t pb-hairline">A whole-season value measure (not current form): per-match runs, wickets, economy and fielding dismissals, z-scored across the squad and scaled 0–100. See Player trends for recent form.</div>
          </div>
        </div>
      )}

      {/* Capability areas */}
      <h3 className="font-display font-bold text-sm uppercase tracking-wide2 text-pb-faint mb-2">Capabilities</h3>
      <div className="grid gap-3 sm:grid-cols-2">
        {CAPABILITIES.map(c => (
          c.live ? (
            <button key={c.key} onClick={() => navigate(c.to)}
              className="pb-card p-5 text-left hover:border-pb-accent/50 transition-colors group" style={{ borderColor: 'color-mix(in srgb, var(--pb-accent) 28%, transparent)' }}>
              <div className="flex items-center justify-between gap-3">
                <span className="font-display font-bold">{c.title}</span>
                <Tag tone="accent">Live</Tag>
              </div>
              <div className="text-pb-faint text-sm mt-1">{c.blurb}</div>
            </button>
          ) : (
            <div key={c.key} className="pb-card p-5 opacity-60">
              <div className="flex items-center justify-between gap-3">
                <span className="font-display font-bold">{c.title}</span>
                <span className="font-mono text-[10px] tracking-wide2 text-pb-faint border pb-hairline rounded px-2 py-0.5">SOON</span>
              </div>
              <div className="text-pb-faint text-sm mt-1">{c.blurb}</div>
            </div>
          )
        ))}
      </div>
    </IQLayout>
  )
}
