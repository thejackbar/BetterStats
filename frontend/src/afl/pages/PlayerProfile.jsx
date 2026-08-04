import { Fragment, useEffect, useState } from 'react'
import { Link, useOutletContext, useParams } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Line,
} from 'recharts'
import StatCard from '../../components/StatCard'
import LoadingSpinner from '../../components/LoadingSpinner'
import { aflApi } from '../aflApi'
import { SectionTitle, ResultPill } from '../components/bits'

// ── Charts — mirrors BetterStats (Core)'s player-profile chart language
// (pages/PlayerProfile.jsx: recharts, CSS-var colours, a single shared
// tooltip style) but kept to a single Y axis per chart throughout, rather
// than cricket's runs/wickets dual-axis SeasonChart — two measures of
// different scale get their own chart, not a second axis on one.
const CHART_TOOLTIP = {
  contentStyle: { background: 'var(--pb-surface)', border: '1px solid var(--pb-hairline2, var(--pb-hairline))', borderRadius: 8, fontSize: 12 },
  labelStyle: { color: 'var(--pb-dim)' },
  itemStyle: { color: 'var(--pb-text)' },
}

function SeasonBarChart({ rows, dataKey, name, color }) {
  const chartData = (rows || []).filter(r => r.season_id).slice().reverse()
  if (!chartData.length) return null
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline)" vertical={false} />
        <XAxis dataKey="season_name" tick={{ fill: 'var(--pb-faint)', fontSize: 10 }} interval="preserveStartEnd" />
        <YAxis tick={{ fill: 'var(--pb-faint)', fontSize: 11 }} allowDecimals={false} width={32} />
        <Tooltip {...CHART_TOOLTIP} />
        <Bar dataKey={dataKey} name={name} fill={color} radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

function CumulativeGoalsChart({ rows }) {
  const seasons = (rows || []).filter(r => r.season_id).slice().reverse()
  if (!seasons.length) return null
  let cumulative = 0
  const chartData = seasons.map(s => {
    cumulative += (s.goals || 0)
    return { season: s.season_name, total: cumulative, season_goals: s.goals || 0 }
  })
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline)" vertical={false} />
        <XAxis dataKey="season" tick={{ fill: 'var(--pb-faint)', fontSize: 10 }} interval="preserveStartEnd" />
        <YAxis tick={{ fill: 'var(--pb-faint)', fontSize: 11 }} allowDecimals={false} width={40} />
        <Tooltip {...CHART_TOOLTIP} formatter={(v, key) => [Number(v).toLocaleString(), key === 'total' ? 'Career total' : 'Season goals']} />
        <Bar dataKey="season_goals" name="season_goals" fill="var(--pb-chart-1)" fillOpacity={0.25} radius={[2, 2, 0, 0]} />
        <Line type="monotone" dataKey="total" name="total" stroke="var(--pb-chart-1)" strokeWidth={2} dot={false} />
      </BarChart>
    </ResponsiveContainer>
  )
}

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

  // Whole-season rows only for the season table + charts (per-grade rows nested under them).
  const seasonRows = (data.seasons || []).filter(s => !s.grade_id)
  const gradeRows = (data.seasons || []).filter(s => s.grade_id)
  const hasChartData = seasonRows.filter(s => s.season_id).length >= 2

  return (
    <div className="space-y-6">
      <div className="flex items-stretch gap-3.5">
        <span className="w-1 rounded-full shrink-0" style={{ background: 'var(--pb-gradient)' }} />
        <div className="flex items-center gap-4">
          {data.photo_url
            ? <img src={data.photo_url} alt="" className="h-20 w-20 rounded-full object-cover" />
            : <span className="h-20 w-20 rounded-full bg-pb-surface2 flex items-center justify-center text-2xl text-pb-faint">
                {(data.name || '?').split(' ').map(w => w[0]).slice(0, 2).join('')}
              </span>}
          <div>
            <h1 className="font-display text-3xl sm:text-4xl font-bold tracking-tight text-pb-text">{data.name}</h1>
            <p className="text-sm text-pb-dim font-mono mt-1">
              {c.first_year ? (c.first_year === c.last_year ? c.first_year : `${c.first_year} – ${c.last_year}`) : ''}
              {c.seasons ? ` · ${c.seasons} season${c.seasons > 1 ? 's' : ''}` : ''}
            </p>
          </div>
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

      {hasChartData && (
        <div>
          <SectionTitle>Career trajectory</SectionTitle>
          <div className="grid md:grid-cols-2 gap-4">
            <div className="pb-card p-4">
              <p className="font-mono text-[10px] tracking-wide uppercase text-pb-faint mb-2">Goals by season</p>
              <SeasonBarChart rows={seasonRows} dataKey="goals" name="Goals" color="var(--pb-chart-1)" />
            </div>
            <div className="pb-card p-4">
              <p className="font-mono text-[10px] tracking-wide uppercase text-pb-faint mb-2">Games by season</p>
              <SeasonBarChart rows={seasonRows} dataKey="games" name="Games" color="var(--pb-chart-2)" />
            </div>
          </div>
          <div className="pb-card p-4 mt-4">
            <p className="font-mono text-[10px] tracking-wide uppercase text-pb-faint mb-2">Cumulative career goals</p>
            <CumulativeGoalsChart rows={seasonRows} />
          </div>
        </div>
      )}

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
              {seasonRows.length === 0 && (
                <tr><td colSpan={5} className="px-3 py-4 text-center text-pb-faint text-sm">No seasons recorded yet.</td></tr>
              )}
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
              {(data.game_log || []).length === 0 && (
                <tr><td colSpan={7} className="px-3 py-4 text-center text-pb-faint text-sm">
                  {(c.games || 0) > 0
                    ? "No individual game records — this player's history comes from an imported season-totals spreadsheet, which doesn't include a game-by-game breakdown."
                    : 'No games recorded yet.'}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
