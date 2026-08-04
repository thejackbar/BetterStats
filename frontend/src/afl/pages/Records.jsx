import { useEffect, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import LoadingSpinner from '../../components/LoadingSpinner'
import { aflApi, scoreLine } from '../aflApi'
import { SectionTitle, Select, PlayerCell, displayName } from '../components/bits'

export default function Records() {
  const { club } = useOutletContext()
  const [gradeId, setGradeId] = useState(null)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const base = `/${club.slug}`

  useEffect(() => {
    setLoading(true)
    aflApi.getRecords(club.id, { grade_id: gradeId })
      .then(setData)
      .finally(() => setLoading(false))
  }, [club.id, gradeId])

  if (loading && !data) return <div className="pt-16 flex justify-center"><LoadingSpinner /></div>

  const playerBoard = (title, rows, valueKey, suffix, context) => (
    <div className="pb-card p-4">
      <SectionTitle>{title}</SectionTitle>
      {(rows || []).length === 0 && <p className="text-sm text-pb-faint">No data yet.</p>}
      <ol className="space-y-1.5">
        {(rows || []).map((r, i) => (
          <li key={i} className="flex items-center gap-2 text-sm">
            <span className="font-mono text-pb-faintest w-4">{i + 1}</span>
            <PlayerCell id={r.player_id} name={displayName(r)} base={base} />
            {context && <span className="text-[11px] text-pb-faintest truncate hidden sm:block">{context(r)}</span>}
            <span className="ml-auto pb-num font-semibold shrink-0">{r[valueKey]}{suffix || ''}</span>
          </li>
        ))}
      </ol>
    </div>
  )

  const gameBoard = (title, rows, value) => (
    <div className="pb-card p-4">
      <SectionTitle>{title}</SectionTitle>
      {(rows || []).length === 0 && <p className="text-sm text-pb-faint">No data yet.</p>}
      <ol className="space-y-1.5">
        {(rows || []).map((r, i) => (
          <li key={r.game_id + String(i)} className="flex items-center gap-2 text-sm">
            <span className="font-mono text-pb-faintest w-4">{i + 1}</span>
            <Link to={`${base}/games/${r.game_id}`} className="truncate hover:text-[var(--pb-accent)]">
              {r.home_team} v {r.away_team}
            </Link>
            <span className="text-[11px] text-pb-faintest hidden sm:block shrink-0">{r.season_name}</span>
            <span className="ml-auto pb-num font-semibold shrink-0">{value(r)}</span>
          </li>
        ))}
      </ol>
    </div>
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold">Club records</h1>
        <div className="ml-auto">
          <Select value={gradeId} onChange={setGradeId} placeholder="All grades"
                  options={(club.grades || []).map(g => ({ value: g.id, label: g.display_name_override || g.name }))} />
        </div>
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        {playerBoard('Most goals in a game', data?.most_goals_in_a_game, 'goals', '',
          r => `${r.round_name || ''} ${r.season_name || ''}`)}
        {playerBoard('Most goals in a season', data?.most_goals_in_a_season, 'goals', '',
          r => r.season_name)}
        {playerBoard('Most career goals', data?.most_goals_career, 'goals')}
        {playerBoard('Most career games', data?.most_games_career, 'games')}
        {playerBoard('Most best on grounds', data?.most_bogs_career, 'bogs')}
        {gameBoard('Biggest wins', data?.biggest_wins, r => `${r.margin} pts`)}
        {gameBoard('Highest scores', data?.highest_scores,
          r => scoreLine(r.our_goals, r.our_behinds, r.our_score))}
      </div>
    </div>
  )
}
