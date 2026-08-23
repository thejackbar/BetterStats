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

function MoverColumn({ title, rows }) {
  return (
    <div>
      <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faintest px-1 pb-1">{title}</div>
      {rows.length === 0 && <p className="text-xs text-pb-faint py-3 px-1">No {title.toLowerCase()} movers yet.</p>}
      <div className="divide-y divide-pb-hairline">
        {rows.map((m) => <MoverRow key={`${m.id}-${m.metric}`} m={m} />)}
      </div>
    </div>
  )
}

function MoverRow({ m }) {
  return (
    <div className="flex items-center gap-2.5 py-2.5">
      <PlayerAvatar name={m.name} size={32} />
      <div className="min-w-0 flex-1">
        <Link to={`/betterscout/app/players/${m.id}`} className="text-sm font-medium hover:text-pb-accent truncate block">{m.name}</Link>
        <div className="text-xs text-pb-faint truncate">{[m.club_name, m.grade_name].filter(Boolean).join(' · ')}</div>
      </div>
      <Sparkline seasons={m.sparkline.map((s) => ({ year: s.year, v: s.value }))} metricKey="v" height={30} width={6} gap={2.5} />
      <div className="text-right shrink-0">
        <div className="font-mono text-sm font-bold">
          {m.current_value}
          <span className={m.improved ? 'text-pb-positive' : 'text-pb-red'} style={{ marginLeft: 4 }}>
            {m.improved ? '▲' : '▼'} {Math.abs(m.delta)}
          </span>
        </div>
        <div className="font-mono text-[9px] text-pb-faint">vs career {m.career_value}</div>
      </div>
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

  const { usage, pipeline_counts: pipeline, form_movers: movers, form_movers_total, stale, recent_clubs: clubs, recent_players: recentPlayers } = data
  const battingMovers = movers.filter((m) => m.batting)
  const bowlingMovers = movers.filter((m) => !m.batting)

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
                <p className="text-xs text-pb-faint mt-0.5">Latest season vs. career average, among players you track</p>
              </div>
              {form_movers_total > movers.length && (
                <Link to="/betterscout/app/players" className="text-xs text-pb-accent hover:underline whitespace-nowrap">See all {form_movers_total} →</Link>
              )}
            </div>
            {movers.length === 0 && <p className="text-sm text-pb-faint py-4">Not enough season-on-season history to show movers yet.</p>}
            {movers.length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4 mt-1">
                <MoverColumn title="Batting" rows={battingMovers} />
                <MoverColumn title="Bowling" rows={bowlingMovers} />
              </div>
            )}
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
            {stale.length === 0 && <p className="text-sm text-pb-faint py-4">Nothing stale. Everyone you track has recent stats or notes.</p>}
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
              Priced by players actively tracked.{usage.player_cap != null && ` ${Math.max(0, usage.player_cap - usage.player_count)} slots left, archive someone to free one up.`}
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

          <div className="pb-card p-4 space-y-1">
            <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">Players you've looked at</div>
            {(!recentPlayers || recentPlayers.length === 0) && <p className="text-xs text-pb-faint">Open a player's profile to build this list.</p>}
            <div className="divide-y divide-pb-hairline -mx-4">
              {(recentPlayers || []).map((p) => (
                <Link key={p.scouted_player_id} to={`/betterscout/app/players/${p.scouted_player_id}`}
                  className="flex items-center justify-between px-4 py-2.5 hover:bg-pb-surface2 transition-colors">
                  <div className="min-w-0">
                    <div className="text-sm font-medium truncate">{p.name}</div>
                    <div className="font-mono text-[11px] text-pb-faint truncate">
                      {p.club_name || 'No club recorded'} · {p.last_viewed_at ? new Date(p.last_viewed_at).toLocaleDateString() : '—'}
                    </div>
                  </div>
                  <span className="text-xs shrink-0" style={{ color: 'var(--pb-accent)' }}>Open →</span>
                </Link>
              ))}
            </div>
          </div>
        </div>
      </div>
    </ScoutModuleLayout>
  )
}
