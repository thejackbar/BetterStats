import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { api } from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'
import ClubInactive from './ClubInactive'
import clsx from 'clsx'

const TABS = [
  { key: 'batting',      label: 'Batting' },
  { key: 'bowling',      label: 'Bowling' },
  { key: 'partnerships', label: 'Partnerships' },
  { key: 'team',         label: 'Team' },
]

const ORDINALS = ['1st','2nd','3rd','4th','5th','6th','7th','8th','9th','10th']

function fmtDate(iso) {
  if (!iso) return null
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

function opponent(row) {
  return row.home_team && row.away_team ? `${row.home_team} v ${row.away_team}` : null
}

// ── Shared sub-components ─────────────────────────────────────────────────────

function RecordCard({ title, children, empty }) {
  return (
    <div className="card overflow-hidden">
      <div className="px-5 py-3 border-b border-navy-700 bg-navy-800/40">
        <h3 className="display-heading text-sm text-accent uppercase tracking-wider">{title}</h3>
      </div>
      {empty
        ? <p className="text-slate-600 text-sm px-5 py-4 italic">No data yet — sync required.</p>
        : <div className="overflow-x-auto">{children}</div>
      }
    </div>
  )
}

function PlayerLink({ id, name }) {
  if (!id) return <span className="text-white">{name}</span>
  return <Link to={`/players/${id}`} className="text-white hover:text-accent transition-colors">{name}</Link>
}

function RankBadge({ rank }) {
  const cls = rank === 1 ? 'text-amber-cricket font-bold' : rank === 2 ? 'text-slate-300' : rank === 3 ? 'text-amber-700' : 'text-slate-600'
  return <span className={clsx('text-xs font-mono w-5 inline-block text-right mr-2', cls)}>{rank}</span>
}

// ── Batting tab ───────────────────────────────────────────────────────────────

function BattingTab({ data }) {
  return (
    <div className="grid gap-5 md:grid-cols-2">
      <RecordCard title="Most Career Runs" empty={!data.top_career_runs?.length}>
        <table className="w-full">
          <thead><tr className="border-b border-navy-700">
            <th className="table-header">Player</th>
            <th className="table-header text-right">Runs</th>
            <th className="table-header text-right">Inn</th>
            <th className="table-header text-right">Avg</th>
            <th className="table-header text-right">HS</th>
          </tr></thead>
          <tbody>{data.top_career_runs?.map((r, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell"><RankBadge rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></td>
              <td className="table-cell stat-number text-right text-accent font-bold">{r.runs?.toLocaleString()}</td>
              <td className="table-cell stat-number text-right text-slate-400">{r.innings}</td>
              <td className="table-cell stat-number text-right text-slate-300">{r.average ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-300">{r.high_score ?? '—'}</td>
            </tr>
          ))}</tbody>
        </table>
      </RecordCard>

      <RecordCard title="Highest Individual Scores" empty={!data.top_high_scores?.length}>
        <table className="w-full">
          <thead><tr className="border-b border-navy-700">
            <th className="table-header">Player</th>
            <th className="table-header text-right">Score</th>
            <th className="table-header">Season</th>
          </tr></thead>
          <tbody>{data.top_high_scores?.map((r, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell"><RankBadge rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></td>
              <td className="table-cell text-right">
                <span className={clsx('stat-number font-bold', r.runs >= 100 ? 'text-amber-cricket' : 'text-accent')}>
                  {r.runs}{r.not_out ? '*' : ''}
                </span>
              </td>
              <td className="table-cell text-xs text-slate-500">{r.season_name}</td>
            </tr>
          ))}</tbody>
        </table>
      </RecordCard>

      <RecordCard title="Best Batting Average" empty={!data.top_batting_avg?.length}>
        <table className="w-full">
          <thead><tr className="border-b border-navy-700">
            <th className="table-header">Player</th>
            <th className="table-header text-right">Avg</th>
            <th className="table-header text-right">Runs</th>
            <th className="table-header text-right">Inn</th>
          </tr></thead>
          <tbody>{data.top_batting_avg?.map((r, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell"><RankBadge rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></td>
              <td className="table-cell stat-number text-right text-accent font-bold">{r.average}</td>
              <td className="table-cell stat-number text-right text-slate-400">{r.runs}</td>
              <td className="table-cell stat-number text-right text-slate-400">{r.innings}</td>
            </tr>
          ))}</tbody>
        </table>
      </RecordCard>

      <RecordCard title="Best Strike Rate (min. 50 balls)" empty={!data.top_strike_rate?.length}>
        <table className="w-full">
          <thead><tr className="border-b border-navy-700">
            <th className="table-header">Player</th>
            <th className="table-header text-right">SR</th>
            <th className="table-header text-right">Runs</th>
            <th className="table-header text-right">Inn</th>
          </tr></thead>
          <tbody>{data.top_strike_rate?.map((r, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell"><RankBadge rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></td>
              <td className="table-cell stat-number text-right text-accent font-bold">{r.strike_rate}</td>
              <td className="table-cell stat-number text-right text-slate-400">{r.runs}</td>
              <td className="table-cell stat-number text-right text-slate-400">{r.innings}</td>
            </tr>
          ))}</tbody>
        </table>
      </RecordCard>

      <RecordCard title="Most Fifties" empty={!data.most_fifties?.length}>
        <table className="w-full">
          <thead><tr className="border-b border-navy-700">
            <th className="table-header">Player</th>
            <th className="table-header text-right">50s</th>
            <th className="table-header text-right">100s</th>
            <th className="table-header text-right">Runs</th>
          </tr></thead>
          <tbody>{data.most_fifties?.map((r, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell"><RankBadge rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></td>
              <td className="table-cell stat-number text-right text-accent font-bold">{r.fifties}</td>
              <td className="table-cell stat-number text-right text-slate-400">{r.hundreds}</td>
              <td className="table-cell stat-number text-right text-slate-400">{r.runs}</td>
            </tr>
          ))}</tbody>
        </table>
      </RecordCard>

      <RecordCard title="Most Hundreds" empty={!data.most_hundreds?.length}>
        <table className="w-full">
          <thead><tr className="border-b border-navy-700">
            <th className="table-header">Player</th>
            <th className="table-header text-right">100s</th>
            <th className="table-header text-right">Runs</th>
          </tr></thead>
          <tbody>{data.most_hundreds?.map((r, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell"><RankBadge rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></td>
              <td className="table-cell stat-number text-right text-amber-cricket font-bold">{r.hundreds}</td>
              <td className="table-cell stat-number text-right text-slate-400">{r.runs}</td>
            </tr>
          ))}</tbody>
        </table>
      </RecordCard>

      <RecordCard title="Most Runs in a Season" empty={!data.most_runs_season?.length}>
        <table className="w-full">
          <thead><tr className="border-b border-navy-700">
            <th className="table-header">Player</th>
            <th className="table-header text-right">Runs</th>
            <th className="table-header">Season</th>
          </tr></thead>
          <tbody>{data.most_runs_season?.map((r, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell"><RankBadge rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></td>
              <td className="table-cell stat-number text-right text-accent font-bold">{r.runs}</td>
              <td className="table-cell text-xs text-slate-500">{r.season_name}</td>
            </tr>
          ))}</tbody>
        </table>
      </RecordCard>

      <RecordCard title="Most Ducks" empty={!data.most_ducks?.length}>
        <table className="w-full">
          <thead><tr className="border-b border-navy-700">
            <th className="table-header">Player</th>
            <th className="table-header text-right">Ducks</th>
            <th className="table-header text-right">Inn</th>
          </tr></thead>
          <tbody>{data.most_ducks?.map((r, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell"><RankBadge rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></td>
              <td className="table-cell stat-number text-right text-red-400 font-bold">{r.ducks}</td>
              <td className="table-cell stat-number text-right text-slate-400">{r.innings}</td>
            </tr>
          ))}</tbody>
        </table>
      </RecordCard>
    </div>
  )
}

// ── Bowling tab ───────────────────────────────────────────────────────────────

function BowlingTab({ data }) {
  return (
    <div className="grid gap-5 md:grid-cols-2">
      <RecordCard title="Most Career Wickets" empty={!data.top_career_wickets?.length}>
        <table className="w-full">
          <thead><tr className="border-b border-navy-700">
            <th className="table-header">Player</th>
            <th className="table-header text-right">Wkts</th>
            <th className="table-header text-right">Avg</th>
            <th className="table-header text-right">Econ</th>
            <th className="table-header text-right">5W</th>
          </tr></thead>
          <tbody>{data.top_career_wickets?.map((r, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell"><RankBadge rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></td>
              <td className="table-cell stat-number text-right text-accent font-bold">{r.wickets}</td>
              <td className="table-cell stat-number text-right text-slate-300">{r.average ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-400">{r.economy ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-400">{r.five_fors}</td>
            </tr>
          ))}</tbody>
        </table>
      </RecordCard>

      <RecordCard title="Best Bowling in an Innings" empty={!data.best_innings_figures?.length}>
        <table className="w-full">
          <thead><tr className="border-b border-navy-700">
            <th className="table-header">Player</th>
            <th className="table-header text-right">Figures</th>
            <th className="table-header">Season</th>
          </tr></thead>
          <tbody>{data.best_innings_figures?.map((r, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell"><RankBadge rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></td>
              <td className="table-cell text-right">
                <span className={clsx('stat-number font-bold', r.wickets >= 5 ? 'text-amber-cricket' : r.wickets >= 3 ? 'text-accent' : 'text-white')}>
                  {r.wickets}/{r.runs}
                </span>
              </td>
              <td className="table-cell text-xs text-slate-500">{r.season_name}</td>
            </tr>
          ))}</tbody>
        </table>
      </RecordCard>

      <RecordCard title="Best Bowling Average (min. 5 wkts)" empty={!data.top_bowling_avg?.length}>
        <table className="w-full">
          <thead><tr className="border-b border-navy-700">
            <th className="table-header">Player</th>
            <th className="table-header text-right">Avg</th>
            <th className="table-header text-right">Wkts</th>
          </tr></thead>
          <tbody>{data.top_bowling_avg?.map((r, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell"><RankBadge rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></td>
              <td className="table-cell stat-number text-right text-accent font-bold">{r.average}</td>
              <td className="table-cell stat-number text-right text-slate-400">{r.wickets}</td>
            </tr>
          ))}</tbody>
        </table>
      </RecordCard>

      <RecordCard title="Best Economy Rate (min. 60 balls)" empty={!data.top_economy?.length}>
        <table className="w-full">
          <thead><tr className="border-b border-navy-700">
            <th className="table-header">Player</th>
            <th className="table-header text-right">Econ</th>
            <th className="table-header text-right">Wkts</th>
            <th className="table-header text-right">Overs</th>
          </tr></thead>
          <tbody>{data.top_economy?.map((r, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell"><RankBadge rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></td>
              <td className="table-cell stat-number text-right text-accent font-bold">{r.economy}</td>
              <td className="table-cell stat-number text-right text-slate-400">{r.wickets}</td>
              <td className="table-cell stat-number text-right text-slate-400">{r.overs}</td>
            </tr>
          ))}</tbody>
        </table>
      </RecordCard>

      <RecordCard title="Most Five-Wicket Hauls" empty={!data.most_five_fors?.length}>
        <table className="w-full">
          <thead><tr className="border-b border-navy-700">
            <th className="table-header">Player</th>
            <th className="table-header text-right">5Ws</th>
            <th className="table-header text-right">Wkts</th>
          </tr></thead>
          <tbody>{data.most_five_fors?.map((r, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell"><RankBadge rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></td>
              <td className="table-cell stat-number text-right text-amber-cricket font-bold">{r.five_fors}</td>
              <td className="table-cell stat-number text-right text-slate-400">{r.wickets}</td>
            </tr>
          ))}</tbody>
        </table>
      </RecordCard>

      <RecordCard title="Most Wickets in a Season" empty={!data.most_wickets_season?.length}>
        <table className="w-full">
          <thead><tr className="border-b border-navy-700">
            <th className="table-header">Player</th>
            <th className="table-header text-right">Wkts</th>
            <th className="table-header">Season</th>
          </tr></thead>
          <tbody>{data.most_wickets_season?.map((r, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell"><RankBadge rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></td>
              <td className="table-cell stat-number text-right text-accent font-bold">{r.wickets}</td>
              <td className="table-cell text-xs text-slate-500">{r.season_name}</td>
            </tr>
          ))}</tbody>
        </table>
      </RecordCard>
    </div>
  )
}

// ── Partnerships tab ──────────────────────────────────────────────────────────

function PartnershipRow({ r, rank }) {
  const b1 = r.batter1_name || 'Unknown'
  const b2 = r.batter2_name || 'Unknown'
  return (
    <tr className="table-row">
      <td className="table-cell">
        <RankBadge rank={rank} />
        <span className="text-white">{b1}</span>
        <span className="text-slate-600 mx-1">&amp;</span>
        <span className="text-white">{b2}</span>
        {r.is_not_out && <span className="ml-1.5 text-xs text-slate-500">*</span>}
        {r.is_manual && <span className="ml-1.5 text-xs text-slate-600 italic">manual</span>}
      </td>
      <td className="table-cell stat-number text-right text-accent font-bold">
        {r.runs}{r.is_not_out ? '*' : ''}
      </td>
      <td className="table-cell text-xs text-slate-400 text-right">{r.wicket_number ? ORDINALS[r.wicket_number - 1] : '—'}</td>
      <td className="table-cell text-xs text-slate-500 hidden sm:table-cell">{r.grade_name || '—'}</td>
      <td className="table-cell text-xs text-slate-600 text-right hidden md:table-cell">
        {r.season_year || (r.played_at ? new Date(r.played_at + 'T00:00:00').getFullYear() : '—')}
      </td>
    </tr>
  )
}

function PartnershipsTab({ data }) {
  const byWicket = data.by_wicket || {}
  const manual = data.manual || []

  // Merge manual records into by_wicket
  const byWicketWithManual = { ...byWicket }
  for (const r of manual) {
    const wk = r.wicket_number
    if (!byWicketWithManual[wk]) byWicketWithManual[wk] = []
    byWicketWithManual[wk] = [...byWicketWithManual[wk], r]
      .sort((a, b) => b.runs - a.runs)
      .slice(0, 5)
  }

  const wktNumbers = Array.from({ length: 10 }, (_, i) => i + 1)
    .filter(n => byWicketWithManual[n]?.length)
  const getWkt = n => byWicketWithManual[n] || []

  // Merge manual records into top_overall
  const allOverall = [...(data.top_overall || []), ...manual]
    .sort((a, b) => b.runs - a.runs)
    .slice(0, 25)

  return (
    <div className="space-y-5">
      <RecordCard title="Top Partnerships" empty={!allOverall.length}>
        <table className="w-full">
          <thead><tr className="border-b border-navy-700">
            <th className="table-header">Batters</th>
            <th className="table-header text-right">Runs</th>
            <th className="table-header text-right">Wkt</th>
            <th className="table-header hidden sm:table-cell">Grade</th>
            <th className="table-header text-right hidden md:table-cell">Year</th>
          </tr></thead>
          <tbody>{allOverall.map((r, i) => <PartnershipRow key={i} r={r} rank={i+1} />)}</tbody>
        </table>
      </RecordCard>

      {wktNumbers.length > 0 && (
        <div>
          <h3 className="display-heading text-base text-white mb-3">Best Partnership by Wicket</h3>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            {wktNumbers.map(wk => (
              <div key={wk} className="card overflow-hidden">
                <div className="px-4 py-2 border-b border-navy-700 bg-navy-800/40">
                  <span className="text-xs text-accent font-medium uppercase tracking-wider">{ORDINALS[wk-1]} Wicket</span>
                </div>
                <div className="divide-y divide-navy-700/50">
                  {getWkt(wk).map((r, i) => (
                    <div key={i} className="px-4 py-2">
                      <div className="text-xs text-white font-medium leading-snug">
                        {r.batter1_name} <span className="text-slate-600">&</span> {r.batter2_name}
                        {r.is_manual && <span className="text-slate-700 ml-1 italic">manual</span>}
                      </div>
                      <div className="flex items-baseline gap-2 mt-0.5">
                        <span className="stat-number text-accent font-bold">{r.runs}{r.is_not_out ? '*' : ''}</span>
                        <span className="text-xs text-slate-600">{r.grade_name || ''}</span>
                        <span className="text-xs text-slate-700">
                          {r.season_year || (r.played_at ? new Date(r.played_at + 'T00:00:00').getFullYear() : '')}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <RecordCard title="Top Partnership Pairs (by total runs)" empty={!data.top_pairs?.length}>
        <table className="w-full">
          <thead><tr className="border-b border-navy-700">
            <th className="table-header">Batters</th>
            <th className="table-header text-right">Count</th>
            <th className="table-header text-right">Total</th>
            <th className="table-header text-right">Best</th>
          </tr></thead>
          <tbody>{data.top_pairs?.map((r, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell">
                <RankBadge rank={i+1} />
                <span className="text-white">{r.batter1_name}</span>
                <span className="text-slate-600 mx-1">&amp;</span>
                <span className="text-white">{r.batter2_name}</span>
              </td>
              <td className="table-cell stat-number text-right text-slate-400">{r.count}</td>
              <td className="table-cell stat-number text-right text-accent font-bold">{r.total_runs}</td>
              <td className="table-cell stat-number text-right text-slate-300">{r.best}</td>
            </tr>
          ))}</tbody>
        </table>
      </RecordCard>
    </div>
  )
}

// ── Team tab ──────────────────────────────────────────────────────────────────

function TeamTab({ data }) {
  return (
    <div className="grid gap-5 md:grid-cols-2">
      <RecordCard title="Most Matches Played" empty={!data.most_matches?.length}>
        <table className="w-full">
          <thead><tr className="border-b border-navy-700">
            <th className="table-header">Player</th>
            <th className="table-header text-right">Matches</th>
          </tr></thead>
          <tbody>{data.most_matches?.map((r, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell"><RankBadge rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></td>
              <td className="table-cell stat-number text-right text-accent font-bold">{r.matches}</td>
            </tr>
          ))}</tbody>
        </table>
      </RecordCard>

      <RecordCard title="Top Fielders" empty={!data.top_fielders?.length}>
        <table className="w-full">
          <thead><tr className="border-b border-navy-700">
            <th className="table-header">Player</th>
            <th className="table-header text-right">Catches</th>
            <th className="table-header text-right">WK Ct</th>
            <th className="table-header text-right">St</th>
            <th className="table-header text-right">RO</th>
          </tr></thead>
          <tbody>{data.top_fielders?.map((r, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell"><RankBadge rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></td>
              <td className="table-cell stat-number text-right text-accent font-bold">{r.catches}</td>
              <td className="table-cell stat-number text-right text-slate-400">{r.catches_wk}</td>
              <td className="table-cell stat-number text-right text-slate-400">{r.stumpings}</td>
              <td className="table-cell stat-number text-right text-slate-400">{r.run_outs}</td>
            </tr>
          ))}</tbody>
        </table>
      </RecordCard>

      <RecordCard title="Top All-Rounders" empty={!data.top_allrounders?.length}>
        <table className="w-full">
          <thead><tr className="border-b border-navy-700">
            <th className="table-header">Player</th>
            <th className="table-header text-right">Runs</th>
            <th className="table-header text-right">Wkts</th>
            <th className="table-header text-right">Matches</th>
          </tr></thead>
          <tbody>{data.top_allrounders?.map((r, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell"><RankBadge rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></td>
              <td className="table-cell stat-number text-right text-accent">{r.runs?.toLocaleString()}</td>
              <td className="table-cell stat-number text-right text-accent">{r.wickets}</td>
              <td className="table-cell stat-number text-right text-slate-400">{r.matches}</td>
            </tr>
          ))}</tbody>
        </table>
      </RecordCard>
    </div>
  )
}

// ── Filters ───────────────────────────────────────────────────────────────────

function FilterBar({ seasons, seasonId, onSeasonChange, grades, gradeId, onGradeChange }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <select
        value={seasonId || ''}
        onChange={e => onSeasonChange(e.target.value || null)}
        className="bg-navy-800 border border-navy-600 text-slate-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-accent"
      >
        <option value="">All time</option>
        {seasons.map(s => (
          <option key={s.id} value={s.id}>{s.name}</option>
        ))}
      </select>
      {grades.length > 0 && (
        <select
          value={gradeId || ''}
          onChange={e => onGradeChange(e.target.value || null)}
          className="bg-navy-800 border border-navy-600 text-slate-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-accent"
        >
          <option value="">All grades</option>
          {grades.map(g => (
            <option key={g.id} value={g.id}>{g.name}</option>
          ))}
        </select>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Records() {
  const { clubSlug } = useParams()
  const { club, orgId, inactive } = useClub(clubSlug)
  useClubTheme(club)

  if (inactive) return <ClubInactive />
  const [tab, setTab] = useState('batting')
  const [seasons, setSeasons] = useState([])
  const [seasonId, setSeasonId] = useState(null)
  const [grades, setGrades] = useState([])
  const [gradeId, setGradeId] = useState(null)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getOrgSeasons(orgId).then(setSeasons).catch(() => {})
  }, [orgId])

  useEffect(() => {
    setGradeId(null)
    if (seasonId) {
      api.getSeasonGrades(orgId, seasonId).then(setGrades).catch(() => setGrades([]))
    } else {
      api.getRecordsGrades(orgId).then(setGrades).catch(() => setGrades([]))
    }
  }, [orgId, seasonId])

  useEffect(() => {
    setLoading(true)
    setError(null)
    api.getRecords(orgId, { seasonId, gradeId })
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [orgId, seasonId, gradeId])

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="display-heading text-3xl text-white">Club Records</h1>
          <p className="text-slate-500 text-sm mt-1">All-time records &amp; statistical leaders</p>
        </div>
        <FilterBar
          seasons={seasons} seasonId={seasonId} onSeasonChange={setSeasonId}
          grades={grades} gradeId={gradeId} onGradeChange={setGradeId}
        />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-navy-700">
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={clsx(
              'px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px',
              tab === t.key
                ? 'text-accent border-accent'
                : 'text-slate-400 border-transparent hover:text-white',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading && <LoadingSpinner message="Loading records…" />}
      {error && <p className="text-red-400 text-sm">{error}</p>}

      {data && !loading && (
        <>
          {tab === 'batting'      && <BattingTab      data={data.batting} />}
          {tab === 'bowling'      && <BowlingTab      data={data.bowling} />}
          {tab === 'partnerships' && <PartnershipsTab data={data.partnerships} />}
          {tab === 'team'         && <TeamTab         data={data.team} />}
        </>
      )}
    </div>
  )
}
