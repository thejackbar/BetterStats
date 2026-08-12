import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { scoutApi } from '../lib/scoutApi'

export default function ScoutPlayers() {
  const [players, setPlayers] = useState(undefined) // undefined = loading
  const [error, setError] = useState(null)

  useEffect(() => {
    scoutApi.listPlayers().then(setPlayers).catch((err) => setError(err.message))
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">My players</h1>
        <p className="text-sm text-pb-dim">Everyone this Scout Org has added.</p>
      </div>

      {error && <p className="text-sm text-[var(--pb-negative)]">{error}</p>}
      {players === undefined && !error && <p className="text-sm text-pb-dim">Loading…</p>}
      {players?.length === 0 && (
        <p className="text-sm text-pb-dim">
          Nobody added yet — <Link to="/betterscout/app/discover" className="underline">discover a player</Link> to get started.
        </p>
      )}

      {players && players.length > 0 && (
        <div className="pb-card divide-y divide-pb-hairline">
          {players.map((p) => (
            <Link key={p.id} to={`/betterscout/app/players/${p.id}`}
                  className="flex items-center justify-between px-4 py-3 hover:bg-pb-surface2">
              <div>
                <div className="font-medium">{p.name}</div>
                <div className="text-xs text-pb-dim">
                  {p.club_name || 'No club recorded'}
                  {p.source === 'manual' && <span className="ml-2 px-1.5 py-0.5 rounded bg-pb-surface2 text-pb-dim">Manual</span>}
                </div>
              </div>
              {p.stats?.totals && (
                <div className="text-sm text-pb-dim font-mono">
                  {p.stats.totals.runs ?? 0} runs · {p.stats.totals.wickets ?? 0} wkts
                </div>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
