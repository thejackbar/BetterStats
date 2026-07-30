import { useMemo } from 'react'

// Cumulative-points progression — the Brownlow "race". Deliberately an inline
// SVG rather than Recharts: five short polylines, no tooltip, no axis library.
// series: [{ player_id, name, colour, points: number[] }] aligned to rounds[].
export default function RaceChart({ series = [], rounds = [], height = 190 }) {
  const W = 368, H = height, X0 = 34, X1 = W - 12, Y0 = H - 22, Y1 = 12
  const max = useMemo(
    () => Math.max(8, ...series.flatMap((s) => s.points)),
    [series],
  )
  const n = Math.max(1, rounds.length - 1)
  const px = (i) => X0 + (i / n) * (X1 - X0)
  const py = (v) => Y0 - (v / max) * (Y0 - Y1)
  const ticks = [0, Math.round(max / 3), Math.round((max / 3) * 2), max]

  if (!series.length || !rounds.length) {
    return <div className="py-10 text-center text-pb-faintest text-xs">Not enough counted rounds yet.</div>
  }

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto block">
      {ticks.map((v) => (
        <g key={v}>
          <line x1={X0} x2={X1} y1={py(v)} y2={py(v)} style={{ stroke: 'var(--pb-hairline)' }} strokeWidth={1} />
          <text x={0} y={py(v) + 3} fontSize={9} fontFamily="JetBrains Mono, monospace" style={{ fill: 'var(--pb-faintest)' }}>{v}</text>
        </g>
      ))}
      {series.map((s, i) => (
        <polyline key={s.player_id} fill="none" stroke={s.colour} strokeWidth={i === 0 ? 2.4 : 1.6}
          strokeLinejoin="round" strokeLinecap="round"
          points={s.points.map((v, j) => `${px(j)},${py(v)}`).join(' ')} />
      ))}
      {series.map((s) => (
        s.points.length > 0 &&
        <circle key={`d-${s.player_id}`} r={3.5} fill={s.colour}
          cx={px(s.points.length - 1)} cy={py(s.points[s.points.length - 1])} />
      ))}
      {rounds.map((r, i) => (
        <text key={r.key} x={px(i)} y={H - 4} fontSize={9} textAnchor="middle"
          fontFamily="JetBrains Mono, monospace" style={{ fill: 'var(--pb-faintest)' }}>{r.short || r.label}</text>
      ))}
    </svg>
  )
}
