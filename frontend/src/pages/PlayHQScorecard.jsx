import { useParams, useSearchParams, Link } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { PbSpinner, ResultPill } from '../lib/presskit'

function fmtDate(iso) {
  if (!iso) return null
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-AU', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  })
}

function ResultBanner({ game, toss }) {
  if (!game) return null
  const isWin = game.result === 'WIN'
  const isDraw = ['DRAW', 'TIE', 'NO_RESULT'].includes(game.result)

  return (
    <div className={`pb-card p-5 mb-5 ${
      isWin ? 'border-pb-accent/30' : isDraw ? 'border-pb-faintest' : 'border-pb-red/30'
    }`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          {(game.season || game.grade?.name) && (
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2 uppercase">
              {[game.season, game.grade?.name].filter(Boolean).join(' · ')}
              {game.round && <span> · {game.round}</span>}
            </p>
          )}
          <h2 className="font-display font-bold text-[24px] md:text-[30px] text-pb-text leading-tight tracking-tight">
            {game.home_team}
            <span className="text-pb-faint font-sans font-normal text-xl mx-2">vs</span>
            {game.away_team}
          </h2>
          {game.played_at && (
            <p className="text-pb-faint text-sm mt-1">{fmtDate(game.played_at)}</p>
          )}
          {game.venue && <p className="font-mono text-[10px] text-pb-faintest mt-0.5">{game.venue}</p>}
          {toss && <p className="font-mono text-[10px] text-pb-faintest mt-2 italic">{toss}</p>}
        </div>

        <div className="text-right shrink-0">
          {(game.competitors || []).map((c, i) => (
            <div key={i} className="mb-1">
              <span className="font-mono text-[10px] text-pb-faint mr-2">{c.name}</span>
              {(c.innings || []).map((inn, j) => (
                <span key={j} className="font-mono font-bold text-sm text-pb-text mr-2 pb-num">
                  {inn.score ?? '—'}{inn.declared ? '*' : ''}
                </span>
              ))}
              {!c.innings?.length && c.score != null && (
                <span className="font-mono font-bold text-sm text-pb-text pb-num">{c.score}</span>
              )}
            </div>
          ))}
          <div className="mt-2 flex justify-end">
            <ResultPill result={game.result || 'N/R'} />
          </div>
          {game.winning_team && (
            <p className="font-mono text-[10px] text-pb-faint mt-1">{game.winning_team} won</p>
          )}
        </div>
      </div>
    </div>
  )
}

function ScoreLine({ innings }) {
  const runs = innings.total_runs ?? innings.batting.reduce((s, r) => s + (r.runs ?? 0), 0)
  const wickets = innings.total_wickets ?? innings.batting.filter(r => !r.not_out && !r.did_not_bat).length
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <span className="font-mono text-[20px] font-bold text-pb-text pb-num">{runs}/{wickets}</span>
      {innings.overs != null && <span className="font-mono text-sm text-pb-faint">({innings.overs} ov)</span>}
      {innings.extras != null && <span className="font-mono text-[11px] text-pb-faintest">Extras: {innings.extras}</span>}
    </div>
  )
}

function BattingTable({ batting = [] }) {
  if (!batting.length) return <p className="text-pb-faint text-sm py-4 px-5">No batting data.</p>

  const dnb = batting.filter(r => r.did_not_bat)
  const batted = batting.filter(r => !r.did_not_bat)

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
          {batted.map((row, i) => (
            <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
              <td className="py-2.5 pl-5">
                {row.player_id
                  ? <Link to={`/players/${row.player_id}`} className="text-pb-text font-semibold hover:text-pb-accent transition-colors">{row.name}</Link>
                  : <span className="text-pb-text font-semibold">{row.name}</span>
                }
              </td>
              <td className="py-2.5 px-3 text-pb-faint text-xs hidden sm:table-cell">
                {row.how_out || (row.not_out ? 'not out' : '—')}
              </td>
              <td className="py-2.5 text-right">
                <span className="font-mono font-bold pb-num" style={{
                  color: (row.runs ?? 0) >= 100 ? 'var(--pb-amber)' : (row.runs ?? 0) >= 50 ? 'var(--pb-accent)' : undefined
                }}>
                  {row.runs ?? '—'}
                </span>
                {row.not_out && <span className="text-pb-accent text-xs">*</span>}
              </td>
              <td className="py-2.5 font-mono text-pb-dim text-right">{row.balls ?? '—'}</td>
              <td className="py-2.5 font-mono text-pb-faint text-right hidden sm:table-cell">{row.fours ?? '—'}</td>
              <td className="py-2.5 font-mono text-pb-faint text-right hidden sm:table-cell">{row.sixes ?? '—'}</td>
              <td className="py-2.5 pr-5 font-mono text-pb-faint text-right hidden sm:table-cell">
                {row.strike_rate != null ? Number(row.strike_rate).toFixed(2) : '—'}
              </td>
            </tr>
          ))}
        </tbody>
        {dnb.length > 0 && (
          <tfoot>
            <tr className="pb-hairline-t">
              <td colSpan={7} className="px-5 py-2 font-mono text-[10px] text-pb-faintest italic">
                DNB: {dnb.map(r => r.name).join(', ')}
              </td>
            </tr>
          </tfoot>
        )}
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
                  ? <Link to={`/players/${row.player_id}`} className="text-pb-text font-semibold hover:text-pb-accent transition-colors">{row.name}</Link>
                  : <span className="text-pb-text font-semibold">{row.name}</span>
                }
              </td>
              <td className="py-2.5 font-mono text-pb-dim text-right">{row.overs ?? '—'}</td>
              <td className="py-2.5 font-mono text-pb-faint text-right hidden sm:table-cell">{row.maidens ?? '—'}</td>
              <td className="py-2.5 font-mono text-pb-dim text-right">{row.runs ?? '—'}</td>
              <td className="py-2.5 text-right">
                <span className="font-mono font-bold pb-num" style={{
                  color: (row.wickets ?? 0) >= 5 ? 'var(--pb-amber)' : (row.wickets ?? 0) >= 3 ? 'var(--pb-accent)' : undefined
                }}>
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

