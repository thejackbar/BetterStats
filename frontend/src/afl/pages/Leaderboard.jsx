import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import clsx from 'clsx'
import LoadingSpinner from '../../components/LoadingSpinner'
import { aflApi } from '../aflApi'
import { Select, PlayerCell, displayName } from '../components/bits'

const STATS = [
  { key: 'goals', label: 'Goals' },
  { key: 'games', label: 'Games' },
  { key: 'bogs', label: 'Best on Ground' },
]

export default function Leaderboard() {
  const { club } = useOutletContext()
  const [stat, setStat] = useState('goals')
  const [seasonId, setSeasonId] = useState(null)
  const [gradeId, setGradeId] = useState(null)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const base = `/${club.slug}`

  useEffect(() => { setGradeId(null) }, [seasonId])

  useEffect(() => {
    setLoading(true)
    aflApi.getLeaderboard(club.id, { stat, season_id: seasonId, grade_id: gradeId, limit: 50 })
      .then(setData)
      .finally(() => setLoading(false))
  }, [club.id, stat, seasonId, gradeId])

  const gradeOptions = (club.grades || [])
    .filter(g => !seasonId || (g.season_ids || []).includes(seasonId))
    .map(g => ({ value: g.id, label: g.display_name_override || g.name }))

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold">Leaderboard</h1>
        <div className="ml-auto flex flex-wrap gap-2">
          <Select value={seasonId} onChange={setSeasonId} placeholder="All seasons"
                  options={(club.seasons || []).map(x => ({ value: x.id, label: x.name }))} />
          <Select value={gradeId} onChange={setGradeId} placeholder="All grades" options={gradeOptions} />
        </div>
      </div>

      <div className="flex gap-1">
        {STATS.map(s => (
          <button key={s.key} onClick={() => setStat(s.key)}
                  className={clsx('px-3 py-1.5 rounded text-sm font-medium',
                    stat === s.key ? 'bg-[var(--pb-accent)] text-black' : 'bg-pb-surface2 text-pb-dim hover:text-pb-text')}>
            {s.label}
          </button>
        ))}
      </div>

      {loading && !data
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
                  <th className="px-3 py-2 text-right font-mono text-[10px] uppercase text-pb-faint">BOG</th>
                  <th className="px-3 py-2 text-right font-mono text-[10px] uppercase text-[var(--pb-accent)]">{STATS.find(s => s.key === stat)?.label}</th>
                </tr>
              </thead>
              <tbody>
                {(data?.rows || []).map((r, i) => (
                  <tr key={r.player_id} className="pb-hairline-b last:border-0 hover:bg-pb-surface2/50">
                    <td className="px-3 py-2 font-mono text-pb-faintest">{i + 1}</td>
                    <td className="px-3 py-2"><PlayerCell id={r.player_id} name={displayName(r)} base={base} photoUrl={r.photo_url} /></td>
                    <td className="px-3 py-2 text-right pb-num">{r.games}</td>
                    <td className="px-3 py-2 text-right pb-num">{r.goals}</td>
                    <td className="px-3 py-2 text-right pb-num">{r.bogs}</td>
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
