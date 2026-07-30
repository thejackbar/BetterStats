import { useEffect, useMemo, useState } from 'react'
import { api } from '../../../../lib/api'

// Presentation mode: the count on a projector, revealed one round at a time,
// exactly how a club reads a Brownlow-style vote on awards night.
//
// Forced dark. The stage sets both its own --pb-* dark tokens AND `color`, so a
// club running the admin app in light mode still gets a dark stage with legible
// text (colour is inherited, so it must be re-declared here).
const STAGE_TOKENS = {
  '--pb-bg': '#07090f',
  '--pb-surface': '#0d1117',
  '--pb-surface2': '#161b27',
  '--pb-hairline': '#1d2331',
  '--pb-hairline2': '#262d3d',
  '--pb-text': '#e6e8ef',
  '--pb-dim': '#8a90a2',
  '--pb-faint': '#5b6072',
  '--pb-faintest': '#3a3f50',
  color: '#e6e8ef',
  background: '#07090f',
}

export default function AwardsNight({ board, onExit }) {
  const counted = useMemo(() => board.rounds.filter((r) => r.counted), [board])
  const [upto, setUpto] = useState(1)
  const [snapshot, setSnapshot] = useState(null)

  // Each reveal re-counts the season "as at" that round — the same
  // through_round replay the leaderboard already supports, so the numbers on
  // screen are always the real count, never an interpolation.
  useEffect(() => {
    let alive = true
    const round = counted[upto - 1]
    if (!round) return
    api.votesLeaderboard({ year: board.year, grade_id: board.grade_id || undefined, through_round: round.key })
      .then((d) => alive && setSnapshot(d)).catch(() => {})
    return () => { alive = false }
  }, [upto, counted, board.year, board.grade_id])

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'ArrowRight' || e.key === ' ') { e.preventDefault(); setUpto((n) => Math.min(counted.length, n + 1)) }
      if (e.key === 'ArrowLeft') setUpto((n) => Math.max(1, n - 1))
      if (e.key === 'Escape') onExit()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [counted.length, onExit])

  const standings = (snapshot?.standings || board.standings).slice(0, 9)
  const leader = standings[0]
  const round = counted[upto - 1]
  const margin = standings[1] ? leader.points - standings[1].points : leader?.points

  return (
    <div className="fixed inset-0 z-50 flex flex-col" style={STAGE_TOKENS}>
      <div className="flex items-center justify-between px-7 py-5">
        <div className="flex items-center gap-3">
          <span className="w-[30px] h-[30px] rounded-lg flex items-center justify-center text-xs font-bold"
            style={{ background: 'var(--pb-accent)', color: '#07090f' }}>
            {(board.club_short || 'CC')}
          </span>
          <div>
            <div className="text-[15px] font-bold leading-tight">{board.club_name || 'Best Player'}</div>
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mt-0.5">
              BEST PLAYER {board.season_label} · {(board.grade_name || 'WHOLE CLUB').toUpperCase()}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3.5">
          <div className="flex items-center gap-1.5">
            {counted.map((r, i) => (
              <span key={r.key} className="w-[7px] h-[7px] rounded-full"
                style={{ background: i < upto ? 'var(--pb-amber)' : 'var(--pb-hairline)' }} />
            ))}
          </div>
          <div className="font-mono text-[11px] text-pb-dim">
            {round?.label?.toUpperCase()} OF {counted.length}
          </div>
          <button onClick={() => setUpto((n) => Math.min(counted.length, n + 1))}
            disabled={upto >= counted.length}
            className="px-4 py-2 rounded-[9px] text-[13px] font-semibold disabled:opacity-40"
            style={{ background: 'var(--pb-amber)', color: '#07090f' }}>
            Reveal next round
          </button>
          <button onClick={onExit} className="text-[13px] text-pb-faint hover:text-pb-text">Exit</button>
        </div>
      </div>

      <div className="flex-1 flex gap-8 px-7 pb-7 min-h-0">
        <div className="w-[430px] shrink-0 flex flex-col justify-center gap-6">
          <div>
            <div className="font-mono text-[11px] tracking-wide4" style={{ color: 'var(--pb-amber)' }}>LEADING THE COUNT</div>
            <div className="text-[64px] font-extrabold leading-none tracking-tighter mt-2.5">{leader?.name}</div>
            <div className="flex items-baseline gap-3.5 mt-4">
              <div className="text-[84px] font-extrabold leading-none tabular-nums" style={{ color: 'var(--pb-amber)' }}>
                {leader?.points}
              </div>
              <div>
                <div className="font-mono text-[11px] tracking-wide3 text-pb-faint">POINTS</div>
                <div className="text-sm text-pb-dim mt-1">
                  {margin > 0 ? `+${margin} clear` : 'level at the top'} · {leader?.counts?.[0] ?? 0} threes
                </div>
              </div>
            </div>
          </div>
          <div className="flex gap-px rounded-[10px] overflow-hidden" style={{ background: 'var(--pb-hairline)' }}>
            {[
              { label: 'THREES', value: leader?.counts?.[0] ?? 0 },
              { label: 'ROUNDS VOTED', value: leader?.rounds ?? 0 },
              { label: 'MARGIN', value: margin > 0 ? `+${margin}` : '=' },
            ].map((s) => (
              <div key={s.label} className="flex-1 px-3.5 py-3" style={{ background: 'var(--pb-surface)' }}>
                <div className="font-mono text-[9.5px] tracking-wide2 text-pb-faint">{s.label}</div>
                <div className="text-xl font-bold tabular-nums mt-1">{s.value}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="flex-1 min-w-0 flex flex-col">
          <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest px-1 pb-2.5">
            THE COUNT · AFTER {round?.label?.toUpperCase()}
          </div>
          <div className="flex-1 flex flex-col gap-1.5 overflow-hidden">
            {standings.map((s, i) => (
              <div key={s.player_id} className="flex items-center gap-4 px-4 py-2.5 rounded-[11px]"
                style={{
                  background: i === 0
                    ? 'linear-gradient(90deg, color-mix(in srgb, var(--pb-amber) 14%, transparent) 0%, transparent 100%)'
                    : i < 3 ? 'var(--pb-surface)' : 'transparent',
                  border: `1px solid ${i === 0 ? 'color-mix(in srgb, var(--pb-amber) 35%, transparent)' : i < 3 ? 'var(--pb-hairline)' : 'transparent'}`,
                }}>
                <div className="font-mono text-[15px] font-bold w-[26px]"
                  style={{ color: i === 0 ? 'var(--pb-amber)' : 'var(--pb-faintest)' }}>{i + 1}</div>
                <div className="flex-1 min-w-0 font-semibold truncate"
                  style={{ fontSize: i === 0 ? 22 : i < 3 ? 19 : 17 }}>{s.name}</div>
                {s.round_gain > 0 && (
                  <span className="font-mono text-[11px] px-1.5 py-0.5 rounded-full"
                    style={{ background: 'color-mix(in srgb, var(--pb-positive) 14%, transparent)', color: 'var(--pb-positive)' }}>
                    +{s.round_gain}
                  </span>
                )}
                <div className="font-extrabold tabular-nums w-[62px] text-right"
                  style={{ fontSize: i === 0 ? 26 : 21, color: i === 0 ? 'var(--pb-amber)' : i < 3 ? 'var(--pb-text)' : 'var(--pb-dim)' }}>
                  {s.points}
                </div>
              </div>
            ))}
          </div>
          <div className="font-mono text-[10px] text-pb-faintest pt-3">
            → / SPACE reveal next · ← back · ESC exit
          </div>
        </div>
      </div>
    </div>
  )
}
