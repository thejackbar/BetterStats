import { useParams, useSearchParams, Link, useNavigate } from 'react-router-dom'
import { useState, useEffect, useMemo } from 'react'
import { api } from '../lib/api'
import { PbSpinner, Card, ResultPill } from '../lib/presskit'
import { useNameFormat } from '../lib/nameFormat'
import { fmtOvers } from '../lib/cricketFormat'
import { useAuth } from '../contexts/AuthContext'
import { CAP } from '../lib/capabilities'

// Cricket overs are base-6: 3.4 + 2.3 = 6.1 (3 ov 4 balls + 2 ov 3 balls = 6 ov 1 ball)
function sumOversBalls(bowlingRows) {
  let totalBalls = 0
  for (const r of bowlingRows) {
    if (r.overs == null) continue
    const whole = Math.floor(r.overs)
    const balls = Math.round((r.overs - whole) * 10)
    totalBalls += whole * 6 + balls
  }
  return totalBalls
}

function ballsToOversStr(balls) {
  if (!balls) return null
  return `${Math.floor(balls / 6)}.${balls % 6}`
}

// Runs/wickets format: 224/6. All out (10 wkts or null wkts) = just runs.
function fmtScore(runs, wickets) {
  if (runs == null) return null
  if (wickets == null || wickets >= 10) return `${runs}`
  return `${runs}/${wickets}`
}

// Shorten "Firstname Lastname" → "F Lastname" in dismissal strings.
// caughtBehind: when the dismissal was a catch by the keeper. The live
// dismissalText already carries the standard dagger (†) before the keeper's
// name; when we only have the stored short code ("c"), the flag lets us still
// mark it "(wk)" so caught-behind shows even without a live fetch.
function fmtDismissal(text, caughtBehind) {
  if (!text) return '—'
  let out = text.replace(/\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b/g, match => {
    const words = match.trim().split(/\s+/)
    return `${words[0][0]} ${words[words.length - 1]}`
  })
  if (caughtBehind && !out.includes('†')) out = `${out} (wk)`
  return out
}

// True iff two team-name strings refer to the same club.
// Splits on whitespace/hyphens, drops tokens shorter than 4 chars (e.g. "XI",
// "CC", "6th"), then checks for any exact-word overlap.
// Using String.includes() would give false positives: "ross" ⊂ "applecross".
function teamsMatch(a, b) {
  if (!a || !b) return false
  const sig = s => s.toLowerCase().split(/[\s\-]+/).filter(w => w.length >= 4)
  const aWords = sig(a)
  const bSet = new Set(sig(b))
  return aWords.some(w => bSet.has(w))
}

