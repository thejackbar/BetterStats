import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

export default function AdminGames() {
  const [seasons, setSeasons] = useState([])
  const [selectedSeason, setSelectedSeason] = useState('')
  const [games, setGames] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.adminListSeasons()
      .then(s => { setSeasons(s); if (s.length > 0) setSelectedSeason(s[0].id) })
      .catch(err => setError(err.message || 'Failed to load seasons'))
  }, [])

  useEffect(() => {
    if (!selectedSeason) return
    setLoading(true)
    setError(null)
    api.adminListGames(selectedSeason)
      .then(setGames)
      .catch(err => setError(err.message || 'Failed to load matches'))
      .finally(() => setLoading(false))
  }, [selectedSeason])

  return (
    <AdminLayout>
      <div className="max-w-4xl">
        <h1 className="text-xl font-display font-bold text-white mb-4">Matches</h1>

        <div className="flex items-center gap-3 mb-4">
          <select
            value={selectedSeason}
            onChange={e => setSelectedSeason(e.target.value)}
            className="bg-navy-800 border border-navy-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-accent"
          >
            {seasons.map(s => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          <span className="text-slate-500 text-xs">
            Match data is synced from PlayHQ and is read-only here.
          </span>
        </div>

        {error && <div className="text-red-400 text-sm bg-red-900/20 border border-red-800 rounded p-3">{error}</div>}
        {loading && <div className="text-slate-400 text-sm">Loading…</div>}

        {!loading && !error && games.length === 0 && (
          <div className="text-slate-500 text-sm">No matches found for this season.</div>
        )}

        {!loading && games.length > 0 && (
          <div className="bg-navy-900 border border-navy-700 rounded-lg overflow-hidden">
            <div className="grid grid-cols-[1fr_1fr_auto] text-xs text-slate-500 px-4 py-2 border-b border-navy-800">
              <span>Teams</span>
              <span>Result</span>
              <span>Date</span>
            </div>
            {games.map((g, i) => (
              <div key={g.id} className={`grid grid-cols-[1fr_1fr_auto] px-4 py-3 text-sm ${i > 0 ? 'border-t border-navy-800' : ''}`}>
                <span className="text-white truncate">{g.home_team} v {g.away_team}</span>
                <span className="text-slate-300 truncate">{g.result || '—'}</span>
                <span className="text-slate-500 text-xs">{g.played_at || '—'}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
