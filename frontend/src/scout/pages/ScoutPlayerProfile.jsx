import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { scoutApi } from '../lib/scoutApi'

export default function ScoutPlayerProfile() {
  const { id } = useParams()
  const [player, setPlayer] = useState(undefined) // undefined = loading
  const [error, setError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)

  const load = () => {
    scoutApi.getPlayer(id).then(setPlayer).catch((err) => setError(err.message))
  }

  useEffect(() => { load() }, [id])

  const refresh = async () => {
    setRefreshing(true)
    setError(null)
    try {
      await scoutApi.refreshPlayer(id)
      // Refresh kicks off a background rebuild — a fresh snapshot lands a
      // little after this returns, same "check back shortly" posture as the
      // club roster build.
      setTimeout(load, 4000)
    } catch (err) {
      setError(err.message)
    } finally {
      setRefreshing(false)
    }
  }

  if (error) return <p className="text-sm text-[var(--pb-negative)]">{error}</p>
  if (player === undefined) return <p className="text-sm text-pb-dim">Loading…</p>

  const totals = player.stats?.totals
  const seasons = player.stats?.seasons || []

  return (
    <div className="space-y-6">
      <Link to="/betterscout/app/players" className="text-sm text-pb-dim hover:text-pb-text">← My players</Link>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold">{player.name}</h1>
          <p className="text-sm text-pb-dim">
            {player.club_name || 'No club recorded'}
            {player.source === 'manual' && <span className="ml-2 px-1.5 py-0.5 rounded bg-pb-surface2 text-pb-dim">Manually added</span>}
          </p>
        </div>
        {player.source === 'au_grassroots' && (
          <button onClick={refresh} disabled={refreshing}
                  className="text-sm px-3 py-1.5 rounded border border-pb-hairline hover:bg-pb-surface2 disabled:opacity-50">
            {refreshing ? 'Refreshing…' : 'Refresh stats'}
          </button>
        )}
      </div>

      {!totals && (
        <p className="text-sm text-pb-dim">
          {player.source === 'manual' ? 'No automated stats — manually added.' : 'No stats available yet.'}
        </p>
      )}

      {totals && (
        <>
          <div className="pb-card p-4 grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            <Stat label="Matches" value={totals.matches} />
            <Stat label="Runs" value={totals.runs} />
            <Stat label="Average" value={totals.average} />
            <Stat label="Strike rate" value={totals.strike_rate} />
            <Stat label="Wickets" value={totals.wickets} />
            <Stat label="Economy" value={totals.economy} />
            <Stat label="Best figures" value={totals.best} />
            <Stat label="Catches" value={totals.catches} />
          </div>

          <div className="pb-card overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-pb-dim text-xs uppercase font-mono">
                <tr className="border-b border-pb-hairline">
                  <th className="text-left px-3 py-2">Season</th>
                  <th className="text-right px-3 py-2">Matches</th>
                  <th className="text-right px-3 py-2">Runs</th>
                  <th className="text-right px-3 py-2">Avg</th>
                  <th className="text-right px-3 py-2">Wkts</th>
                  <th className="text-right px-3 py-2">Econ</th>
                </tr>
              </thead>
              <tbody>
                {seasons.map((s) => (
                  <tr key={s.year} className="border-b border-pb-hairline last:border-0">
                    <td className="px-3 py-2">{s.year}</td>
                    <td className="px-3 py-2 text-right">{s.matches}</td>
                    <td className="px-3 py-2 text-right">{s.runs}</td>
                    <td className="px-3 py-2 text-right">{s.average ?? '—'}</td>
                    <td className="px-3 py-2 text-right">{s.wickets}</td>
                    <td className="px-3 py-2 text-right">{s.economy ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div>
      <div className="text-xs text-pb-dim uppercase font-mono">{label}</div>
      <div className="text-lg font-semibold">{value ?? '—'}</div>
    </div>
  )
}
