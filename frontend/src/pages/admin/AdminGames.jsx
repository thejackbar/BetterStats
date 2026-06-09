import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import { formatSeason } from '../../lib/cricketFormat'

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
        <h1 className="font-display font-bold text-2xl text-pb-text mb-4">Matches</h1>

        <div className="flex items-center gap-3 mb-5">
          <select
            value={selectedSeason}
            onChange={e => setSelectedSeason(e.target.value)}
            className="bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
          >
            {seasons.map(s => (
              <option key={s.id} value={s.id}>{formatSeason(s)}</option>
            ))}
          </select>
          <span className="font-mono text-[10px] text-pb-faint">
            Match data is synced from PlayHQ and is read-only here.
          </span>
        </div>

        {error && (
          <div className="font-mono text-[11px] text-pb-red bg-pb-red/10 border border-pb-red/30 rounded px-4 py-3 mb-4">{error}</div>
        )}
        {loading && <div className="font-mono text-[11px] text-pb-faint">Loading…</div>}

        {!loading && !error && games.length === 0 && (
          <div className="font-mono text-[11px] text-pb-faint">No matches found for this season.</div>
        )}

        {!loading && games.length > 0 && (
          <div className="pb-card overflow-hidden">
            <div className="grid grid-cols-[1fr_1fr_auto] font-mono text-[10px] tracking-wide3 text-pb-faint px-5 py-2.5 bg-pb-surface2/40">
              <span>TEAMS</span>
              <span>RESULT</span>
              <span>DATE</span>
            </div>
            {games.map((g, i) => (
              <div key={g.id} className={`grid grid-cols-[1fr_1fr_auto] px-5 py-3 text-sm ${i > 0 ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                <span className="text-pb-text truncate">{g.home_team} v {g.away_team}</span>
                <span className="text-pb-dim truncate">{g.result || '—'}</span>
                <span className="font-mono text-[10px] text-pb-faintest">{g.played_at || '—'}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
