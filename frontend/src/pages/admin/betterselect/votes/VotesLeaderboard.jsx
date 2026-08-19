import { useEffect, useMemo, useState } from 'react'
import { useToast } from '../../../../contexts/ToastContext'
import { api } from '../../../../lib/api'
import { Chip } from '../ui'
import PodiumCard from './PodiumCard'
import RaceChart from './RaceChart'
import AwardsNight from './AwardsNight'
import { initialsOf, seasonLabel } from './votesTokens'

const SERIES_COLOURS = ['var(--pb-accent)', 'var(--pb-positive)', 'var(--pb-amber)', '#a855f7', '#06b6d4']

// Form sparkline: one bar per recent round, height scaled to that round's
// points, empty rounds a hairline stub. Keeps the "who's hot" read that a
// points column alone can't give.
function Form({ points = [], max = 3 }) {
  return (
    <div className="flex items-end gap-[3px] h-[22px]">
      {points.map((v, i) => (
        <span key={i} className="w-2 rounded-[2px]"
          style={{
            height: `${4 + (v / max) * 18}px`,
            background: v === 0 ? 'var(--pb-hairline)'
              : `color-mix(in srgb, var(--pb-accent) ${35 + (v / max) * 65}%, transparent)`,
          }} />
      ))}
    </div>
  )
}