function MatchHeader({ game, innings }) {
  const dateStr = game.played_at
    ? new Date(game.played_at).toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }).toUpperCase()
    : null
  const venue = game.venue || game.ground || null

  // Build per-innings data with accurate totals, overs, RR
  const inningsData = innings.map(inn => {
    const t = (game.innings_totals || {})[inn.num] || {}
    // Use backend totals if available, fall back to summing batting rows. Add extras to total.
    const batsRuns = t.runs ?? inn.batting.reduce((s, r) => s + (r.runs ?? 0), 0)
    const runs = batsRuns != null ? batsRuns + (t.extras ?? 0) : null
    const wickets = t.runs != null ? t.wickets : inn.batting.filter(r => !r.not_out && r.dismissal_type).length
    const balls = sumOversBalls(inn.bowling)
    const oversStr = ballsToOversStr(balls)
    const rr = (runs != null && balls > 0) ? (runs / (balls / 6)).toFixed(2) : null
    return { ...inn, runs, wickets, oversStr, rr, battingTeam: t.batting_team || '' }
  })

  // Map innings to home/away using batting_team if available
  const homeTeam = game.home_team || ''
  const inn1Data = inningsData[0]
  const inn2Data = inningsData[1]

  // Determine which innings is home vs away
  let homeInn = inn1Data, awayInn = inn2Data
  if (inn1Data?.battingTeam && homeTeam) {
    if (!teamsMatch(inn1Data.battingTeam, homeTeam) && inn2Data) {
      homeInn = inn2Data
      awayInn = inn1Data
    }
  }

  // Win/loss background tints
  const winner = (game.winning_team || '').toLowerCase().trim()
  const homeWon = !!winner && !!(homeTeam) && teamsMatch(game.winning_team || '', homeTeam)
  const awayTeam = game.away_team || ''
  const awayWon = !!winner && !homeWon
  const winBg = 'rgba(22,199,132,0.07)'
  const lossBg = 'rgba(220,38,38,0.07)'

  return (
    <div className="pb-card overflow-hidden mb-5">
      {/* Teams + scores — main hero */}
      <div className="grid grid-cols-[1fr_auto_1fr]">
        {/* Home */}
        <div
          className="px-3 sm:px-8 pt-5 pb-4 flex flex-col items-center text-center gap-1"
          style={winner ? { background: homeWon ? winBg : lossBg } : undefined}
        >
          <div className="font-mono text-[9px] tracking-wide3 text-pb-faintest">HOME</div>
          <div className="font-display font-bold text-[14px] sm:text-[22px] text-pb-text tracking-tight leading-tight">
            {homeTeam || '—'}
          </div>
          {homeInn && fmtScore(homeInn.runs, homeInn.wickets) != null && (
            <div className="font-mono font-bold text-[28px] sm:text-[48px] leading-none" style={{ color: homeWon ? 'var(--pb-accent)' : 'var(--pb-dim)' }}>
              {fmtScore(homeInn.runs, homeInn.wickets)}
            </div>
          )}
          {homeInn?.oversStr && (
            <div className="font-mono text-[10.5px] text-pb-faint tracking-wide2">
              {homeInn.oversStr} overs{homeInn.rr ? ` · RR ${homeInn.rr}` : ''}
            </div>
          )}
        </div>

        {/* Result */}
        <div className="px-2 sm:px-8 py-5 flex flex-col items-center justify-center gap-2 pb-hairline-l pb-hairline-r min-w-[110px] sm:min-w-[160px]">
          <div className="font-mono text-[9px] tracking-wide3 text-pb-faintest">RESULT</div>
          <ResultPill result={game.result || 'N/R'} />
          {game.winning_team && (
            <div className="font-mono text-[11px] text-pb-text font-semibold text-center leading-snug max-w-[160px]">
              {game.winning_team}
            </div>
          )}
          {game.winning_team && (
            <div className="font-mono text-[9px] tracking-wide2 text-pb-faint">WON</div>
          )}
          {dateStr && (
            <div className="font-mono text-[9px] tracking-wide2 text-pb-faintest text-center mt-1">
              {dateStr}{venue ? <><br />{venue}</> : ''}
            </div>
          )}
        </div>

        {/* Away */}
        <div
          className="px-3 sm:px-8 pt-5 pb-4 flex flex-col items-center text-center gap-1"
          style={winner ? { background: awayWon ? winBg : lossBg } : undefined}
        >
          <div className="font-mono text-[9px] tracking-wide3 text-pb-faintest">AWAY</div>
          <div className="font-display font-bold text-[14px] sm:text-[22px] text-pb-text tracking-tight leading-tight">
            {awayTeam || '—'}
          </div>
          {awayInn && fmtScore(awayInn.runs, awayInn.wickets) != null && (
            <div className="font-mono font-bold text-[28px] sm:text-[48px] leading-none" style={{ color: awayWon ? 'var(--pb-accent)' : 'var(--pb-dim)' }}>
              {fmtScore(awayInn.runs, awayInn.wickets)}
            </div>
          )}
          {awayInn?.oversStr && (
            <div className="font-mono text-[10.5px] text-pb-faint tracking-wide2">
              {awayInn.oversStr} overs{awayInn.rr ? ` · RR ${awayInn.rr}` : ''}
            </div>
          )}
        </div>
      </div>

      {/* Toss / Umpires strip */}
      {(game.toss || game.umpires) && (
        <div className="px-5 py-2.5 pb-hairline-t bg-pb-surface2/20 flex flex-wrap gap-x-6 gap-y-1">
          {game.toss && (
            <span className="font-mono text-[10.5px] text-pb-dim">
              <span className="text-pb-faint mr-2">TOSS</span>{game.toss}
            </span>
          )}
          {game.umpires && (
            <span className="font-mono text-[10.5px] text-pb-dim">
              <span className="text-pb-faint mr-2">UMPIRES</span>{game.umpires}
            </span>
          )}
        </div>
      )}
    </div>
  )
}