function InningsCard({ innings, accentTitle }) {
  const label = innings.batting_team || `Innings ${innings.innings_number}`

  return (
    <div className="pb-card overflow-hidden flex flex-col">
      <div className="px-5 py-4 pb-hairline-b">
        <h3 className={`font-display font-bold text-[17px] tracking-tight ${accentTitle ? '' : 'text-pb-text'}`}
          style={accentTitle ? { color: 'var(--pb-accent)' } : {}}>
          {label.toUpperCase()}
        </h3>
        {innings.bowling_team && (
          <p className="font-mono text-[10px] text-pb-faintest mt-0.5">Bowling: {innings.bowling_team}</p>
        )}
        <div className="mt-2">
          <ScoreLine innings={innings} />
        </div>
      </div>

      <div className="pb-hairline-b">
        <div className="px-5 py-2 bg-pb-surface2/10">
          <span className="font-mono text-[10px] tracking-wide3 text-pb-faint">BATTING</span>
        </div>
        <BattingTable batting={innings.batting} />
      </div>

      {innings.bowling.length > 0 && (
        <div>
          <div className="px-5 py-2 bg-pb-surface2/10 pb-hairline-b">
            <span className="font-mono text-[10px] tracking-wide3 text-pb-faint">BOWLING</span>
          </div>
          <BowlingTable bowling={innings.bowling} />
        </div>
      )}
    </div>
  )
}

export default function PlayHQScorecard() {
  const { gameId } = useParams()
  const [searchParams] = useSearchParams()
  const orgId = searchParams.get('org')

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!orgId) {
      setError('Missing org parameter')
      setLoading(false)
      return
    }
    api.getPlayHQScorecard(orgId, gameId)
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [gameId, orgId])

  if (loading) return <PbSpinner message="Loading scorecard…" />
  if (error) return (
    <div className="min-h-screen bg-pb-bg flex items-center justify-center">
      <p className="text-pb-red font-mono text-sm">Error: {error}</p>
    </div>
  )
  if (!data) return null

  const { innings = [], game, toss, status } = data

  if (!innings.length) {
    return (
      <div className="min-h-screen bg-pb-bg text-pb-text flex items-center justify-center">
        <div className="text-center px-4">
          <p className="text-pb-faint text-lg mb-2">Scorecard not available</p>
          <p className="font-mono text-[11px] text-pb-faintest mb-6">
            {status === 'FINAL'
              ? 'The match is complete but scorecard data could not be loaded.'
              : 'This match may not have started yet or data is still being processed.'}
          </p>
        </div>
      </div>
    )
  }

  const isTwoInnings = innings.length >= 2

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-7xl mx-auto px-4 py-8">
        <ResultBanner game={game} toss={toss} />

        {isTwoInnings ? (
          <div className="grid lg:grid-cols-2 gap-5">
            {innings.map((inn, i) => (
              <InningsCard key={inn.innings_number} innings={inn} accentTitle={i === 0} />
            ))}
          </div>
        ) : (
          <div className="space-y-5">
            {innings.map((inn, i) => (
              <InningsCard key={inn.innings_number} innings={inn} accentTitle={i === 0} />
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
