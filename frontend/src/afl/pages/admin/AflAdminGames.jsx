import { useEffect, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import { aflApi } from '../../aflApi'
import { SectionTitle, Select } from '../../components/bits'
import LoadingSpinner from '../../../components/LoadingSpinner'

// Every game the club holds, synced or imported, with how far the sync got for
// it. The one flag worth reading is "stats pending": a finished synced game
// whose player stats haven't been pulled yet, which is why a player's total can
// look a game short until the next sync.
const PAGE = 100

function scoreText(g) {
  if (g.is_bye) return 'Bye'
  if (g.home_score == null && g.away_score == null) return g.result_note || '—'
  return `${g.home_score ?? '—'} – ${g.away_score ?? '—'}`
}

export default function AflAdminGames() {
  const { settings } = useOutletContext() || {}
  const [seasons, setSeasons] = useState([])
  const [season, setSeason] = useState(null)
  const [source, setSource] = useState(null)
  const [q, setQ] = useState('')
  const [data, setData] = useState(null)
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState(null)

  useEffect(() => { aflApi.adminListSeasons().then(r => setSeasons(Array.isArray(r) ? r : (r?.seasons || []))).catch(() => {}) }, [])

  useEffect(() => {
    const t = setTimeout(() => {
      setData(null)
      aflApi.adminListGames({ season_id: season, source, q: q.trim(), limit: PAGE, offset })
        .then(setData).catch(e => { setError(e.message); setData({ games: [], total: 0 }) })
    }, 200)
    return () => clearTimeout(t)
  }, [season, source, q, offset])

  const slug = settings?.slug
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">Matches</h1>
        <p className="text-sm text-pb-dim mt-1">Every game the club holds, and whether its player stats have landed.</p>
      </div>
      {error && <p className="text-sm text-[var(--pb-negative)]">{error}</p>}
      <div className="flex flex-wrap gap-2 items-center">
        <Select value={season} onChange={v => { setSeason(v); setOffset(0) }} placeholder="All seasons"
          options={seasons.map(s => ({ value: s.id, label: s.name }))} />
        <Select value={source} onChange={v => { setSource(v); setOffset(0) }} placeholder="Synced and imported"
          options={[{ value: 'playhq', label: 'Synced from PlayHQ' }, { value: 'import', label: 'Imported' }]} />
        <input value={q} onChange={e => { setQ(e.target.value); setOffset(0) }} placeholder="Search team or grade"
          className="flex-1 min-w-[180px] bg-pb-surface2 border border-pb-hairline rounded px-3 py-1.5 text-sm" />
      </div>
      <div className="pb-card p-4 overflow-x-auto">
        {data === null ? <LoadingSpinner /> : (
          <>
            <SectionTitle right={<span className="font-mono text-[10px] text-pb-faint">{data.total} games</span>}>Games</SectionTitle>
            {data.games.length === 0 ? <p className="text-sm text-pb-faint">No games match.</p> : (
              <table className="w-full text-sm min-w-[640px]">
                <thead>
                  <tr className="text-left font-mono text-[10px] uppercase text-pb-faint">
                    <th className="py-1 pr-2">Date</th><th className="pr-2">Grade</th><th className="pr-2">Match</th>
                    <th className="pr-2">Score</th><th className="pr-2">Source</th><th className="pr-2">Stats</th>
                  </tr>
                </thead>
                <tbody>
                  {data.games.map(g => (
                    <tr key={g.id} className="pb-hairline-t" data-testid="game-row">
                      <td className="py-2 pr-2 font-mono text-[11px] text-pb-dim whitespace-nowrap">{g.played_at ? new Date(g.played_at).toLocaleDateString('en-AU') : '—'}</td>
                      <td className="pr-2 text-pb-dim">{g.grade_name}{g.round_name ? <span className="text-pb-faint"> · {g.round_name}</span> : null}</td>
                      <td className="pr-2">{slug ? <Link to={`/${slug}/games/${g.id}`} className="hover:underline">{g.home_team} v {g.away_team}</Link> : `${g.home_team} v ${g.away_team}`}</td>
                      <td className="pr-2 whitespace-nowrap">{scoreText(g)}</td>
                      <td className="pr-2 text-pb-dim">{g.source === 'import' ? 'Imported' : 'PlayHQ'}</td>
                      <td className="pr-2">
                        {g.stats_pending ? <span className="text-[var(--pb-warning,#d9a53f)]" title="Finished, player stats not pulled yet. The next sync fetches them.">Pending</span>
                          : g.source === 'import' ? <span className="text-pb-faint">Result only</span>
                          : g.status !== 'FINAL' ? <span className="text-pb-faint">{(g.status || 'Scheduled').toLowerCase()}</span>
                          : <span className="text-pb-dim">{g.our_lines} players</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {data.total > PAGE && (
              <div className="flex items-center justify-between mt-3 text-sm">
                <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))} className="underline disabled:opacity-40">Newer</button>
                <span className="text-pb-faint">{offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}</span>
                <button disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)} className="underline disabled:opacity-40">Older</button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
