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
 */
function TeamRecords({ rows }) {
  const teams = rows || []
  if (teams.length < 2) return null

  const winPct = (r) => {
    const decided = r.wins + r.losses + r.draws
    return decided ? Math.round((r.wins / decided) * 100) : null
  }

  return (
    <div className="pb-card overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="pb-hairline-b">
          <tr>
            <th className="px-3 py-2 text-left font-mono text-[10px] uppercase tracking-wide text-pb-faint">Team</th>
            {['Played', 'Won', 'Lost', 'Drawn', 'Win %'].map(h => (
              <th key={h} className="px-3 py-2 text-right font-mono text-[10px] uppercase tracking-wide text-pb-faint">{h}</th>
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
                <td className="px-3 py-2.5 text-right pb-num text-pb-dim">{pct == null ? '—' : `${pct}%`}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

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

      <TeamRecords rows={data?.by_team} />

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
