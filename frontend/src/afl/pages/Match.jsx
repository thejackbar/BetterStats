import { useEffect, useMemo, useState } from 'react'
import { useOutletContext, useParams, Link } from 'react-router-dom'
import clsx from 'clsx'
import LoadingSpinner from '../../components/LoadingSpinner'
import { aflApi, scoreLine } from '../aflApi'
import { SectionTitle, PlayerCell } from '../components/bits'

const PERIOD_LABELS = { 1: 'Q1', 2: 'Q2', 3: 'Q3', 4: 'Q4' }

function Crest({ url, name }) {
  const [err, setErr] = useState(false)
  if (!url || err) {
    return (
      <span className="h-10 w-10 rounded-full bg-pb-surface2 flex items-center justify-center text-xs font-bold text-pb-faint">
        {(name || '?').split(' ').map(w => w[0]).slice(0, 2).join('')}
      </span>
    )
  }
  return <img src={url} alt="" className="h-10 w-10 object-contain" onError={() => setErr(true)} />
}

export default function Match() {
  const { club } = useOutletContext()
  const { gameId } = useParams()
  const [game, setGame] = useState(null)
  const [notFound, setNotFound] = useState(false)
  const [tab, setTab] = useState('stats')
  const base = `/${club.slug}`

  useEffect(() => {
    setGame(null)
    aflApi.getGame(gameId).then(setGame).catch(() => setNotFound(true))
  }, [gameId])

  // Cumulative quarter scores per side (the API stores per-quarter deltas).
  const periodTable = useMemo(() => {
    if (!game?.periods?.length) return null
    const bySide = { HOME: [], AWAY: [] }
    for (const p of game.periods) bySide[p.side]?.push(p)
    const numbers = [...new Set(game.periods.map(p => p.period_number))].sort((a, b) => a - b)
    const rows = {}
    for (const side of ['HOME', 'AWAY']) {
      let g = 0, b = 0, s = 0
      rows[side] = numbers.map(n => {
        const p = bySide[side].find(x => x.period_number === n)
        g += p?.goals || 0; b += p?.behinds || 0; s += p?.score || 0
        return { n, goals: g, behinds: b, score: s }
      })
    }
    return { numbers, rows }
  }, [game])

  if (notFound) return <p className="pt-16 text-center text-pb-dim">Game not found.</p>
  if (!game) return <div className="pt-16 flex justify-center"><LoadingSpinner /></div>

  const homeWon = game.winning_team && game.winning_team === game.home_team
  const awayWon = game.winning_team && game.winning_team === game.away_team

  const lines = game.player_lines || []
  const bySide = { HOME: lines.filter(l => l.side === 'HOME'), AWAY: lines.filter(l => l.side === 'AWAY') }
  const bestPlayers = (side) => bySide[side]
    .filter(l => l.bog_ranking != null)
    .sort((a, b) => a.bog_ranking - b.bog_ranking)

  const Side = ({ side }) => {
    const isHome = side === 'HOME'
    const won = isHome ? homeWon : awayWon
    return (
      <div className={clsx('flex items-center gap-3 flex-1 min-w-0', !isHome && 'flex-row-reverse text-right')}>
        <Crest url={isHome ? game.home_logo_url : game.away_logo_url} name={isHome ? game.home_team : game.away_team} />
        <div className="min-w-0">
          <div className="font-semibold truncate flex items-center gap-2">
            <span className={clsx(!isHome && 'order-2')}>{isHome ? game.home_team : game.away_team}</span>
            {won && <span className="font-mono text-[9px] font-bold px-1 py-0.5 rounded bg-[color-mix(in_srgb,var(--pb-positive)_18%,transparent)] text-[var(--pb-positive)]">✓ WON</span>}
          </div>
          <div className="pb-num text-2xl font-bold">
            {scoreLine(isHome ? game.home_goals : game.away_goals,
                       isHome ? game.home_behinds : game.away_behinds,
                       isHome ? game.home_score : game.away_score)}
          </div>
        </div>
      </div>
    )
  }

  const statTable = (side) => {
    const rows = bySide[side]
    return (
      <div className="pb-card overflow-x-auto">
        <div className="px-3 pt-3 pb-1 font-mono text-[10px] uppercase tracking-wide3 text-pb-faint">
          {side === 'HOME' ? game.home_team : game.away_team}
        </div>
        <table className="w-full text-sm">
          <thead className="pb-hairline-b">
            <tr>
              <th className="px-3 py-2 text-left font-mono text-[10px] uppercase text-pb-faint w-10">#</th>
              <th className="px-3 py-2 text-left font-mono text-[10px] uppercase text-pb-faint">Player</th>
              <th className="px-3 py-2 text-right font-mono text-[10px] uppercase text-pb-faint">G</th>
              <th className="px-3 py-2 text-right font-mono text-[10px] uppercase text-pb-faint">B</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(l => (
              <tr key={`${l.side}-${l.name}-${l.jumper_number}`} className="pb-hairline-b last:border-0">
                <td className="px-3 py-1.5 pb-num text-pb-faint">{l.jumper_number}</td>
                <td className="px-3 py-1.5">
                  <span className="flex items-center gap-1.5">
                    <PlayerCell id={l.player_id} name={l.name} base={base} />
                    {l.is_captain && <span className="text-[9px] font-mono text-pb-faint border border-pb-hairline rounded px-1">C</span>}
                    {l.bog_ranking != null && (
                      <span className="font-mono text-[9px] font-bold px-1 rounded bg-[color-mix(in_srgb,var(--pb-amber)_20%,transparent)] text-[var(--pb-amber)]">BOG</span>
                    )}
                  </span>
                </td>
                <td className="px-3 py-1.5 text-right pb-num font-semibold">{l.goals || 0}</td>
                <td className="px-3 py-1.5 text-right pb-num">{l.behinds || 0}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={4} className="px-3 py-3 text-pb-faint text-sm">Team list not published.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="text-sm text-pb-faint">
        <Link to={`${base}/games`} className="hover:text-pb-text">← All games</Link>
      </div>

      <div className="pb-card p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono uppercase tracking-wide text-pb-faint">
          <span>{game.grade_name}</span>
          <span>·</span>
          <span>{game.round_name || (game.is_final ? 'Final' : '')}</span>
          <span>·</span>
          <span>{game.played_at}{game.start_time ? ` ${game.start_time.slice(0, 5)}` : ''}</span>
          {(game.venue_name || game.venue) && (<><span>·</span><span>{game.venue_name || game.venue}</span></>)}
        </div>
        <div className="flex items-center gap-4">
          <Side side="HOME" />
          <span className="text-pb-faintest font-mono text-sm shrink-0">VS</span>
          <Side side="AWAY" />
        </div>
        {game.outcome_description && (
          <p className="text-sm text-pb-dim">{game.outcome_description}</p>
        )}
      </div>

      {periodTable && (
        <div>
          <SectionTitle>Period scores</SectionTitle>
          <div className="pb-card overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="pb-hairline-b">
                <tr>
                  <th className="px-3 py-2 text-left font-mono text-[10px] uppercase text-pb-faint">End of period</th>
                  {periodTable.numbers.map(n => (
                    <th key={n} className="px-3 py-2 text-right font-mono text-[10px] uppercase text-pb-faint">
                      {PERIOD_LABELS[n] || `OT${n - 4}`}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {['HOME', 'AWAY'].map(side => (
                  <tr key={side} className="pb-hairline-b last:border-0">
                    <td className="px-3 py-2 font-medium">{side === 'HOME' ? game.home_team : game.away_team}</td>
                    {periodTable.rows[side].map(p => (
                      <td key={p.n} className="px-3 py-2 text-right">
                        <span className="pb-num font-bold">{p.score}</span>
                        <span className="block text-[11px] text-pb-faintest pb-num">{p.goals}.{p.behinds}</span>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {(bestPlayers('HOME').length > 0 || bestPlayers('AWAY').length > 0) && (
        <div className="grid md:grid-cols-2 gap-4">
          {['HOME', 'AWAY'].map(side => (
            <div key={side} className="pb-card p-4">
              <SectionTitle>Best players — {side === 'HOME' ? game.home_team : game.away_team}</SectionTitle>
              <p className="text-sm">
                {bestPlayers(side).map((l, i) => (
                  <span key={l.name + i}>
                    {i > 0 && ', '}
                    {l.player_id
                      ? <Link to={`${base}/players/${l.player_id}`} className="text-[var(--pb-accent)] hover:underline">{l.name}</Link>
                      : l.name}
                  </span>
                ))}
                {bestPlayers(side).length === 0 && <span className="text-pb-faint">Not recorded.</span>}
              </p>
            </div>
          ))}
        </div>
      )}

      <div>
        <div className="flex gap-1 mb-3">
          {[['stats', 'Player statistics'], ['pbp', 'Play-by-play']].map(([k, label]) => (
            <button
              key={k}
              onClick={() => setTab(k)}
              className={clsx(
                'px-3 py-1.5 rounded text-sm font-medium',
                tab === k ? 'bg-[var(--pb-accent)] text-black' : 'bg-pb-surface2 text-pb-dim hover:text-pb-text',
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {tab === 'stats' && (
          <div className="grid lg:grid-cols-2 gap-4">
            {statTable('HOME')}
            {statTable('AWAY')}
          </div>
        )}

        {tab === 'pbp' && (
          <div className="pb-card">
            {(game.events || []).length === 0 && (
              <p className="p-4 text-sm text-pb-faint">No play-by-play was recorded for this game.</p>
            )}
            {(game.events || []).map((ev, i) => {
              const prev = game.events[i - 1]
              const showHeader = !prev || prev.period_label !== ev.period_label
              return (
                <div key={ev.sequence}>
                  {showHeader && (
                    <div className="px-3 py-2 bg-pb-surface2 font-mono text-[10px] uppercase tracking-wide3 text-pb-faint pb-hairline-b">
                      {ev.period_label}
                    </div>
                  )}
                  <div className="px-3 py-2 flex items-center gap-3 pb-hairline-b text-sm">
                    <span className="pb-num text-pb-faint w-12">{ev.clock}</span>
                    <span className={clsx(
                      'font-mono text-[10px] font-bold px-1.5 py-0.5 rounded w-14 text-center',
                      ev.event_type === 'Goal'
                        ? 'bg-[color-mix(in_srgb,var(--pb-accent)_18%,transparent)] text-[var(--pb-accent)]'
                        : 'bg-pb-surface2 text-pb-dim',
                    )}>
                      {ev.event_type}
                    </span>
                    <span className="flex-1 min-w-0">
                      <span className="font-medium">{ev.team_name}</span>
                      {ev.scorer_name && (
                        <span className="text-pb-dim">
                          {' — '}
                          {ev.player_id
                            ? <Link to={`${base}/players/${ev.player_id}`} className="hover:text-[var(--pb-accent)]">{ev.scorer_number ? `${ev.scorer_number}. ` : ''}{ev.scorer_name}</Link>
                            : `${ev.scorer_number ? `${ev.scorer_number}. ` : ''}${ev.scorer_name}`}
                        </span>
                      )}
                    </span>
                    <span className="pb-num text-pb-faint">{ev.progressive_score}</span>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
