import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import LoadingSpinner from '../../components/LoadingSpinner'
import StatCard from '../../components/StatCard'
import { aflApi } from '../aflApi'
import { Select, GameRow } from '../components/bits'

export default function Games() {
  const { club } = useOutletContext()
  const [seasonId, setSeasonId] = useState(null)
  const [gradeId, setGradeId] = useState(null)
  const [finalsOnly, setFinalsOnly] = useState(false)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const base = `/${club.slug}`

  const gradeOptions = useMemo(() => {
    const grades = (club.grades || []).filter(g => !seasonId || (g.season_ids || []).includes(seasonId))
    return grades.map(g => ({ value: g.id, label: g.display_name_override || g.name }))
  }, [club.grades, seasonId])

  useEffect(() => { setGradeId(null) }, [seasonId])

  useEffect(() => {
    setLoading(true)
    aflApi.getResults(club.id, {
      season_id: seasonId, grade_id: gradeId, finals_only: finalsOnly, limit: 100,
    }).then(setData).finally(() => setLoading(false))
  }, [club.id, seasonId, gradeId, finalsOnly])

  const s = data?.summary || {}

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

      <div className="grid grid-cols-4 gap-3">
        <StatCard label="Played" value={s.played} />
        <StatCard label="Wins" value={s.wins} accent />
        <StatCard label="Losses" value={s.losses} />
        <StatCard label="Draws" value={s.draws} />
      </div>

      {loading
        ? <div className="pt-8 flex justify-center"><LoadingSpinner /></div>
        : (
          <div className="space-y-2">
            {(data?.games || []).map(g => <GameRow key={g.id} game={g} base={base} />)}
            {(data?.games || []).length === 0 && <p className="text-sm text-pb-faint pt-4">No games match these filters.</p>}
          </div>
        )}
    </div>
  )
}
