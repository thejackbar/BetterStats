import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import LoadingSpinner from '../../components/LoadingSpinner'
import StatCard from '../../components/StatCard'
import { aflApi } from '../aflApi'
import { Select, GameRow } from '../components/bits'

/**
 * The same record as the cards above, split by team. Every row is built from
 * the same filters the totals are, so the columns add up to them.
 *
 * Hidden for a single team: with a grade filter applied it would just restate
 * the totals directly above it.
 *
 * The "No result" column only appears when there is one to report. It closes
 * the gap between Played and Won+Lost+Drawn — a completed game that carries no
 * score at all, which plenty of junior competitions publish. Without it a row
 * reading "Played 9, Won 4, Lost 2" leaves three games unaccounted for and no
 * way to tell a missing score from a missing game.
 */
function TeamRecords({ rows }) {
  const teams = rows || []
  if (teams.length < 2) return null
  const anyUnresolved = teams.some(r => (r.no_result || 0) > 0)

  const winPct = (r) => {
    // Out of the games that actually have a result — a team whose scores were
    // never published shouldn't read as having lost those games.
    const decided = r.wins + r.losses + r.draws
    return decided ? Math.round((r.wins / decided) * 100) : null
  }

  const headers = ['Played', 'Won', 'Lost', 'Drawn',
    ...(anyUnresolved ? ['No result'] : []), 'Win %']

  return (
    <div className="pb-card overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="pb-hairline-b">
          <tr>
            <th className="px-3 py-2 text-left font-mono text-[10px] uppercase tracking-wide text-pb-faint">Team</th>
            {headers.map(h => (
              <th key={h} className="px-3 py-2 text-right font-mono text-[10px] uppercase tracking-wide text-pb-faint whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {teams.map(r => {
            const pct = winPct(r)
            return (
              <tr key={r.team} className="pb-hairline-b last:border-0 hover:bg-pb-surface2/50">
                <td className="px-3 py-2.5 font-medium">{r.team}</td>
                <td className="px-3 py-2.5 text-right pb-num">{r.played}</td>
                <td className="px-3 py-2.5 text-right pb-num font-semibold" style={{ color: 'var(--pb-accent)' }}>{r.wins}</td>
                <td className="px-3 py-2.5 text-right pb-num">{r.losses}</td>
                <td className="px-3 py-2.5 text-right pb-num">{r.draws}</td>
                {anyUnresolved && (
                  <td className="px-3 py-2.5 text-right pb-num text-pb-faint">{r.no_result || 0}</td>
                )}
                <td className="px-3 py-2.5 text-right pb-num text-pb-dim">{pct == null ? '—' : `${pct}%`}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// The endpoint caps a page at 200 rows. A club with a century of results has
// thousands, so the list is paged rather than truncated — before this it asked
// for 100 and stopped, which for Hampton Hammers meant their history appeared
// to end in the mid-1970s with nothing on the page saying otherwise.
const PAGE_SIZE = 200

export default function Games() {
  const { club } = useOutletContext()
  const [seasonId, setSeasonId] = useState(null)
  const [gradeId, setGradeId] = useState(null)
  const [finalsOnly, setFinalsOnly] = useState(false)
  const [data, setData] = useState(null)
  // Every page fetched so far, concatenated. Kept separately from `data` so
  // the summary/by_team blocks (which always describe the WHOLE filtered set,
  // not the loaded page) aren't rebuilt on each Load more.
  const [games, setGames] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const base = `/${club.slug}`

  const gradeOptions = useMemo(() => {
    const grades = (club.grades || []).filter(g => !seasonId || (g.season_ids || []).includes(seasonId))
    return grades.map(g => ({ value: g.id, label: g.display_name_override || g.name }))
  }, [club.grades, seasonId])

  useEffect(() => { setGradeId(null) }, [seasonId])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setGames([])
    aflApi.getResults(club.id, {
      season_id: seasonId, grade_id: gradeId, finals_only: finalsOnly,
      limit: PAGE_SIZE, offset: 0,
    }).then(d => {
      // A filter changed while this was in flight — its results are for the
      // old filters, so dropping them is the whole point.
      if (cancelled) return
      setData(d)
      setGames(d.games || [])
    }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [club.id, seasonId, gradeId, finalsOnly])

  const loadMore = async () => {
    setLoadingMore(true)
    try {
      const d = await aflApi.getResults(club.id, {
        season_id: seasonId, grade_id: gradeId, finals_only: finalsOnly,
        limit: PAGE_SIZE, offset: games.length,
      })
      setGames(prev => [...prev, ...(d.games || [])])
    } finally {
      setLoadingMore(false)
    }
  }

  const s = data?.summary || {}
  const total = data?.total ?? games.length
  const hasMore = games.length < total

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold">Games</h1>
        <div className="ml-auto flex flex-wrap gap-2 items-center">
          <Select value={seasonId} onChange={setSeasonId} placeholder="All seasons"
                  options={(club.seasons || []).map(x => ({ value: x.id, label: x.name }))} />
          <Select value={gradeId} onChange={setGradeId} placeholder="All grades" options={gradeOptions} />
          <label className="text-sm text-pb-dim flex items-center gap-1.5">
            <input type="checkbox" checked={finalsOnly} onChange={e => setFinalsOnly(e.target.checked)} />
            Finals only
          </label>
        </div>
      </div>

      {/* A fifth card only when there's something to explain — see the note on
          TeamRecords. It's what makes Played reconcile with W/L/D. */}
      <div className={`grid gap-3 ${(s.no_result || 0) > 0 ? 'grid-cols-3 md:grid-cols-5' : 'grid-cols-4'}`}>
        <StatCard label="Played" value={s.played} />
        <StatCard label="Wins" value={s.wins} accent />
        <StatCard label="Losses" value={s.losses} />
        <StatCard label="Draws" value={s.draws} />
        {(s.no_result || 0) > 0 && <StatCard label="No result" value={s.no_result} />}
      </div>

      {(s.no_result || 0) > 0 && (
        <p className="text-[11px] text-pb-faintest leading-snug">
          {s.no_result} completed {s.no_result === 1 ? 'game has' : 'games have'} no score
          recorded against {s.no_result === 1 ? 'it' : 'them'}, so {s.no_result === 1 ? 'it' : 'they'}{' '}
          can't be counted as a win, loss or draw. Junior competitions often publish a finished
          fixture without scores.
        </p>
      )}

      <TeamRecords rows={data?.by_team} />

      {loading
        ? <div className="pt-8 flex justify-center"><LoadingSpinner /></div>
        : (
          <div className="space-y-2">
            {games.map(g => <GameRow key={g.id} game={g} base={base} />)}
            {games.length === 0 && <p className="text-sm text-pb-faint pt-4">No games match these filters.</p>}
            {games.length > 0 && (
              <div className="pt-3 flex flex-col items-center gap-2">
                <span className="font-mono text-[11px] text-pb-faintest">
                  Showing {games.length.toLocaleString()} of {total.toLocaleString()}
                </span>
                {hasMore && (
                  <button
                    onClick={loadMore}
                    disabled={loadingMore}
                    className="px-4 py-2 rounded text-sm font-semibold bg-pb-surface2 text-pb-text hover:text-[var(--pb-accent)] disabled:opacity-50"
                  >
                    {loadingMore ? 'Loading…' : `Load ${Math.min(PAGE_SIZE, total - games.length).toLocaleString()} more`}
                  </button>
                )}
              </div>
            )}
          </div>
        )}
    </div>
  )
}
