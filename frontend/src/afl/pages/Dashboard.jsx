import { useEffect, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import StatCard from '../../components/StatCard'
import LoadingSpinner from '../../components/LoadingSpinner'
import { aflApi } from '../aflApi'
import { SectionTitle, Select, GameRow, PlayerCell, displayName } from '../components/bits'

export default function Dashboard() {
  const { club } = useOutletContext()
  const [seasonId, setSeasonId] = useState(null)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const base = `/${club.slug}`

  useEffect(() => {
    setLoading(true)
    aflApi.getSummary(club.id, { season_id: seasonId })
      .then(setData)
      .finally(() => setLoading(false))
  }, [club.id, seasonId])

  if (loading && !data) return <div className="pt-16 flex justify-center"><LoadingSpinner /></div>
  const s = data?.summary || {}

  const board = (title, rows, statKey, statLabel) => (
    <div className="pb-card p-4">
      <SectionTitle>{title}</SectionTitle>
      {(rows || []).length === 0 && <p className="text-sm text-pb-faint">No data yet.</p>}
      <ol className="space-y-2">
        {(rows || []).map((r, i) => (
          <li key={r.player_id} className="flex items-center gap-2 text-sm">
            <span className="font-mono text-pb-faintest w-4">{i + 1}</span>
            <PlayerCell id={r.player_id} name={displayName(r)} base={base} photoUrl={r.photo_url} />
            <span className="ml-auto pb-num font-semibold">{r[statKey]}</span>
            <span className="text-[10px] text-pb-faintest font-mono uppercase">{statLabel}</span>
          </li>
        ))}
      </ol>
    </div>
  )

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold">{club.name}</h1>
        <div className="ml-auto">
          <Select
            value={seasonId}
            onChange={setSeasonId}
            placeholder="All seasons"
            options={(club.seasons || []).map(x => ({ value: x.id, label: x.name }))}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Games" value={s.played} accent large />
        <StatCard label="Wins" value={s.wins} large />
        <StatCard label="Losses" value={s.losses} large />
        <StatCard label="Draws" value={s.draws} large />
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        {board('Leading goal kickers', data?.top_goal_kickers, 'goals', 'goals')}
        {board('Most games', data?.most_games, 'games', 'games')}
        {board('Most best on grounds', data?.most_bogs, 'bogs', 'BOG')}
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <div>
          <SectionTitle right={<Link to={`${base}/games`} className="text-xs text-[var(--pb-accent)]">All games →</Link>}>
            Recent results
          </SectionTitle>
          <div className="space-y-2">
            {(data?.recent_games || []).map(g => <GameRow key={g.id} game={g} base={base} />)}
            {(data?.recent_games || []).length === 0 && <p className="text-sm text-pb-faint">No results synced yet.</p>}
          </div>
        </div>
        <div>
          <SectionTitle>Upcoming</SectionTitle>
          <div className="space-y-2">
            {(data?.upcoming_games || []).map(g => (
              <div key={g.id} className="pb-card p-3 text-sm flex flex-wrap gap-x-4 gap-y-1 items-center">
                <div className="w-28 shrink-0">
                  <div className="text-[11px] text-pb-faint font-mono">{g.round_name}</div>
                  <div className="text-[11px] text-pb-faintest font-mono">{g.played_at} {g.start_time ? g.start_time.slice(0, 5) : ''}</div>
                </div>
                <div className="flex-1">
                  <div>{g.home_team} <span className="text-pb-faint">v</span> {g.away_team}</div>
                  <div className="text-[11px] text-pb-faint">{g.venue || ''}</div>
                </div>
                <span className="text-[11px] text-pb-faint">{g.grade_name}</span>
              </div>
            ))}
            {(data?.upcoming_games || []).length === 0 && <p className="text-sm text-pb-faint">No upcoming fixtures.</p>}
          </div>
        </div>
      </div>
    </div>
  )
}
