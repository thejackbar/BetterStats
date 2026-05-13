import { useParams, useSearchParams, Link, useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { PbSpinner, Card, ResultPill } from '../lib/presskit'

function MatchHeader({ game }) {
  const totals = game.innings_totals || {}
  const inningNums = Object.keys(totals).map(Number).sort()
  const scoreLine = inningNums.map(n => {
    const t = totals[n]
    return `${t.runs}/${t.wickets}`
  }).join('  ·  ')

  const result = game.result || 'N/R'

  return (
    <div className="pb-card p-5 mb-5">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">
        {[game.season?.name, game.grade?.name].filter(Boolean).join(' · ')}
        {game.played_at && (
          <span className="ml-3">
            {new Date(game.played_at).toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
          </span>
        )}
      </p>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display font-bold text-[26px] sm:text-[32px] text-pb-text leading-tight tracking-tight">
            {game.home_team}
            <span className="text-pb-faint font-sans font-normal text-lg mx-3">vs</span>
            {game.away_team}
          </h1>
          {scoreLine && (
            <p className="font-mono text-pb-dim text-base mt-1.5 tracking-wider">{scoreLine}</p>
          )}
        </div>
        <div className="flex flex-col items-end gap-2 shrink-0">
          <ResultPill result={result} />
          {game.winning_team && (
            <p className="font-mono text-[11px] text-pb-faint">{game.winning_team} won</p>
          )}
        </div>
      </div>
    </div>
  )
}

function BattingTable({ batting = [] }) {
  if (!batting.length) return <p className="text-pb-faint text-sm py-4 px-5">No batting data.</p>

  const total = batting.reduce((s, r) => s + (r.runs ?? 0), 0)
  const wickets = batting.filter(r => !r.not_out && r.dismissal_type).length

  return (
    <div className="overflow-x-auto pb-scroll">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
            <th className="font-medium py-2.5 pl-5">BATTER</th>
            <th className="font-medium py-2.5 text-pb-faintest font-normal normal-case tracking-normal hidden sm:table-cell">Dismissal</th>
            <th className="font-medium py-2.5 text-right" style={{ color: 'var(--pb-accent)' }}>R</th>
            <th className="font-medium py-2.5 text-right">B</th>
            <th className="font-medium py-2.5 text-right hidden sm:table-cell">4s</th>
            <th className="font-medium py-2.5 text-right hidden sm:table-cell">6s</th>
            <th className="font-medium py-2.5 pr-5 text-right hidden sm:table-cell">SR</th>
          </tr>
        </thead>
        <tbody>
          {batting.map((row, i) => (
            <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
              <td className="py-2.5 pl-5">
                {row.player_id
                  ? <Link to={`/players/${row.player_id}`} className="text-pb-text font-semibold hover:text-pb-accent transition-colors">{row.player_name || '—'}</Link>
                  : <span className="text-pb-text font-semibold">{row.player_name || '—'}</span>
                }
              </td>
              <td className="py-2.5 px-3 text-pb-faint text-xs capitalize max-w-[140px] truncate hidden sm:table-cell">
                {row.not_out ? 'not out' : row.dismissal_type || '—'}
              </td>
              <td className="py-2.5 text-right">
                <span
                  className="font-mono font-bold pb-num"
                  style={{ color: row.runs >= 100 ? 'var(--pb-amber)' : row.runs >= 50 ? 'var(--pb-accent)' : undefined }}
                >
                  {row.runs ?? '—'}
                </span>
                {row.not_out && <span className="text-pb-accent text-xs">*</span>}
              </td>
              <td className="py-2.5 font-mono text-pb-dim text-right">{row.balls ?? '—'}</td>
              <td className="py-2.5 font-mono text-pb-faint text-right hidden sm:table-cell">{row.fours ?? '—'}</td>
              <td className="py-2.5 font-mono text-pb-faint text-right hidden sm:table-cell">{row.sixes ?? '—'}</td>
              <td className="py-2.5 pr-5 font-mono text-pb-faint text-right text-xs hidden sm:table-cell">
                {row.strike_rate != null ? Number(row.strike_rate).toFixed(1) : '—'}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="pb-hairline-t bg-pb-surface2/30">
            <td colSpan={2} className="py-2 pl-5 text-pb-dim font-semibold text-sm">Total</td>
            <td className="py-2 font-mono font-bold text-pb-text text-right pb-num">{total}/{wickets}</td>
            <td colSpan={4} />
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

function BowlingTable({ bowling = [] }) {
  if (!bowling.length) return <p className="text-pb-faint text-sm py-4 px-5">No bowling data.</p>

  return (
    <div className="overflow-x-auto pb-scroll">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
            <th className="font-medium py-2.5 pl-5">BOWLER</th>
            <th className="font-medium py-2.5 text-right">O</th>
            <th className="font-medium py-2.5 text-right hidden sm:table-cell">M</th>
            <th className="font-medium py-2.5 text-right">R</th>
            <th className="font-medium py-2.5 text-right" style={{ color: 'var(--pb-accent)' }}>W</th>
            <th className="font-medium py-2.5 text-right hidden sm:table-cell">ECON</th>
            <th className="font-medium py-2.5 text-right hidden md:table-cell">WD</th>
            <th className="font-medium py-2.5 pr-5 text-right hidden md:table-cell">NB</th>
          </tr>
        </thead>
        <tbody>
          {bowling.map((row, i) => (
            <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
              <td className="py-2.5 pl-5">
                {row.player_id
                  ? <Link to={`/players/${row.player_id}`} className="text-pb-text font-semibold hover:text-pb-accent transition-colors">{row.player_name || '—'}</Link>
                  : <span className="text-pb-text font-semibold">{row.player_name || '—'}</span>
                }
              </td>
              <td className="py-2.5 font-mono text-pb-dim text-right">{row.overs ?? '—'}</td>
              <td className="py-2.5 font-mono text-pb-faint text-right hidden sm:table-cell">{row.maidens ?? '—'}</td>
              <td className="py-2.5 font-mono text-pb-dim text-right">{row.runs ?? '—'}</td>
              <td className="py-2.5 text-right">
                <span
                  className="font-mono font-bold pb-num"
                  style={{ color: row.wickets >= 5 ? 'var(--pb-amber)' : row.wickets >= 3 ? 'var(--pb-accent)' : undefined }}
                >
                  {row.wickets ?? '—'}
                </span>
              </td>
              <td className="py-2.5 font-mono text-pb-dim text-right hidden sm:table-cell">
                {row.economy != null ? Number(row.economy).toFixed(2) : '—'}
              </td>
              <td className="py-2.5 font-mono text-pb-faint text-right hidden md:table-cell">{row.wides ?? '—'}</td>
              <td className="py-2.5 pr-5 font-mono text-pb-faint text-right hidden md:table-cell">{row.no_balls ?? '—'}</td>
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
    <div className="pb-card overflow-hidden">
      <div className="px-5 py-3 pb-hairline-b bg-pb-surface2/20 flex items-center justify-between">
        <div>
          <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-0.5">INNINGS {num}</p>
          <h3 className="font-display font-bold text-[16px] text-pb-text tracking-tight">{title}</h3>
        </div>
        {batting.length > 0 && (
          <div className="text-right">
            <span className="font-mono text-[22px] font-bold text-pb-text pb-num">{total}/{wickets}</span>
          </div>
        )}
      </div>

      <div className="pb-hairline-b">
        <div className="px-5 py-2 bg-pb-surface2/10">
          <span className="font-mono text-[10px] tracking-wide3 text-pb-faint">BATTING</span>
        </div>
        <BattingTable batting={batting} />
      </div>

      {bowling.length > 0 && (
        <div>
          <div className="px-5 py-2 bg-pb-surface2/10 pb-hairline-b">
            <span className="font-mono text-[10px] tracking-wide3 text-pb-faint">BOWLING</span>
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
    <div className="pb-card p-5">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3">FALL OF WICKETS</p>
      {Object.entries(byInnings).map(([inn, items]) => (
        <div key={inn} className="mb-3 last:mb-0">
          {Object.keys(byInnings).length > 1 && (
            <p className="font-mono text-[10px] tracking-wide2 text-pb-faintest mb-2 uppercase">Innings {inn}</p>
          )}
          <div className="flex flex-wrap gap-2">
            {items.map((f, i) => (
              <div key={i} className="bg-pb-surface border pb-hairline rounded px-2.5 py-1 text-xs">
                <span className="font-mono font-bold pb-num" style={{ color: 'var(--pb-accent)' }}>{f.score_at_fall ?? '?'}</span>
                <span className="text-pb-faint mx-1">-</span>
                <span className="font-mono text-pb-text">{f.wicket_number}</span>
                {f.player_name && (
                  <Link to={`/players/${f.player_id}`} className="text-pb-faint ml-1.5 hover:text-pb-accent transition-colors">
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
    <div className="pb-card overflow-hidden">
      <div className="px-5 py-3 pb-hairline-b">
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint">PARTNERSHIPS</p>
      </div>
      {Object.entries(byInnings).map(([inn, items]) => (
        <div key={inn}>
          {Object.keys(byInnings).length > 1 && (
            <p className="font-mono text-[10px] tracking-wide2 text-pb-faintest px-5 pt-3 pb-1 uppercase">Innings {inn}</p>
          )}
          <div className="overflow-x-auto pb-scroll">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
                  <th className="font-medium py-2.5 pl-5">WKT</th>
                  <th className="font-medium py-2.5">BATTERS</th>
                  <th className="font-medium py-2.5 pr-5 text-right" style={{ color: 'var(--pb-accent)' }}>RUNS</th>
                </tr>
              </thead>
              <tbody>
                {items.map((p, i) => (
                  <tr key={i} className={i ? 'pb-hairline-t' : ''}>
                    <td className="py-2 pl-5 font-mono text-pb-faint">{p.wicket_number}</td>
                    <td className="py-2 px-3 text-pb-dim text-xs">
                      <span className="flex flex-wrap gap-3">
                        {p.batter1_name && (
                          <span>
                            <Link to={`/players/${p.batter1_id}`} className="hover:text-pb-accent transition-colors">{p.batter1_name}</Link>
                            {p.batter1_runs != null && <span className="text-pb-faint ml-1">({p.batter1_runs})</span>}
                          </span>
                        )}
                        {p.batter2_name && (
                          <span>
                            <Link to={`/players/${p.batter2_id}`} className="hover:text-pb-accent transition-colors">{p.batter2_name}</Link>
                            {p.batter2_runs != null && <span className="text-pb-faint ml-1">({p.batter2_runs})</span>}
                          </span>
                        )}
                      </span>
                    </td>
                    <td className="py-2 pr-5 font-mono font-bold text-pb-text text-right pb-num">{p.runs ?? '—'}</td>
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

  if (loading) return <PbSpinner message="Loading scorecard…" />
  if (error) return (
    <div className="min-h-screen bg-pb-bg text-pb-text flex items-center justify-center">
      <p className="text-pb-red font-mono text-sm">Error: {error}</p>
    </div>
  )
  if (!game) return null

  const inningsNums = [...new Set([
    ...(game.batting || []).map(r => r.innings_number || 1),
    ...(game.bowling || []).map(r => r.innings_number || 1),
  ])].sort()

  const innings = inningsNums.map(num => ({
    num,
    batting: (game.batting || []).filter(r => (r.innings_number || 1) === num),
    bowling: (game.bowling || []).filter(r => (r.innings_number || 1) === num),
  }))

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[900px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1.5 font-mono text-[11px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors mb-5"
        >
          ← BACK
        </button>

        <MatchHeader game={game} />

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
            <Card>
              <div className="py-12 text-center text-pb-faint">
                No scorecard data available for this match.
              </div>
            </Card>
          )}

          <FallOfWicketsSection fow={game.fall_of_wickets ?? []} />
          <PartnershipsSection partnerships={game.partnerships ?? []} />
        </div>
      </main>
    </div>
  )
}
