import { Fragment, useEffect, useState } from 'react'
import { Link, useOutletContext, useParams } from 'react-router-dom'
import StatCard from '../../components/StatCard'
import LoadingSpinner from '../../components/LoadingSpinner'
import { aflApi } from '../aflApi'
import { SectionTitle, ResultPill } from '../components/bits'

export default function PlayerProfile() {
  const { club } = useOutletContext()
  const { playerId } = useParams()
  const [data, setData] = useState(null)
  const [notFound, setNotFound] = useState(false)
  const base = `/${club.slug}`

  useEffect(() => {
    setData(null)
    aflApi.getPlayer(playerId).then(setData).catch(() => setNotFound(true))
  }, [playerId])

  if (notFound) return <p className="pt-16 text-center text-pb-dim">Player not found.</p>
  if (!data) return <div className="pt-16 flex justify-center"><LoadingSpinner /></div>
  const c = data.career || {}

  // Whole-season rows only for the season table (grade rows shown nested).
  const seasonRows = (data.seasons || []).filter(s => !s.grade_id)
  const gradeRows = (data.seasons || []).filter(s => s.grade_id)

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        {data.photo_url
          ? <img src={data.photo_url} alt="" className="h-16 w-16 rounded-full object-cover" />
          : <span className="h-16 w-16 rounded-full bg-pb-surface2 flex items-center justify-center text-xl text-pb-faint">
              {(data.name || '?').split(' ').map(w => w[0]).slice(0, 2).join('')}
            </span>}
        <div>
          <h1 className="text-2xl font-bold">{data.name}</h1>
          <p className="text-sm text-pb-faint">
            {c.first_year ? (c.first_year === c.last_year ? c.first_year : `${c.first_year} – ${c.last_year}`) : ''}
            {c.seasons ? ` · ${c.seasons} season${c.seasons > 1 ? 's' : ''}` : ''}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatCard label="Games" value={c.games} accent large />
        <StatCard label="Goals" value={c.goals} large />
        <StatCard label="Behinds" value={c.behinds} large />
        <StatCard label="Best on Ground" value={c.bogs} large />
        <StatCard
          label="Best haul"
          value={data.best_haul ? data.best_haul.goals : '—'}
          sub={data.best_haul ? `${data.best_haul.round_name || ''} ${data.best_haul.season_name || ''}`.trim() : null}
          large
        />
      </div>

      <div>
        <SectionTitle>Season by season</SectionTitle>
        <div className="pb-card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="pb-hairline-b">
              <tr>
                {['Season', 'GP', 'Goals', 'Behinds', 'BOG'].map((h, i) => (
                  <th key={h} className={`px-3 py-2 font-mono text-[10px] uppercase tracking-wide text-pb-faint ${i ? 'text-right' : 'text-left'}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {seasonRows.map(s => (
                <Fragment key={s.season_id}>
                  <tr className="pb-hairline-b hover:bg-pb-surface2/50">
                    <td className="px-3 py-2 font-medium">{s.season_name}</td>
                    <td className="px-3 py-2 text-right pb-num">{s.games}</td>
                    <td className="px-3 py-2 text-right pb-num">{s.goals}</td>
                    <td className="px-3 py-2 text-right pb-num">{s.behinds}</td>
                    <td className="px-3 py-2 text-right pb-num">{s.bogs}</td>
                  </tr>
                  {gradeRows.filter(g => g.season_id === s.season_id).map(g => (
                    <tr key={`${s.season_id}-${g.grade_id}`} className="pb-hairline-b text-pb-dim">
                      <td className="px-3 py-1.5 pl-8 text-xs">{g.grade_name}</td>
                      <td className="px-3 py-1.5 text-right pb-num text-xs">{g.games}</td>
                      <td className="px-3 py-1.5 text-right pb-num text-xs">{g.goals}</td>
                      <td className="px-3 py-1.5 text-right pb-num text-xs">{g.behinds}</td>
                      <td className="px-3 py-1.5 text-right pb-num text-xs">{g.bogs}</td>
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <SectionTitle>Game log</SectionTitle>
        <div className="pb-card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="pb-hairline-b">
              <tr>
                {['Date', 'Round', 'Match', 'Goals', 'Behinds', 'BOG', ''].map((h, i) => (
                  <th key={h + i} className={`px-3 py-2 font-mono text-[10px] uppercase tracking-wide text-pb-faint ${i >= 3 ? 'text-right' : 'text-left'}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(data.game_log || []).map(g => (
                <tr key={g.game_id} className="pb-hairline-b last:border-0 hover:bg-pb-surface2/50">
                  <td className="px-3 py-2 pb-num text-pb-faint whitespace-nowrap">{g.played_at}</td>
                  <td className="px-3 py-2 text-pb-faint whitespace-nowrap">{g.round_name || (g.is_final ? 'Final' : '')}</td>
                  <td className="px-3 py-2">
                    <Link to={`${base}/games/${g.game_id}`} className="hover:text-[var(--pb-accent)]">
                      {g.home_team} v {g.away_team}
                    </Link>
                    <span className="block text-[11px] text-pb-faintest">{g.grade_name}</span>
                  </td>
                  <td className="px-3 py-2 text-right pb-num font-semibold">{g.goals}</td>
                  <td className="px-3 py-2 text-right pb-num">{g.behinds}</td>
                  <td className="px-3 py-2 text-right">
                    {g.bog_ranking != null && (
                      <span className="font-mono text-[10px] font-bold px-1.5 py-0.5 rounded bg-[color-mix(in_srgb,var(--pb-amber)_20%,transparent)] text-[var(--pb-amber)]">
                        BOG{g.bog_ranking === 1 ? ' #1' : ''}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right"><ResultPill result={g.result} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
