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

  // "Biggest wins"/"Highest scores" show only the opposition's name, not
  // both sides — our_side tells us which of home/away team is the opponent.
  const opponent = r => (r.our_side === 'HOME' ? r.away_team : r.home_team)

  const gameBoard = (title, rows, value) => (
    <div className="pb-card p-4">
      <SectionTitle>{title}</SectionTitle>
      {(rows || []).length === 0 && <p className="text-sm text-pb-faint">No data yet.</p>}
      <ol className="space-y-1.5">
        {(rows || []).map((r, i) => (
          <li key={r.game_id + String(i)} className="flex items-center gap-2 text-sm">
            <span className="font-mono text-pb-faintest w-4">{i + 1}</span>
            <Link to={`${base}/games/${r.game_id}`} className="truncate hover:text-[var(--pb-accent)]">
              vs {opponent(r)}
            </Link>
            <span className="text-[11px] text-pb-faintest hidden sm:block shrink-0">{r.season_name}</span>
            <span className="ml-auto pb-num font-semibold shrink-0">{value(r)}</span>
          </li>
        ))}
      </ol>
    </div>
  )

  const hasGoalsInGame = (data?.most_goals_in_a_game || []).length > 0
  const hasBogs = (data?.most_bogs_career || []).length > 0
  const hasBiggestWins = (data?.biggest_wins || []).length > 0
  const hasHighestScores = (data?.highest_scores || []).length > 0

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex items-stretch gap-3.5">
          <span className="w-1 rounded-full shrink-0" style={{ background: 'var(--pb-gradient)' }} />
          <h1 className="font-display text-3xl sm:text-4xl font-bold tracking-tight text-pb-text">Club records</h1>
        </div>
        <Select value={gradeId} onChange={setGradeId} placeholder="All grades"
                options={(club.grades || []).map(g => ({ value: g.id, label: g.display_name_override || g.name }))} />
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        {playerBoard('Most games', data?.most_games_career, 'games')}
        {playerBoard('Most goals', data?.most_goals_career, 'goals')}
        {playerBoard('Most goals in a season', data?.most_goals_in_a_season, 'goals', '',
          r => r.season_name)}
        {hasGoalsInGame && playerBoard('Most goals in a game', data?.most_goals_in_a_game, 'goals', '',
          r => `${r.round_name || ''} ${r.season_name || ''}`)}
        {hasBogs && playerBoard('Most best on grounds', data?.most_bogs_career, 'bogs')}
        {hasBiggestWins && gameBoard('Biggest wins', data?.biggest_wins, r => `${r.margin} pts`)}
        {hasHighestScores && gameBoard('Highest scores', data?.highest_scores,
          r => scoreLine(r.our_goals, r.our_behinds, r.our_score))}
      </div>
    </div>
  )
}