export default function VotesLeaderboard({ medalId }) {
  const toast = useToast()
  const [board, setBoard] = useState(null)
  const [year, setYear] = useState(null)
  const [gradeId, setGradeId] = useState('')
  const [throughRound, setThroughRound] = useState('')
  const [presenting, setPresenting] = useState(false)

  useEffect(() => {
    let alive = true
    api.votesLeaderboard({ year, grade_id: gradeId || undefined, through_round: throughRound || undefined, medal_id: medalId || undefined })
      .then((d) => alive && setBoard(d)).catch((e) => toast.error(e.message))
    return () => { alive = false }
  }, [year, gradeId, throughRound, medalId, toast])

  const values = board?.ballot_values || [3, 2, 1]

  const series = useMemo(() => {
    if (!board) return []
    return (board.standings || []).slice(0, 5).map((s, i) => ({
      player_id: s.player_id,
      name: s.name.split(' ').slice(-1)[0],
      colour: SERIES_COLOURS[i],
      points: s.cumulative || [],
    }))
  }, [board])

  if (!board) return <div className="py-16 text-center text-pb-faint text-sm">Counting the votes…</div>

  if (presenting) {
    return <AwardsNight board={board} onExit={() => setPresenting(false)} />
  }

  const top3 = board.standings.slice(0, 3)

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-2.5">
        <div className="font-display font-bold text-[19px]">Best Player Count</div>
        <span className="w-px h-5 bg-pb-hairline2" />
        <div className="flex flex-wrap gap-1.5">
          <Chip label="Whole club" active={!gradeId} onClick={() => setGradeId('')} />
          {(board.grades || []).map((g) => (
            <Chip key={g.id} label={g.name} active={gradeId === g.id} onClick={() => setGradeId(g.id)} />
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2.5">
          <span className="font-mono text-[10.5px] text-pb-faint">AS AT</span>
          <select value={throughRound} onChange={(e) => setThroughRound(e.target.value)}
            className="bg-pb-surface2 border pb-hairline rounded-[9px] h-[34px] px-2.5 text-[13px] focus:outline-none focus:border-pb-accent">
            <option value="">Full season to date</option>
            {board.rounds.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
          </select>
          <select value={board.year} onChange={(e) => { setYear(parseInt(e.target.value, 10)); setThroughRound('') }}
            className="bg-pb-surface2 border pb-hairline rounded-[9px] h-[34px] px-2.5 text-[13px] focus:outline-none focus:border-pb-accent">
            {[board.year, board.year - 1, board.year - 2].map((y) => <option key={y} value={y}>{seasonLabel(y)}</option>)}
          </select>
          <button onClick={() => setPresenting(true)}
            className="h-[34px] px-3.5 rounded-[9px] text-[13px] font-semibold"
            style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>
            Presentation mode
          </button>
        </div>
      </div>

      {board.standings.length === 0 ? (
        <div className="rounded-xl border pb-hairline px-4 py-12 text-center text-pb-faint text-sm">
          No votes counted yet{gradeId ? ' for this grade' : ''}. Ballots appear here as soon as they're cast.
        </div>
      ) : (
        <>
          <div className="flex flex-col md:flex-row gap-3.5">
            {top3.map((s, i) => (
              <PodiumCard key={s.player_id} standing={s} index={i} ballotValues={values} />
            ))}
          </div>

          <div className="flex flex-col xl:flex-row gap-5">
            <div className="flex-1 min-w-0">
              <div className="grid grid-cols-[44px_minmax(190px,1fr)_104px_72px_56px_56px_56px] items-center gap-3
                              px-3.5 py-2.5 font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">
                <div>#</div><div>Player</div><div>Form · last 5</div>
                <div className="text-right">Points</div>
                {values.map((v) => <div key={v} className="text-right">{v}s</div>)}
              </div>
              {board.standings.map((s, i) => (
                <div key={s.player_id}
                  className="grid grid-cols-[44px_minmax(190px,1fr)_104px_72px_56px_56px_56px] items-center gap-3
                             px-3.5 py-3 border-t pb-hairline"
                  style={i < 3 ? { background: 'color-mix(in srgb, var(--pb-amber) 3.5%, transparent)' } : undefined}>
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-[13px] font-semibold"
                      style={{ color: i < 3 ? 'var(--pb-amber)' : 'var(--pb-faint)' }}>
                      {s.tied ? '=' : i + 1}
                    </span>
                    <span className="text-[9px]"
                      style={{ color: !s.movement ? 'var(--pb-faintest)' : s.movement > 0 ? 'var(--pb-positive)' : 'var(--pb-red)' }}>
                      {!s.movement ? '—' : s.movement > 0 ? '▲' : '▼'}
                    </span>
                  </div>
                  <div className="flex items-center gap-2.5 min-w-0">
                    <span className="w-[26px] h-[26px] rounded-full shrink-0 bg-pb-surface2 border pb-hairline2
                                     text-pb-dim font-mono text-[9.5px] font-semibold flex items-center justify-center">
                      {initialsOf(s.name)}
                    </span>
                    <span className="text-sm font-medium flex-1 min-w-0 truncate">{s.name}</span>
                    <span className="font-mono text-[9.5px] text-pb-faintest shrink-0">{s.grade_short || ''}</span>
                  </div>
                  <Form points={s.form || []} max={values[0]} />
                  <div className="text-right text-[17px] font-bold tabular-nums"
                    style={{ color: i === 0 ? 'var(--pb-amber)' : 'var(--pb-text)' }}>{s.points}</div>
                  {s.counts.map((c, j) => (
                    <div key={j} className="text-right font-mono text-[13px]"
                      style={{ color: j === 0 ? 'var(--pb-dim)' : 'var(--pb-faint)' }}>{c || '·'}</div>
                  ))}
                </div>
              ))}
            </div>

            <div className="w-full xl:w-[344px] shrink-0 pb-card px-4 py-4 h-fit">
              <div className="flex items-baseline justify-between">
                <div className="font-display font-bold text-[14.5px]">The race</div>
                <div className="font-mono text-[10px] text-pb-faintest">CUMULATIVE POINTS</div>
              </div>
              <div className="text-xs text-pb-faint mb-2.5">{board.race_caption || 'Top five, round by round.'}</div>
              <RaceChart series={series} rounds={board.rounds.filter((r) => r.counted)} />
              <div className="flex flex-wrap gap-2.5 mt-3">
                {series.map((s) => (
                  <span key={s.player_id} className="inline-flex items-center gap-1.5 text-xs text-pb-dim">
                    <span className="w-2.5 h-[3px] rounded-sm" style={{ background: s.colour }} />{s.name}
                  </span>
                ))}
              </div>

              {board.last_round && (
                <div className="mt-4 pt-3.5 border-t pb-hairline">
                  <div className="text-[13.5px] font-semibold mb-2">
                    {board.last_round.label} · {board.last_round.fixture}
                  </div>
                  {board.last_round.results.map((r) => (
                    <div key={r.player_id} className="flex items-center gap-2.5 py-1.5">
                      <span className="w-[22px] h-[22px] rounded-md flex items-center justify-center
                                       font-mono text-[11px] font-bold bg-pb-accent/15 text-pb-accent">{r.points}</span>
                      <span className="text-[13.5px]">{r.name}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