// A fill-in (borrowed player, or a CA-redacted junior) has no linked player_id.
// Flagged by the backend as `is_fill_in` so it can't be confused with an
// ordinary missing-name row.
function FillInBadge() {
  return (
    <span
      className="ml-1.5 align-middle font-mono text-[9px] tracking-wide2 px-1.5 py-0.5 rounded border border-pb-amber/30 text-pb-amber whitespace-nowrap"
      title="Not a registered club player — filled in for this game"
    >
      FILL-IN
    </span>
  )
}

// Admin-only affordance next to a genuine fill-in (never a redacted row —
// there's no identity to claim there). Opens the claim modal in the parent.
function ClaimButton({ row, onClaim }) {
  if (!row.is_fill_in || !row.grassroots_participant_id) return null
  return (
    <button
      type="button"
      onClick={() => onClaim(row)}
      className="ml-1.5 align-middle font-mono text-[9px] tracking-wide2 px-1.5 py-0.5 rounded border border-pb-hairline2 text-pb-faint hover:text-pb-accent hover:border-pb-accent/30 transition-colors whitespace-nowrap"
      title="Promote this fill-in to a real player"
    >
      CLAIM
    </button>
  )
}

function BattingCard({ label, teamName, batting = [], inningsTotal, fmtName = n => n, canManage = false, onClaim }) {
  const batted = batting
    .filter(r => !r.did_not_bat)
    .sort((a, b) => (a.batting_position ?? 999) - (b.batting_position ?? 999))
  const dnb = batting.filter(r => r.did_not_bat)
  if (!batted.length && !dnb.length) return null

  // Use backend total if available, otherwise sum batting rows. Always add extras to total.
  const extras = inningsTotal?.extras ?? null
  const batsRuns = inningsTotal?.runs ?? batted.reduce((s, r) => s + (r.runs ?? 0), 0)
  const total = batsRuns != null ? batsRuns + (extras ?? 0) : null
  const wickets = inningsTotal?.runs != null
    ? inningsTotal.wickets
    : batted.filter(r => !r.not_out && r.dismissal_type).length
  const score = fmtScore(total, wickets)

  return (
    <div className="pb-card overflow-hidden">
      {/* Card header: team name large, score large, innings label small below */}
      <div className="px-5 pt-4 pb-3 pb-hairline-b bg-pb-surface2/20 flex items-start justify-between gap-4">
        <div>
          <div className="font-display font-bold text-[16px] sm:text-[18px] tracking-tight text-pb-text leading-tight">
            {teamName}
          </div>
          <div className="font-mono text-[9px] tracking-wide3 text-pb-faintest mt-0.5">{label}</div>
        </div>
        {score != null && (
          <div className="font-mono font-bold text-[22px] sm:text-[26px] pb-num leading-none shrink-0" style={{ color: 'var(--pb-accent)' }}>
            {score}
          </div>
        )}
      </div>

      {/* Batting table */}
      <div className="overflow-x-auto [&::-webkit-scrollbar]:hidden" style={{ scrollbarWidth: 'none' }}>
        <table className="w-full text-[13px]">
          <thead>
            <tr className="font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/30" style={{ color: 'var(--pb-faintest)' }}>
              <th className="font-medium py-2 pl-5 pr-3">BATTER</th>
              <th className="font-medium py-2 pr-3 text-left max-sm:hidden">DISMISSAL</th>
              <th className="font-medium py-2 px-3 text-right w-12" style={{ color: 'var(--pb-accent)' }}>R</th>
              <th className="font-medium py-2 px-2 text-right w-10">B</th>
              <th className="font-medium py-2 px-2 text-right w-8 max-md:hidden">4s</th>
              <th className="font-medium py-2 pr-4 text-right w-8 max-md:hidden">6s</th>
            </tr>
          </thead>
          <tbody>
            {batted.map((row, i) => (
              <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                <td className="py-2 pl-5 pr-3 whitespace-nowrap">
                  {row.player_id
                    ? <Link to={`/players/${row.player_id}`} className="text-pb-text font-semibold hover:text-pb-accent transition-colors">{fmtName(row.player_name) || '—'}</Link>
                    : <span className="text-pb-text font-semibold">{fmtName(row.player_name) || '—'}</span>
                  }
                  {row.is_fill_in && <FillInBadge />}
                  {canManage && <ClaimButton row={row} onClaim={onClaim} />}
                </td>
                <td className="py-2 pr-5 font-mono text-[12px] whitespace-nowrap max-sm:hidden" style={{ color: 'var(--pb-faint)' }}>
                  {row.not_out ? 'not out' : fmtDismissal(row.dismissal_type, row.caught_behind)}
                </td>
                <td className="py-2 px-3 text-right w-12">
                  <span
                    className="font-mono font-bold text-[14px] pb-num"
                    style={{ color: row.runs >= 100 ? 'var(--pb-amber)' : row.runs >= 50 ? 'var(--pb-accent)' : undefined }}
                  >
                    {row.runs ?? '—'}
                  </span>
                  {row.not_out && <span className="text-pb-accent text-[11px]">*</span>}
                </td>
                <td className="py-2 px-2 font-mono text-[12px] text-pb-faint text-right w-10">{row.balls ?? '—'}</td>
                <td className="py-2 px-2 font-mono text-[12px] text-right w-8 max-md:hidden" style={{ color: 'var(--pb-faint)' }}>{row.fours ?? '—'}</td>
                <td className="py-2 pr-4 font-mono text-[12px] text-right w-8 max-md:hidden" style={{ color: 'var(--pb-faint)' }}>{row.sixes ?? '—'}</td>
              </tr>
            ))}
            {dnb.map((row, i) => (
              <tr key={`dnb-${i}`} className="pb-hairline-t hover:bg-pb-surface2">
                <td className="py-2 pl-5 pr-3 whitespace-nowrap">
                  {row.player_id
                    ? <Link to={`/players/${row.player_id}`} className="text-pb-text font-semibold hover:text-pb-accent transition-colors">{fmtName(row.player_name) || '—'}</Link>
                    : <span className="text-pb-text font-semibold">{fmtName(row.player_name) || '—'}</span>
                  }
                  {row.is_fill_in && <FillInBadge />}
                  {canManage && <ClaimButton row={row} onClaim={onClaim} />}
                </td>
                <td className="py-2 pr-5 font-mono text-[12px] italic max-sm:hidden" style={{ color: 'var(--pb-faintest)' }}>did not bat</td>
                <td className="py-2 px-3 font-mono text-[12px] text-pb-faintest text-right">—</td>
                <td className="py-2 px-2 font-mono text-[12px] text-pb-faintest text-right">—</td>
                <td className="py-2 px-2 font-mono text-[12px] text-pb-faintest text-right max-md:hidden">—</td>
                <td className="py-2 pr-4 font-mono text-[12px] text-pb-faintest text-right max-md:hidden">—</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            {extras != null && extras > 0 && (
              <tr className="pb-hairline-t">
                <td className="py-1.5 pl-5 font-mono text-[11px] text-pb-faint" colSpan={2}>Extras</td>
                <td className="py-1.5 px-3 font-mono text-[13px] text-pb-faint text-right">{extras}</td>
                <td colSpan={3} />
              </tr>
            )}
            <tr className="pb-hairline-t bg-pb-surface2/20">
              <td colSpan={2} className="py-2 pl-5 font-mono text-[10px] tracking-wide2 text-pb-faint hidden sm:table-cell">BATTING TOTAL</td>
              <td className="py-2 px-3 font-mono font-bold text-pb-text text-right pb-num">{score ?? '—'}</td>
              <td colSpan={3} />
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  )
}

function BowlingCard({ label, teamName, bowling = [], fmtName = n => n, canManage = false, onClaim }) {
  if (!bowling.length) return null

  return (
    <div className="pb-card overflow-hidden">
      <div className="px-5 pt-4 pb-3 pb-hairline-b bg-pb-surface2/20 flex items-start justify-between gap-4">
        <div>
          <div className="font-display font-bold text-[16px] sm:text-[18px] tracking-tight text-pb-text leading-tight">
            {teamName}
          </div>
          <div className="font-mono text-[9px] tracking-wide3 text-pb-faintest mt-0.5">{label} · BOWLING</div>
        </div>
      </div>
      <div className="overflow-x-auto [&::-webkit-scrollbar]:hidden" style={{ scrollbarWidth: 'none' }}>
        <table className="w-full text-[13px]">
          <thead>
            <tr className="font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/30" style={{ color: 'var(--pb-faintest)' }}>
              <th className="font-medium py-2 pl-5">BOWLER</th>
              <th className="font-medium py-2 px-3 text-right" style={{ color: 'var(--pb-text)' }}>O</th>
              <th className="font-medium py-2 px-3 text-right max-sm:hidden">M</th>
              <th className="font-medium py-2 px-3 text-right" style={{ color: 'var(--pb-text)' }}>R</th>
              <th className="font-medium py-2 px-3 text-right" style={{ color: 'var(--pb-accent)' }}>W</th>
              <th className="font-medium py-2 px-3 text-right max-sm:hidden">ECON</th>
              <th className="font-medium py-2 px-3 text-right max-md:hidden">WD</th>
              <th className="font-medium py-2 pr-5 text-right max-md:hidden">NB</th>
            </tr>
          </thead>
          <tbody>
            {bowling.map((row, i) => (
              <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                <td className="py-2 pl-5 whitespace-nowrap">
                  {row.player_id
                    ? <Link to={`/players/${row.player_id}`} className="text-pb-text font-semibold hover:text-pb-accent transition-colors">{fmtName(row.player_name) || '—'}</Link>
                    : <span className="text-pb-text font-semibold">{fmtName(row.player_name) || '—'}</span>
                  }
                  {row.is_fill_in && <FillInBadge />}
                  {canManage && <ClaimButton row={row} onClaim={onClaim} />}
                </td>
                <td className="py-2 px-3 font-mono font-semibold text-[13px] text-right" style={{ color: 'var(--pb-text)' }}>{fmtOvers(row.overs)}</td>
                <td className="py-2 px-3 font-mono text-[12px] text-right max-sm:hidden" style={{ color: 'var(--pb-faint)' }}>{row.maidens ?? 0}</td>
                <td className="py-2 px-3 font-mono font-semibold text-[13px] text-right" style={{ color: 'var(--pb-text)' }}>{row.runs ?? '—'}</td>
                <td className="py-2 px-3 text-right">
                  <span
                    className="font-mono font-bold text-[13px] pb-num"
                    style={{ color: row.wickets >= 5 ? 'var(--pb-amber)' : row.wickets >= 3 ? 'var(--pb-accent)' : 'var(--pb-text)' }}
                  >
                    {row.wickets ?? 0}
                  </span>
                </td>
                <td className="py-2 px-3 font-mono text-[12px] text-right max-sm:hidden" style={{ color: 'var(--pb-faint)' }}>
                  {row.economy != null ? Number(row.economy).toFixed(2) : '—'}
                </td>
                <td className="py-2 px-3 font-mono text-[12px] text-right max-md:hidden" style={{ color: 'var(--pb-faint)' }}>{row.wides ?? 0}</td>
                <td className="py-2 pr-5 font-mono text-[12px] text-right max-md:hidden" style={{ color: 'var(--pb-faint)' }}>{row.no_balls ?? 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function FallOfWicketsSection({ fow = [], fmtName = n => n }) {
  if (!fow.length) return null
  const byInnings = fow.reduce((acc, f) => {
    const k = f.innings_number; if (!acc[k]) acc[k] = []; acc[k].push(f); return acc
  }, {})
  return (
    <div className="pb-card p-5 mt-4">
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
                  f.player_id ? (
                    <Link to={`/players/${f.player_id}`} className="text-pb-faint ml-1.5 hover:text-pb-accent transition-colors">
                      {fmtName(f.player_name)}
                    </Link>
                  ) : (
                    <span className="text-pb-faint ml-1.5">{fmtName(f.player_name)}</span>
                  )
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function PartnershipsSection({ partnerships = [], fmtName = n => n }) {
  if (!partnerships.length) return null
  const byInnings = partnerships.reduce((acc, p) => {
    const k = p.innings_number; if (!acc[k]) acc[k] = []; acc[k].push(p); return acc
  }, {})
  return (
    <div className="pb-card overflow-hidden mt-4">
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
                <tr className="text-pb-faintest font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/30">
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
                        {(p.batter1_name || p.batter1_id) && (
                          <span>
                            {p.batter1_id
                              ? <Link to={`/players/${p.batter1_id}`} className="hover:text-pb-accent transition-colors">{fmtName(p.batter1_name)}</Link>
                              : p.batter1_name
                                ? <span>{fmtName(p.batter1_name)}</span>
                                : <span className="text-pb-faintest italic">Unknown</span>}
                            {p.batter1_is_fill_in && <FillInBadge />}
                            {p.batter1_runs != null && <span className="text-pb-faint ml-1">({p.batter1_runs})</span>}
                          </span>
                        )}
                        {(p.batter2_name || p.batter2_id) && (
                          <span>
                            {p.batter2_id
                              ? <Link to={`/players/${p.batter2_id}`} className="hover:text-pb-accent transition-colors">{fmtName(p.batter2_name)}</Link>
                              : p.batter2_name
                                ? <span>{fmtName(p.batter2_name)}</span>
                                : <span className="text-pb-faintest italic">Unknown</span>}
                            {p.batter2_is_fill_in && <FillInBadge />}
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

// Promote a scorecard fill-in into a real player: edit the name, optionally
// match it to an existing player (merges into them instead of creating a
// new row), and an optional free-text reference note — e.g. a pasted PlayHQ
// profile URL kept purely for the club's own record-keeping. That URL is NOT
// parsed or verified: PlayHQ's player pages are a client-rendered app with no
// documented public lookup API, so there's no reliable way to resolve it to
// a real identity automatically.
function ClaimFillInModal({ row, existingPlayers, onClose, onSaved }) {
  const [name, setName] = useState(row.player_name || '')
  const [query, setQuery] = useState('')
  const [matchedId, setMatchedId] = useState('')
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState(null)

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return []
    return (existingPlayers || [])
      .filter(p => (p.display_name || p.name || '').toLowerCase().includes(q))
      .slice(0, 8)
  }, [query, existingPlayers])

  const matchedPlayer = (existingPlayers || []).find(p => p.id === matchedId)

  async function save() {
    if (!name.trim()) { setErr('Name is required'); return }
    setSaving(true)
    setErr(null)
    try {
      await api.claimFillIn({
        grassroots_participant_id: row.grassroots_participant_id,
        name: name.trim(),
        existing_player_id: matchedId || null,
        reference_note: note.trim() || null,
      })
      onSaved()
    } catch (e) {
      setErr(e.message || 'Failed to claim this fill-in')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4" onClick={onClose}>
      <div className="pb-card w-full max-w-md p-5" onClick={e => e.stopPropagation()}>
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3">CLAIM FILL-IN</p>

        <label className="block font-mono text-[10px] text-pb-faintest mb-1">Name</label>
        <input
          value={name}
          onChange={e => setName(e.target.value)}
          className="w-full mb-3 px-3 py-2 rounded bg-pb-surface2 border border-pb-hairline text-sm text-pb-text"
        />

        <label className="block font-mono text-[10px] text-pb-faintest mb-1">
          Is this actually an existing player? (optional)
        </label>
        {matchedPlayer ? (
          <div className="flex items-center justify-between mb-3 px-3 py-2 rounded bg-pb-surface2 border border-pb-hairline text-sm">
            <span>{matchedPlayer.display_name || matchedPlayer.name}</span>
            <button type="button" onClick={() => { setMatchedId(''); setQuery('') }}
              className="font-mono text-[10px] text-pb-faint hover:text-pb-text">CLEAR</button>
          </div>
        ) : (
          <div className="relative mb-3">
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search players…"
              className="w-full px-3 py-2 rounded bg-pb-surface2 border border-pb-hairline text-sm text-pb-text"
            />
            {matches.length > 0 && (
              <div className="absolute z-10 top-full left-0 right-0 mt-1 pb-card overflow-hidden max-h-48 overflow-y-auto">
                {matches.map(p => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => { setMatchedId(p.id); setQuery('') }}
                    className="block w-full text-left px-3 py-2 text-sm hover:bg-pb-surface2"
                  >
                    {p.display_name || p.name}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        <label className="block font-mono text-[10px] text-pb-faintest mb-1">
          Reference note (optional — e.g. a pasted PlayHQ profile link, for your own records only)
        </label>
        <textarea
          value={note}
          onChange={e => setNote(e.target.value)}
          rows={2}
          className="w-full mb-3 px-3 py-2 rounded bg-pb-surface2 border border-pb-hairline text-sm text-pb-text"
        />

        {err && <p className="text-pb-red text-xs mb-3">{err}</p>}

        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">
            CANCEL
          </button>
          <button type="button" onClick={save} disabled={saving}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold disabled:opacity-50 text-pb-bg"
            style={{ background: 'var(--pb-accent)' }}>
            {saving ? 'SAVING…' : matchedId ? 'MERGE INTO PLAYER' : 'CREATE PLAYER'}
          </button>
        </div>
      </div>
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
  const [orgData, setOrgData] = useState(null)
  const fmtName = useNameFormat(orgData)
  const { hasCapability } = useAuth()
  const canManage = hasCapability(CAP.MANAGE_PLAYERS)
  const [claimTarget, setClaimTarget] = useState(null)
  const [existingPlayers, setExistingPlayers] = useState([])

  useEffect(() => {
    // Always DB-first → Grassroots fallback for live/unsynced (api.getScorecard);
    // the old PlayHQ Partner path (when ?org was present) is retired. ?org is
    // still read below purely for club name-formatting.
    api.getScorecard(gameId)
      .then(setGame)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [gameId])

  useEffect(() => {
    if (orgId) api.getOrg(orgId).then(setOrgData).catch(() => {})
  }, [orgId])

  useEffect(() => {
    // Only a club admin can even open the claim modal, and the roster list is
    // only needed once they do — skip the fetch entirely otherwise.
    if (canManage) api.adminListPlayers().then(setExistingPlayers).catch(() => {})
  }, [canManage])

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
    ...(game.opp_batting || []).map(r => r.innings_number || 1),
    ...(game.opp_bowling || []).map(r => r.innings_number || 1),
  ])].sort()

  const innings = inningsNums.map(num => ({
    num,
    batting: [
      ...(game.batting || []).filter(r => (r.innings_number || 1) === num),
      ...(game.opp_batting || []).filter(r => (r.innings_number || 1) === num),
    ],
    bowling: [
      ...(game.bowling || []).filter(r => (r.innings_number || 1) === num),
      ...(game.opp_bowling || []).filter(r => (r.innings_number || 1) === num),
    ],
  }))

  const inn1 = innings[0] || { num: 1, batting: [], bowling: [] }
  const inn2 = innings[1] || { num: 2, batting: [], bowling: [] }
  const hasInn2 = inn2.batting.length > 0 || inn2.bowling.length > 0

  // Determine team names per innings from batting_team if available
  const t1 = (game.innings_totals || {})[inn1.num] || {}
  const t2 = (game.innings_totals || {})[inn2.num] || {}
  // Never fall back to home_team/away_team by innings index — the away team bats
  // first as often as the home team does, so that guess is frequently backwards.
  const inn1Team = t1.batting_team || '1ST INNINGS'
  const inn2Team = t2.batting_team || '2ND INNINGS'

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1300px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
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
          <div className="space-y-4">
            {/* Row 1 — Batting cards */}
            <div className={`grid gap-4 ${hasInn2 ? 'grid-cols-1 lg:grid-cols-2' : 'grid-cols-1'}`}>
              <BattingCard
                label="INNINGS 1"
                teamName={inn1Team}
                batting={inn1.batting}
                inningsTotal={t1}
                fmtName={fmtName}
                canManage={canManage}
                onClaim={setClaimTarget}
              />
              {hasInn2 && (
                <BattingCard
                  label="INNINGS 2"
                  teamName={inn2Team}
                  batting={inn2.batting}
                  inningsTotal={t2}
                  fmtName={fmtName}
                  canManage={canManage}
                  onClaim={setClaimTarget}
                />
              )}
            </div>

            {/* Row 2 — Bowling cards */}
            {(inn1.bowling.length > 0 || inn2.bowling.length > 0) && (
              <div className={`grid gap-4 ${hasInn2 && inn2.bowling.length > 0 ? 'grid-cols-1 lg:grid-cols-2' : 'grid-cols-1'}`}>
                {inn1.bowling.length > 0 && (
                  <BowlingCard label="INNINGS 1" teamName={inn2Team} bowling={inn1.bowling} fmtName={fmtName} canManage={canManage} onClaim={setClaimTarget} />
                )}
                {hasInn2 && inn2.bowling.length > 0 && (
                  <BowlingCard label="INNINGS 2" teamName={inn1Team} bowling={inn2.bowling} fmtName={fmtName} canManage={canManage} onClaim={setClaimTarget} />
                )}
              </div>
            )}
          </div>
        )}

        <FallOfWicketsSection fow={game.fall_of_wickets ?? []} fmtName={fmtName} />
        <PartnershipsSection partnerships={game.partnerships ?? []} fmtName={fmtName} />
      </main>

      {claimTarget && (
        <ClaimFillInModal
          row={claimTarget}
          existingPlayers={existingPlayers}
          onClose={() => setClaimTarget(null)}
          onSaved={() => {
            setClaimTarget(null)
            api.getScorecard(gameId).then(setGame).catch(() => {})
          }}
        />
      )}
    </div>
  )
}
