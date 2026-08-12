import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { scoutApi } from '../lib/scoutApi'
import ScoutModuleLayout from '../ScoutModuleLayout'
import { PlayerAvatar, Sparkline } from '../components/ScoutUi'
import { Btn } from '../../pages/admin/betterselect/ui'

function StatReadout({ label, value }) {
  return (
    <div className="text-right">
      <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faint">{label}</div>
      <div className="font-mono text-lg font-bold">{value}</div>
    </div>
  )
}

export default function ScoutOverview() {
  const [data, setData] = useState(undefined)
  const [error, setError] = useState(null)
  const [refreshingId, setRefreshingId] = useState(null)

  const load = () => { scoutApi.getOverview().then(setData).catch((err) => setError(err.message)) }
  useEffect(load, [])

  const refreshPlayer = async (id) => {
    setRefreshingId(id)
    try {
      await scoutApi.refreshPlayer(id)
      setTimeout(load, 2000)
    } finally {
      setRefreshingId(null)
    }
  }

  if (error) return <ScoutModuleLayout title="Overview"><p className="text-sm text-pb-red">{error}</p></ScoutModuleLayout>
  if (data === undefined) return <ScoutModuleLayout title="Overview"><p className="text-sm text-pb-dim">Loading…</p></ScoutModuleLayout>

  const { usage, pipeline_counts: pipeline, form_movers: movers, form_movers_total, stale, recent_clubs: clubs } = data

  return (
    <ScoutModuleLayout
      title="Overview"
      stats={
        <div className="flex items-center gap-6">
          <StatReadout label="In pipeline" value={pipeline.in_pipeline} />
          <StatReadout label={pipeline.final_stage_label} value={pipeline.final_stage_count} />
        </div>
      }
      actions={<Btn variant="primary"><Link to="/betterscout/app/discover">Find players</Link></Btn>}
    >
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_372px] gap-5">
        <div className="space-y-5">
          <div className="pb-card p-4 space-y-1">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Form movers</div>
                <p className="text-xs text-pb-faint mt-0.5">Last season vs. the two before, among players you track</p>
              </div>
              {form_movers_total > movers.length && (
                <Link to="/betterscout/app/players" className="text-xs text-pb-accent hover:underline whitespace-nowrap">See all {form_movers_total} →</Link>
              )}
            </div>
            {movers.length === 0 && <p className="text-sm text-pb-faint py-4">Not enough season-on-season history to show movers yet.</p>}
            <div className="divide-y divide-pb-hairline -mx-4 mt-1">
              {movers.map((m) => (
                <div key={m.id} className="flex items-center gap-3 px-4 py-3">
                  <PlayerAvatar name={m.name} size={36} />
                  <div className="min-w-0 flex-1">
                    <Link to={`/betterscout/app/players/${m.id}`} className="text-sm font-medium hover:text-pb-accent truncate block">{m.name}</Link>
                    <div className="text-xs text-pb-faint truncate">{[m.club_name, m.grade_name].filter(Boolean).join(' · ')}</div>
                  </div>
                  <Sparkline seasons={m.sparkline.map((s) => ({ year: s.year, v: s.value }))} metricKey="v" height={34} width={7} gap={3} />
                  <div className="text-right shrink-0">
                    <div className="font-mono text-sm font-bold">
                      {m.current_value}
                      <span className={m.improved ? 'text-pb-accent' : 'text-pb-red'} style={{ marginLeft: 4 }}>
                        {m.improved ? '▲' : '▼'} {Math.abs(m.delta)}
                      </span>
                    </div>
                    <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faint">{m.metric}</div>
                  </div>
                  <Link to={`/betterscout/app/players/${m.id}`} className="text-xs px-2 py-1 rounded border border-pb-hairline2 text-pb-faint hover:text-pb-text shrink-0">Open</Link>
                </div>
              ))}
            </div>
          </div>

          <div className="pb-card p-4 space-y-1">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Going stale</div>
                <p className="text-xs text-pb-faint mt-0.5">Tracked, but no stats refresh or note in {data.stale_after_weeks || 6}+ weeks</p>
              </div>
              {stale.filter((s) => !s.manual).length > 0 && (
                <button onClick={() => stale.filter((s) => !s.manual).forEach((s) => refreshPlayer(s.id))} className="text-xs text-pb-accent hover:underline whitespace-nowrap">
                  Refresh all {stale.filter((s) => !s.manual).length}
                </button>
              )}
            </div>
            {stale.length === 0 && <p className="text-sm text-pb-faint py-4">Nothing stale — everyone you track has recent stats or notes.</p>}
            <div className="divide-y divide-pb-hairline -mx-4 mt-1">
              {stale.map((s) => (
                <div key={s.id} className="flex items-center gap-3 px-4 py-3">
                  <PlayerAvatar name={s.name} size={30} dashed={s.manual} />
                  <div className="min-w-0 flex-1">
                    <Link to={`/betterscout/app/players/${s.id}`} className="text-sm font-medium hover:text-pb-accent truncate block">{s.name}</Link>
                    <div className="text-xs text-pb-faint truncate">{s.club_name || '—'}</div>
                  </div>
                  <span className="font-mono text-xs text-pb-amber shrink-0">{s.note}</span>
                  {!s.manual && (
                    <button onClick={() => refreshPlayer(s.id)} disabled={refreshingId === s.id} className="text-xs px-2 py-1 rounded border border-pb-hairline2 text-pb-faint hover:text-pb-text shrink-0 disabled:opacity-50">
                      {refreshingId === s.id ? '…' : 'Refresh'}
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-5">
          <div className="pb-card p-4 space-y-2">
            <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Growth plan</div>
            <div className="font-mono text-lg font-bold">{usage.player_count} / {usage.player_cap ?? '∞'}</div>
            {usage.player_cap != null && (
              <div className="h-1.5 rounded-full bg-pb-surface2 overflow-hidden">
                <div className="h-full rounded-full" style={{ width: `${Math.min(100, Math.round(100 * usage.player_count / usage.player_cap))}%`, background: usage.at_cap ? 'var(--pb-red)' : 'var(--pb-accent)' }} />
              </div>
            )}
            <p className="text-xs text-pb-faint">
              Priced by players actively tracked.{usage.player_cap != null && ` ${Math.max(0, usage.player_cap - usage.player_count)} slots left — archive someone to free one up.`}
            </p>
          </div>

          <div className="pb-card p-4 space-y-1">
            <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">Clubs you've looked at</div>
            {clubs.length === 0 && <p className="text-xs text-pb-faint">Search a club on Discover to get started.</p>}
            <div className="divide-y divide-pb-hairline -mx-4">
              {clubs.map((c) => (
                <div key={c.org_guid} className="flex items-center justify-between px-4 py-2.5">
                  <div className="min-w-0">
                    <div className="text-sm font-medium truncate">{c.club_name}</div>
                    <div className={`font-mono text-[11px] ${c.stale ? 'text-pb-amber' : 'text-pb-faint'}`}>
                      {c.player_count != null ? `${c.player_count} players` : '—'} · {c.built_at ? `cached ${new Date(c.built_at).toLocaleDateString()}` : 'not built'}
                    </div>
                  </div>
                  <Link to={`/betterscout/app/discover`} className="text-xs shrink-0" style={{ color: 'var(--pb-accent)' }}>
                    {c.stale ? 'Rebuild →' : 'Open roster →'}
                  </Link>
                </div>
              ))}
            </div>
          </div>

          <div className="pb-card p-4 space-y-2 border-dashed" style={{ borderStyle: 'dashed' }}>
            <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Not built yet</div>
            <p className="text-sm font-medium">Search a player by name, anywhere in Australia</p>
            <p className="text-xs text-pb-faint">
              BetterScout only knows clubs a scout has actually searched for — name search across the whole country needs crawling and indexing every club's roster, which isn't built yet.
            </p>
            <input disabled placeholder="Search any player…" className="w-full bg-pb-bg border border-pb-hairline2 rounded px-3 py-2 text-sm text-pb-faintest cursor-not-allowed" />
            <p className="text-xs text-pb-faint">The same applies to a country-wide hot-form feed.</p>
          </div>
        </div>
      </div>
    </ScoutModuleLayout>
  )
}
