import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import clsx from 'clsx'
import LoadingSpinner from '../../components/LoadingSpinner'
import { aflApi } from '../aflApi'
import { Select, PlayerCell, displayName } from '../components/bits'
import AllTimeGames from '../components/AllTimeGames'

// `career: true` marks a board that is career-wide by definition and so takes
// no season or grade filter — the filters are hidden for it rather than shown
// doing nothing.
const ALL_STATS = [
  { key: 'games', label: 'Games' },
  { key: 'goals', label: 'Goals' },
  { key: 'all_time_games', label: 'All Time Games', career: true },
  { key: 'bogs', label: 'Best on Ground', flag: 'public_show_bog_leaderboard' },
  { key: 'club_bf_votes', label: 'Club B&F votes', flag: 'public_show_club_bf_leaderboard' },
  { key: 'comp_bf_votes', label: 'Competition B&F votes', flag: 'public_show_comp_bf_leaderboard' },
]

// Career goals per game. Guarded rather than shown as 0.00 — a row carrying
// goals but no games (an older Import Stats upload that recorded totals
// without a games count) would otherwise read as if the player never scored.
const avgGoals = (r) => ((r.games ?? 0) > 0 ? (r.goals / r.games).toFixed(2) : '—')

export default function Leaderboard() {
  const { club } = useOutletContext()
  // Games and Goals always show; the rest are each a club's own opt-out
  // (Settings → Public leaderboard) — default true, so nothing already-live
  // disappears until a club actively turns one off.
  const STATS = ALL_STATS.filter(s => !s.flag || club[s.flag] !== false)
  const [stat, setStat] = useState('games')
  const [seasonId, setSeasonId] = useState(null)
  const [gradeId, setGradeId] = useState(null)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const base = `/${club.slug}`

  // The active stat could be one this club has since turned off — fall back
  // to the always-available Games tab rather than showing a dead selection.
  useEffect(() => {
    if (!STATS.some(s => s.key === stat)) setStat('games')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [club.id])

  const statInfo = STATS.find(s => s.key === stat) || STATS[0]
  const isCareerBoard = !!statInfo?.career

  useEffect(() => { setGradeId(null) }, [seasonId])

  useEffect(() => {
    // A career-wide board owns its own fetch (see AllTimeGames) — the
    // leaderboard endpoint has no stat for it and would 422 on the name.
    if (isCareerBoard) return
    setLoading(true)
    // A season's full roster (every grade combined) can run well past 50 —
    // this is meant to be the whole list, not a top-N cut-off, so ask for
    // the backend's max rather than an arbitrary round number.
    aflApi.getLeaderboard(club.id, { stat, season_id: seasonId, grade_id: gradeId, limit: 500 })
      .then(setData)
      .finally(() => setLoading(false))
  }, [club.id, stat, seasonId, gradeId, isCareerBoard])

  const gradeOptions = (club.grades || [])
    .filter(g => !seasonId || (g.season_ids || []).includes(seasonId))
    .map(g => ({ value: g.id, label: g.display_name_override || g.name }))

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold">Leaderboard</h1>
        {isCareerBoard
          ? <span className="ml-auto text-sm text-pb-faint">Every season, every grade</span>
          : (
            <div className="ml-auto flex flex-wrap gap-2">
              <Select value={seasonId} onChange={setSeasonId} placeholder="All seasons"
                      options={(club.seasons || []).map(x => ({ value: x.id, label: x.name }))} />
              <Select value={gradeId} onChange={setGradeId} placeholder="All grades" options={gradeOptions} />
            </div>
          )}
      </div>

      <div className="flex flex-wrap gap-1">
        {STATS.map(s => (
          <button key={s.key} onClick={() => setStat(s.key)}
                  className={clsx('px-3 py-1.5 rounded text-sm font-medium',
                    stat === s.key ? 'bg-[var(--pb-accent)] text-black' : 'bg-pb-surface2 text-pb-dim hover:text-pb-text')}>
            {s.label}
          </button>
        ))}
      </div>

      {isCareerBoard ? <AllTimeGames club={club} base={base} /> : loading && !data
        ? <div className="pt-8 flex justify-center"><LoadingSpinner /></div>
        : (
          <div className="pb-card overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="pb-hairline-b">
                <tr>
                  <th className="px-3 py-2 text-left font-mono text-[10px] uppercase text-pb-faint w-10">#</th>
                  <th className="px-3 py-2 text-left font-mono text-[10px] uppercase text-pb-faint">Player</th>
                  <th className="px-3 py-2 text-right font-mono text-[10px] uppercase text-pb-faint">GP</th>
                  <th className="px-3 py-2 text-right font-mono text-[10px] uppercase text-pb-faint">Goals</th>
                  <th className="px-3 py-2 text-right font-mono text-[10px] uppercase text-pb-faint">Avg goals</th>
                  <th className="px-3 py-2 text-right font-mono text-[10px] uppercase text-[var(--pb-accent)]">{statInfo?.label}</th>
                </tr>
              </thead>
              <tbody>
                {(data?.rows || []).map((r, i) => (
                  <tr key={r.player_id} className="pb-hairline-b last:border-0 hover:bg-pb-surface2/50">
                    <td className="px-3 py-2 font-mono text-pb-faintest">{i + 1}</td>
                    <td className="px-3 py-2"><PlayerCell id={r.player_id} name={displayName(r)} base={base} photoUrl={r.photo_url} /></td>
                    <td className="px-3 py-2 text-right pb-num">{r.games}</td>
                    <td className="px-3 py-2 text-right pb-num">{r.goals}</td>
                    <td className="px-3 py-2 text-right pb-num text-pb-dim">{avgGoals(r)}</td>
                    <td className="px-3 py-2 text-right pb-num font-bold text-[var(--pb-accent)]">{r.value}</td>
                  </tr>
                ))}
                {(data?.rows || []).length === 0 && (
                  <tr><td colSpan={6} className="px-3 py-4 text-pb-faint text-sm">Nothing here for these filters yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
    </div>
  )
}
