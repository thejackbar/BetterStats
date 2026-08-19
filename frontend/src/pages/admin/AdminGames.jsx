import { useState, useEffect, useMemo } from 'react'
import { api } from '../../lib/api'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import { formatSeason } from '../../lib/cricketFormat'

// Cricket Australia's own words for a fixture that never happened. Kept in
// step with NOT_PLAYED_STATUSES in backend/app/services/game_status.py — the
// backend is what decides, this is only how it reads.
const CALLED_OFF = ['ABANDONED', 'CANCELLED']
const isCalledOff = g => CALLED_OFF.includes((g.status || '').toUpperCase())

function StatusTag({ status }) {
  const s = (status || '').toUpperCase()
  if (!CALLED_OFF.includes(s)) return null
  return (
    <span
      className="font-mono text-[9px] tracking-wide3 px-1.5 py-0.5 rounded"
      style={{
        color: 'var(--pb-accent-ink)',
        background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)',
        border: '1px solid color-mix(in srgb, var(--pb-accent) 35%, transparent)',
      }}
    >
      {s}
    </span>
  )
}

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

  const calledOff = useMemo(() => games.filter(isCalledOff), [games])
  // A fixture nobody was named in never counted towards anyone, so saying so
  // would send an admin looking for a correction that was never needed.
  const affecting = useMemo(() => calledOff.filter(g => (g.players_named || 0) > 0), [calledOff])
  const unknownStatus = useMemo(() => games.some(g => !g.status), [games])

  return (
    <BetterStatsLayout>
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
            Match data is synced automatically and is read-only here.
          </span>
        </div>

        {error && (
          <div className="font-mono text-[11px] text-pb-red bg-pb-red/10 border border-pb-red/30 rounded px-4 py-3 mb-4">{error}</div>
        )}
        {loading && <div className="font-mono text-[11px] text-pb-faint">Loading…</div>}

        {!loading && !error && calledOff.length > 0 && (
          <div className="pb-card p-5 mb-5">
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2">
              CALLED OFF THIS SEASON
            </div>
            <p className="text-sm text-pb-dim mb-3">
              {calledOff.length === 1 ? 'One fixture was' : `${calledOff.length} fixtures were`}{' '}
              abandoned or cancelled. PlayHQ counts a player as having played once they are
              named in the side, so{' '}
              {affecting.length === 0
                ? 'nobody was named in these and no match counts are affected.'
                : `these no longer count towards the matches played of the ${
                    affecting.length === 1 ? 'side' : 'sides'
                  } named in them.`}{' '}
              A game abandoned after play started still counts.
            </p>
            {calledOff.map(g => (
              <div key={g.id} className="flex items-baseline gap-2 py-1.5 pb-hairline-t first:border-t-0">
                <span className="font-mono text-[10px] text-pb-faintest w-20 shrink-0">{g.played_at || '—'}</span>
                <span className="text-sm text-pb-text truncate flex-1">{g.home_team} v {g.away_team}</span>
                {g.players_named > 0 && (
                  <span className="font-mono text-[10px] text-pb-faint shrink-0">
                    {g.players_named} named
                  </span>
                )}
                <StatusTag status={g.status} />
              </div>
            ))}
          </div>
        )}

        {!loading && !error && calledOff.length === 0 && unknownStatus && games.length > 0 && (
          <div className="font-mono text-[10px] text-pb-faint mb-4">
            Some of this season's fixtures have no status from PlayHQ yet. Run a sync to fill it in.
          </div>
        )}

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
                <span className="text-pb-dim truncate">
                  {isCalledOff(g) ? <StatusTag status={g.status} /> : (g.result || '—')}
                </span>
                <span className="font-mono text-[10px] text-pb-faintest">{g.played_at || '—'}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </BetterStatsLayout>
  )
}
