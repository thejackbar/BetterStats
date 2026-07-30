import { initialsOf } from './votesTokens'

// Gold / silver / bronze come from the existing token family: amber is
// --pb-amber, silver is --pb-dim, bronze is a single warm hex. No new
// palette is introduced beyond that one bronze value.
const PLACE = [
  { label: '1ST', accent: 'var(--pb-amber)' },
  { label: '2ND', accent: 'var(--pb-dim)' },
  { label: '3RD', accent: '#c98b4a' },
]

export default function PodiumCard({ standing, index, ballotValues = [3, 2, 1] }) {
  const p = PLACE[index] || PLACE[2]
  const move = standing.movement ?? 0
  const border = `color-mix(in srgb, ${p.accent} 32%, transparent)`

  return (
    <div className="flex-1 rounded-[14px] p-[18px] relative overflow-hidden"
      style={{
        background: `linear-gradient(160deg, color-mix(in srgb, ${p.accent} 9%, var(--pb-surface)) 0%, var(--pb-surface) 70%)`,
        border: `1px solid ${border}`,
      }}>
      <div className="flex items-center justify-between">
        <div className="font-mono text-[11px] font-bold tracking-wide3" style={{ color: p.accent }}>{p.label}</div>
        <div className="font-mono text-[11px]" style={{ color: move === 0 ? 'var(--pb-faintest)' : move > 0 ? 'var(--pb-positive)' : 'var(--pb-red)' }}>
          {move === 0 ? '—' : `${move > 0 ? '▲' : '▼'} ${Math.abs(move)}`}
        </div>
      </div>

      <div className="flex items-end gap-3 mt-3.5">
        <span className="w-11 h-11 rounded-full flex items-center justify-center shrink-0
                         bg-pb-surface2 font-mono text-sm font-bold"
          style={{ border: `1.5px solid ${border}`, color: p.accent }}>
          {initialsOf(standing.name)}
        </span>
        <div className="min-w-0">
          <div className="text-[19px] font-bold tracking-tight truncate">{standing.name}</div>
          <div className="text-xs text-pb-faint">{standing.grade || 'Club'}</div>
        </div>
        <div className="ml-auto text-right">
          <div className="text-[38px] font-extrabold leading-none tabular-nums" style={{ color: p.accent }}>
            {standing.points}
          </div>
          <div className="font-mono text-[9.5px] tracking-wide2 text-pb-faint mt-1">POINTS</div>
        </div>
      </div>

      <div className="flex gap-3.5 mt-4 pt-3.5" style={{ borderTop: `1px solid ${border}` }}>
        {ballotValues.map((v, i) => (
          <div key={v}>
            <div className="font-mono text-[9.5px] tracking-wide2 text-pb-faint">{v}s</div>
            <div className="text-[15px] font-semibold tabular-nums mt-0.5">{standing.counts?.[i] ?? 0}</div>
          </div>
        ))}
        <div>
          <div className="font-mono text-[9.5px] tracking-wide2 text-pb-faint">RAW</div>
          <div className="text-[15px] font-semibold tabular-nums mt-0.5">{standing.raw}</div>
        </div>
      </div>
    </div>
  )
}
