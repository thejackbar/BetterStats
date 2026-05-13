import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer
} from 'recharts'

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-pb-surface border pb-hairline rounded px-3 py-2 text-sm">
      <p className="font-mono text-[10px] text-pb-faint mb-1">{label}</p>
      <p className="font-mono font-bold text-pb-text">{payload[0].value} runs</p>
    </div>
  )
}

export default function TrendChart({ innings = [] }) {
  const last10 = innings.slice(0, 10).reverse()
  const data = last10.map((inn, i) => ({
    match: i + 1,
    runs: inn.runs ?? 0,
    label: inn.played_at
      ? new Date(inn.played_at).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })
      : `Match ${i + 1}`,
  }))

  const avg = data.length > 0 ? Math.round(data.reduce((s, d) => s + d.runs, 0) / data.length) : 0

  if (data.length === 0) {
    return <p className="font-mono text-[11px] text-pb-faint py-6 text-center">Not enough data.</p>
  }

  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={data} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" />
        <XAxis dataKey="label" tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} />
        <Tooltip content={<CustomTooltip />} />
        <ReferenceLine y={avg} stroke="var(--pb-accent, #16c784)" strokeDasharray="4 4" strokeOpacity={0.5} />
        <Line
          type="monotone"
          dataKey="runs"
          stroke="var(--pb-accent, #16c784)"
          strokeWidth={2}
          dot={{ fill: 'var(--pb-accent, #16c784)', r: 3, strokeWidth: 0 }}
          activeDot={{ r: 5 }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
