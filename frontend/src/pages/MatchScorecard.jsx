import { useParams, useSearchParams, Link, useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'
import clsx from 'clsx'

function MatchSummary({ game }) {
  const isWin = game.result === 'WIN'
  const isLoss = game.result === 'LOSS'
  const isDraw = ['DRAW', 'TIE', 'NO_RESULT'].includes(game.result)

  const resultColor = isWin ? 'text-accent' : isLoss ? 'text-red-400' : 'text-slate-400'
  const bannerBorder = isWin ? 'border-accent/20' : isLoss ? 'border-red-500/20' : 'border-navy-700'

  // Build score summary from innings_totals
  const totals = game.innings_totals || {}
  const inningNums = Object.keys(totals).map(Number).sort()
  const scoreLine = inningNums.map(n => {
    const t = totals[n]
    return `${t.runs}/${t.wickets}`
  }).join('  ·  ')

  return (
    <div className={`card p-5 mb-6 border ${bannerBorder}`}>
      {/* Grade / Season breadcrumb */}
      <p className="section-label mb-3">
        {game.season?.name}{game.grade?.name ? ` · ${game.grade.name}` : ''}
        {game.played_at && (
          <span className="ml-2">
            {new Date(game.played_at).toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
          </span>
        )}
      </p>

      {/* Teams + result */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="display-heading text-3xl md:text-4xl text-white leading-tight">
            {game.home_team}
            <span className="text-slate-600 font-sans font-normal text-xl mx-3">vs</span>
            {game.away_team}
          </h1>
          {scoreLine && (
            <p className="stat-number text-slate-300 text-lg mt-2 tracking-wider">{scoreLine}</p>
          )}
        </div>
        <div className="text-right shrink-0">
          <div className={clsx('display-heading text-3xl font-bold', resultColor)}>
            {game.result || 'N/R'}
          </div>
          {game.winning_team && (
            <p className="text-sm text-slate-400 mt-1">{game.winning_team} won</p>
          )}
        </div>
      </div>
    </div>
  )
}

function BattingTable({ batting = [] }) {
  if (!batting.length) return <p className="text-slate-500 text-sm py-4 px-5">No batting data.</p>

  const total = batting.reduce((s, r) => s + (r.runs ?? 0), 0)
  const wickets = batting.filter(r => !r.not_out && r.dismissal_type).length

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-navy-700 bg-navy-800/30">
            <th className="table-header pl-5">Batter</th>
            <th className="table-header text-slate-500 font-normal normal-case tracking-normal">Dismissal</th>
            <th className="table-header text-right pr-2">R</th>
            <th className="table-header text-right pr-2">B</th>
            <th className="table-header text-right pr-2">4s</th>
            <th className="table-header text-right pr-2">6s</th>
            <th className="table-header text-right pr-5">SR</th>
          </tr>
        </thead>
        <tbody>
          {batting.map((row, i) => (
            <tr key={i} className="border-b border-navy-800/50 hover:bg-navy-800/20 transition-colors">
              <td className="py-2.5 px-5">
                {row.player_id
                  ? <Link to={`/players/${row.player_id}`} className="text-white hover:text-accent transition-colors font-medium">{row.player_name || '—'}</Link>
                  : <span className="text-white font-medium">{row.player_name || '—'}</span>
                }
              </td>
              <td className="py-2.5 px-3 text-slate-500 text-xs capitalize max-w-[140px] truncate">
                {row.not_out ? 'not out' : row.dismissal_type || '—'}
              </td>
              <td className="py-2.5 pr-2 text-right">
                <span className={clsx(
                  'stat-number font-bold',
                  row.runs >= 100 ? 'text-amber-cricket' : row.runs >= 50 ? 'text-accent' : 'text-white'
                )}>
                  {row.runs ?? '—'}
                </span>
                {row.not_out && <span className="text-accent text-xs">*</span>}
              </td>
              <td className="py-2.5 pr-2 stat-number text-right text-slate-400">{row.balls ?? '—'}</td>
              <td className="py-2.5 pr-2 stat-number text-right text-slate-400">{row.fours ?? '—'}</td>
              <td className="py-2.5 pr-2 stat-number text-right text-slate-400">{row.sixes ?? '—'}</td>
              <td className="py-2.5 pr-5 stat-number text-right text-slate-500 text-xs">
                {row.strike_rate != null ? Number(row.strike_rate).toFixed(1) : '—'}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-navy-600 bg-navy-800/20">
            <td colSpan={2} className="py-2 px-5 text-slate-400 font-semibold text-sm">Total</td>
            <td className="py-2 pr-2 stat-number text-right font-bold text-white">
              {total}/{wickets}
            </td>
            <td colSpan={4} />
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

function BowlingTable({ bowling = [] }) {
  if (!bowling.length) return <p className="text-slate-500 text-sm py-4 px-5">No bowling data.</p>

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-navy-700 bg-navy-800/30">
            <th className="table-header pl-5">Bowler</th>
            <th className="table-header text-right pr-2">O</th>
            <th className="table-header text-right pr-2">M</th>
            <th className="table-header text-right pr-2">R</th>
            <th className="table-header text-right pr-2">W</th>
            <th className="table-header text-right pr-2">Econ</th>
            <th className="table-header text-right pr-2">Wd</th>
            <th className="table-header text-right pr-5">NB</th>
          </tr>
        </thead>
        <tbody>
          {bowling.map((row, i) => (
            <tr key={i} className="border-b border-navy-800/50 hover:bg-navy-800/20 transition-colors">
              <td className="py-2.5 px-5">
                {row.player_id
                  ? <Link to={`/players/${row.player_id}`} className="text-white hover:text-accent transition-colors font-medium">{row.player_name || '—'}</Link>
                  : <span className="text-white font-medium">{row.player_name || '—'}</span>
                }
              </td>
              <td className="py-2.5 pr-2 stat-number text-right text-slate-300">{row.overs ?? '—'}</td>
              <td className="py-2.5 pr-2 stat-number text-right text-slate-500">{row.maidens ?? '—'}</td>
              <td className="py-2.5 pr-2 stat-number text-right text-slate-300">{row.runs ?? '—'}</td>
              <td className="py-2.5 pr-2 text-right">
                <span className={clsx(
                  'stat-number font-bold',
                  row.wickets >= 5 ? 'text-amber-cricket' : row.wickets >= 3 ? 'text-accent' : 'text-white'
                )}>
                  {row.wickets ?? '—'}
                </span>
              </td>
              <td className="py-2.5 pr-2 stat-number text-right text-slate-300">
                {row.economy != null ? Number(row.economy).toFixed(2) : '—'}
              </td>
              <td className="py-2.5 pr-2 stat-number text-right text-slate-500">{row.wides ?? '—'}</td>
              <td className="py-2.5 pr-5 stat-number text-right text-slate-500">{row.no_balls ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function InningsBlock({ num, title, batting, bowling }) {
  const total = batting.reduce((s, r) => s + (r.runs ?? 0), 0)
  const wickets = batting.filter(r => !r.not_out && r.dismissal_type).length

  return (
    <div className="card overflow-hidden">
      <div className="px-5 py-3 border-b border-navy-700 bg-navy-800/20 flex items-center justify-between">
        <div>
          <p className="section-label text-xs">INNINGS {num}</p>
          <h3 className="display-heading text-lg text-white">{title}</h3>
        </div>
        {batting.length > 0 && (
          <div className="text-right">
            <span className="stat-number text-2xl font-bold text-white">{total}/{wickets}</span>
          </div>
        )}
      </div>

      <div className="border-b border-navy-800/50">
        <div className="px-5 py-2 bg-navy-800/10">
          <span className="text-xs text-slate-500 uppercase tracking-wider font-semibold">Batting</span>
        </div>
        <BattingTable batting={batting} />
      </div>

      {bowling.length > 0 && (
        <div>
          <div className="px-5 py-2 bg-navy-800/10 border-b border-navy-800/50">
            <span className="text-xs text-slate-500 uppercase tracking-wider font-semibold">Bowling</span>
          </div>
          <BowlingTable bowling={bowling} />
        </div>
      )}
    </div>
  )
}

function FallOfWicketsSection({ fow = [] }) {
  if (!fow.length) return null
  const byInnings = fow.reduce((acc, f) => {
    const k = f.innings_number; if (!acc[k]) acc[k] = []; acc[k].push(f); return acc
  }, {})
  return (
    <div className="card p-5">
      <h3 className="display-heading text-base text-white mb-3">FALL OF WICKETS</h3>
      {Object.entries(byInnings).map(([inn, items]) => (
        <div key={inn} className="mb-3 last:mb-0">
          {Object.keys(byInnings).length > 1 && <p className="section-label mb-2">Innings {inn}</p>}
          <div className="flex flex-wrap gap-2">
            {items.map((f, i) => (
              <div key={i} className="bg-navy-800 border border-navy-700 rounded px-2.5 py-1 text-xs">
                <span className="stat-number text-accent font-bold">{f.score_at_fall ?? '?'}</span>
                <span className="text-slate-600 mx-1">-</span>
                <span className="stat-number text-white">{f.wicket_number}</span>
                {f.player_name && (
                  <Link to={`/players/${f.player_id}`} className="text-slate-400 ml-1.5 hover:text-accent transition-colors">
                    {f.player_name}
                  </Link>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function PartnershipsSection({ partnerships = [] }) {
  if (!partnerships.length) return null
  const byInnings = partnerships.reduce((acc, p) => {
    const k = p.innings_number; if (!acc[k]) acc[k] = []; acc[k].push(p); return acc
  }, {})
  return (
    <div className="card overflow-hidden">
      <div className="px-5 py-3 border-b border-navy-700">
        <h3 className="display-heading text-base text-white">PARTNERSHIPS</h3>
      </div>
      {Object.entries(byInnings).map(([inn, items]) => (
        <div key={inn}>
          {Object.keys(byInnings).length > 1 && <p className="section-label px-5 pt-3 pb-1">Innings {inn}</p>}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-navy-700 bg-navy-800/20">
                  <th className="table-header pl-5">Wkt</th>
                  <th className="table-header">Batters</th>
                  <th className="table-header text-right pr-5">Runs</th>
                </tr>
              </thead>
              <tbody>
                {items.map((p, i) => (
                  <tr key={i} className="border-b border-navy-800/50">
                    <td className="py-2 px-5 stat-number text-slate-500">{p.wicket_number}</td>
                    <td className="py-2 px-3 text-slate-300 text-xs">
                      <span className="flex gap-3">
                        {p.batter1_name && (
                          <span>
                            <Link to={`/players/${p.batter1_id}`} className="hover:text-accent transition-colors">{p.batter1_name}</Link>
                            {p.batter1_runs != null && <span className="text-slate-600 ml-1">({p.batter1_runs})</span>}
                          </span>
                        )}
                        {p.batter2_name && (
                          <span>
                            <Link to={`/players/${p.batter2_id}`} className="hover:text-accent transition-colors">{p.batter2_name}</Link>
                            {p.batter2_runs != null && <span className="text-slate-600 ml-1">({p.batter2_runs})</span>}
                          </span>
                        )}
                      </span>
                    </td>
                    <td className="py-2 pr-5 stat-number text-right font-bold text-white">{p.runs ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  )
}

export default function MatchScorecard() {
  const { gameId } = useParams()
  const [searchParams] = useSearchParams()
  const orgId = searchParams.get('org')
  const navigate = useNavigate()
  const [game, setGame] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const fetch = orgId
      ? api.getPlayHQScorecard(orgId, gameId)
      : api.getScorecard(gameId)
    fetch
      .then(setGame)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [gameId, orgId])

  if (loading) return <LoadingSpinner message="Loading scorecard…" />
  if (error) return <div className="max-w-5xl mx-auto px-4 py-16 text-red-400">Error: {error}</div>
  if (!game) return null

  // Group batting and bowling by innings_number
  const inningsNums = [...new Set([
    ...(game.batting || []).map(r => r.innings_number || 1),
    ...(game.bowling || []).map(r => r.innings_number || 1),
  ])].sort()

  const innings = inningsNums.map(num => ({
    num,
    batting: (game.batting || []).filter(r => (r.innings_number || 1) === num),
    bowling: (game.bowling || []).filter(r => (r.innings_number || 1) === num),
  }))

  // Determine team name per innings: bowling team for inn 1 bats in inn 2 etc.
  const teams = [game.home_team, game.away_team].filter(Boolean)
  const getInningsTitle = (num, batting) => {
    if (batting.length && batting[0].player_name) {
      // Try to determine team from the winning_team / home/away assignment
    }
    // Fallback: just use home/away alternating
    return num === 1 ? (game.home_team || `Innings ${num}`) : (game.away_team || `Innings ${num}`)
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-1.5 text-slate-500 hover:text-white text-sm mb-5 transition-colors"
      >
        ← Back
      </button>
      <MatchSummary game={game} />

      <div className="space-y-5">
        {innings.map(({ num, batting, bowling }) => (
          <InningsBlock
            key={num}
            num={num}
            title={(num === 1 ? game.home_team : game.away_team)?.toUpperCase() || `INNINGS ${num}`}
            batting={batting}
            bowling={bowling}
          />
        ))}

        {innings.length === 0 && (
          <div className="card p-8 text-center text-slate-500">
            No scorecard data available for this match.
          </div>
        )}

        <FallOfWicketsSection fow={game.fall_of_wickets ?? []} />
        <PartnershipsSection partnerships={game.partnerships ?? []} />
      </div>
    </div>
  )
}
