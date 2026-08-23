import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { scoutApi } from '../lib/scoutApi'
import { useScoutAuth } from '../contexts/ScoutAuthContext'
import ScoutModuleLayout from '../ScoutModuleLayout'
import { PlayerAvatar, Sparkline } from '../components/ScoutUi'
import { Icon, Search } from '../../pages/admin/betterselect/ui'

export default function ScoutPlayers() {
  const { user } = useScoutAuth()
  const usage = user?.usage
  const [players, setPlayers] = useState(undefined) // undefined = loading
  const [error, setError] = useState(null)
  const [q, setQ] = useState('')
  const [removingId, setRemovingId] = useState(null)

  useEffect(() => {
    scoutApi.listPlayers().then(setPlayers).catch((err) => setError(err.message))
  }, [])

  const removePlayer = async (e, p) => {
    e.preventDefault()
    e.stopPropagation()
    if (!window.confirm(`Remove ${p.name} from My Players? This removes them from every one of your boards.`)) return
    setRemovingId(p.id)
    setError(null)
    try {
      await scoutApi.removePlayerEverywhere(p.id)
      setPlayers((ps) => ps.filter((x) => x.id !== p.id))
    } catch (err) {
      setError(err.message)
    } finally {
      setRemovingId(null)
    }
  }

  const shown = useMemo(() => {
    if (!players) return []
    const query = q.trim().toLowerCase()
    if (!query) return players
    return players.filter((p) => p.name.toLowerCase().includes(query) || (p.club_name || '').toLowerCase().includes(query))
  }, [players, q])

  return (
    <ScoutModuleLayout
      title="My players"
      caption="Everyone this Scout Org has added"
      stats={usage ? (
        <div className="text-right">
          <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faint">Tracked</div>
          <div className="font-mono text-lg font-bold">{usage.player_cap ? `${usage.player_count} / ${usage.player_cap}` : usage.player_count}</div>
        </div>
      ) : null}
      filters={players && players.length > 0 ? <Search value={q} onChange={setQ} placeholder="Search your players…" className="w-56" /> : null}
    >
      {usage?.at_cap && (
        <p className="text-sm px-3 py-2 rounded border border-pb-red text-pb-red mb-4">
          You've reached your {usage.tier_label} plan's {usage.player_cap}-player limit. Contact us to upgrade before adding another player.
        </p>
      )}

      {error && <p className="text-sm text-pb-red">{error}</p>}
      {players === undefined && !error && <p className="text-sm text-pb-dim">Loading…</p>}
      {players?.length === 0 && (
        <p className="text-sm text-pb-dim">
          Nobody added yet. <Link to="/betterscout/app/discover" className="underline" style={{ color: 'var(--pb-accent)' }}>discover a player</Link> to get started.
        </p>
      )}

      {players && players.length > 0 && (
        <div className="pb-card overflow-hidden">
          <div className="divide-y divide-pb-hairline">
            {shown.map((p) => {
              const t = p.stats?.totals
              return (
                <Link key={p.id} to={`/betterscout/app/players/${p.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-pb-surface2 transition-colors">
                  <PlayerAvatar name={p.name} photoUrl={p.photo_url} size={36} />
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-[13.5px] truncate">{p.name}</div>
                    <div className="font-mono text-[10.5px] text-pb-faint uppercase truncate">
                      {p.club_name || 'No club recorded'}
                      {p.source === 'manual' && <span className="ml-2 px-1.5 py-0.5 rounded bg-pb-surface2 text-pb-dim normal-case">Manual</span>}
                      {p.internal_link && <span className="ml-2 px-1.5 py-0.5 rounded bg-[var(--pb-accent)]/15 text-[var(--pb-accent)] normal-case">On BetterCricket</span>}
                    </div>
                  </div>
                  {t?.seasons !== undefined && (
                    <Sparkline seasons={p.stats.seasons} metricKey="runs" height={26} width={6} gap={2} />
                  )}
                  {t && (
                    <div className="text-right shrink-0 font-mono text-sm">
                      <span className="font-bold">{t.runs ?? 0}</span> <span className="text-pb-faint text-xs">runs</span>
                      {t.wickets > 0 && <> · <span className="font-bold">{t.wickets}</span> <span className="text-pb-faint text-xs">wkts</span></>}
                    </div>
                  )}
                  <button
                    onClick={(e) => removePlayer(e, p)}
                    disabled={removingId === p.id}
                    title="Remove from My Players"
                    aria-label="Remove from My Players"
                    className="shrink-0 text-pb-faint hover:text-pb-red p-1.5 rounded transition-colors disabled:opacity-50"
                  >
                    <Icon name="trash" size={15} />
                  </button>
                </Link>
              )
            })}
            {shown.length === 0 && <p className="px-4 py-6 text-sm text-pb-faint">No players match "{q}".</p>}
          </div>
        </div>
      )}
    </ScoutModuleLayout>
  )
}
