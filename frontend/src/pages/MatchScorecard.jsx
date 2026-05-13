import { useParams, useSearchParams, Link, useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { PbSpinner, Card, ResultPill } from '../lib/presskit'

function MatchHeader({ game, innings }) {
  const totals = game.innings_totals || {}

  // Calculate overs per innings from bowling data
  const oversByInnings = {}
  for (const row of (game.bowling || [])) {
    const n = row.innings_number || 1
    oversByInnings[n] = (oversByInnings[n] || 0) + (row.overs || 0)
  }

  const inn1 = totals[1] || {}
  const inn2 = totals[2] || {}
  const overs1 = oversByInnings[1] ? Number(oversByInnings[1]).toFixed(1) : null
  const overs2 = oversByInnings[2] ? Number(oversByInnings[2]).toFixed(1) : null
  const rr1 = overs1 && inn1.runs ? (inn1.runs / Number(overs1)).toFixed(2) : null
  const rr2 = overs2 && inn2.runs ? (inn2.runs / Number(overs2)).toFixed(2) : null

  const homeScore = inn1.runs != null ? `${inn1.runs}${inn1.wickets != null && inn1.wickets < 10 ? `/${inn1.wickets}` : ' a.o.'}` : null
  const awayScore = inn2.runs != null ? `${inn2.runs}${inn2.wickets != null && inn2.wickets < 10 ? `/${inn2.wickets}` : ' a.o.'}` : null

  const dateStr = game.played_at
    ? new Date(game.played_at).toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }).toUpperCase()
    : null
  const venue = game.venue || game.ground || null

  return (
    <div className="pb-card overflow-hidden mb-5">
      {/* Grade / date strip */}
      <div className="px-5 py-2.5 pb-hairline-b bg-pb-surface2/40 flex items-center justify-between gap-4 flex-wrap">
        <span className="font-mono text-[10px] tracking-wide3 text-pb-faint">
          {[game.season?.name, game.grade?.name].filter(Boolean).join(' · ')}
        </span>
        {dateStr && <span className="font-mono text-[10px] tracking-wide3 text-pb-faint">{dateStr}{venue ? ` · ${venue}` : ''}</span>}
      </div>

      {/* Main score block: HOME | RESULT | AWAY */}
      <div className="grid grid-cols-[1fr_auto_1fr] gap-0 px-0">
        {/* Home team */}
        <div className="px-6 py-5 text-center border-r pb-hairline-r">
          <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1">HOME</div>
          <div className="font-display font-bold text-[22px] sm:text-[28px] text-pb-text leading-tight tracking-tight">
            {game.home_team || '—'}
          </div>
          {homeScore && (
            <div className="font-mono font-bold text-[36px] sm:text-[48px] leading-none mt-1" style={{ color: 'var(--pb-accent)' }}>
              {homeScore}
            </div>
          )}
          {overs1 && (
            <div className="font-mono text-[11px] text-pb-faint mt-1 tracking-wide2">
              {overs1} overs{rr1 ? ` · RR ${rr1}` : ''}
            </div>
          )}
        </div>

        {/* Result */}
        <div className="px-4 sm:px-8 py-5 text-center flex flex-col items-center justify-center gap-2">
          <div className="font-mono text-[9px] tracking-wide3 text-pb-faintest">RESULT</div>
          <ResultPill result={game.result || 'N/R'} />
          {game.winning_team && (
            <div className="font-mono text-[11px] text-pb-dim text-center max-w-[120px] leading-tight">{game.winning_team} won</div>
          )}
        </div>

        {/* Away team */}
        <div className="px-6 py-5 text-center border-l pb-hairline-l">
          <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1">AWAY</div>
          <div className="font-display font-bold text-[22px] sm:text-[28px] text-pb-text leading-tight tracking-tight">
            {game.away_team || '—'}
          </div>
          {awayScore && (
            <div className="font-mono font-bold text-[36px] sm:text-[48px] leading-none mt-1 text-pb-dim">
              {awayScore}
            </div>
          )}
          {overs2 && (
            <div className="font-mono text-[11px] text-pb-faint mt-1 tracking-wide2">
              {overs2} overs{rr2 ? ` · RR ${rr2}` : ''}
            </div>
          )}
        </div>
      </div>

      {/* Toss / Umpires strip */}
      {(game.toss || game.umpires) && (
        <div className="px-5 py-2.5 pb-hairline-t bg-pb-surface2/20 flex flex-wrap gap-x-6 gap-y-1">
          {game.toss && (
            <span className="font-mono text-[10.5px] text-pb-dim">
              <span className="text-pb-faint">TOSS</span> {game.toss}
            </span>
          )}
          {game.umpires && (
            <span className="font-mono text-[10.5px] text-pb-dim">
              <span className="text-pb-faint">UMPIRES</span> {game.umpires}
            </span>
          )}
        </div>
      )}
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

function InningsCard({ title, teamLabel, batting, bowling }) {
  const total = batting.reduce((s, r) => s + (r.runs ?? 0), 0)
  const wickets = batting.filter(r => !r.not_out && r.dismissal_type).length

  return (
    <div className="pb-card overflow-hidden">
      <div className="px-5 py-3 pb-hairline-b bg-pb-surface2/20 flex items-center justify-between">
        <div>
          <p className="font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">{teamLabel}</p>
          <h3 className="font-display font-bold text-[15px] text-pb-text tracking-tight">{title}</h3>
        </div>
        {batting.length > 0 && (
          <span className="font-mono text-[20px] font-bold text-pb-text pb-num">{total}/{wickets}</span>
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

  const homeInnings = innings.find(i => i.num === 1) || { batting: [], bowling: [] }
  const awayInnings = innings.find(i => i.num === 2) || { batting: [], bowling: [] }

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1200px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1.5 font-mono text-[11px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors mb-5"
        >
          ← BACK
        </button>

        <MatchHeader game={game} innings={innings} />

        {innings.length === 0 ? (
          <Card>
            <div className="py-12 text-center text-pb-faint">No scorecard data available for this match.</div>
          </Card>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-5">
            <InningsCard
              title={(game.home_team || 'HOME TEAM').toUpperCase()}
              teamLabel="HOME · INNINGS 1"
              batting={homeInnings.batting}
              bowling={homeInnings.bowling}
            />
            <InningsCard
              title={(game.away_team || 'AWAY TEAM').toUpperCase()}
              teamLabel="AWAY · INNINGS 2"
              batting={awayInnings.batting}
              bowling={awayInnings.bowling}
            />
          </div>
        )}

        <FallOfWicketsSection fow={game.fall_of_wickets ?? []} />
        <PartnershipsSection partnerships={game.partnerships ?? []} />
      </main>
    </div>
  )
}
