import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer } from 'recharts'

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-pb-surface border pb-hairline rounded px-3 py-2 text-sm">
      <p className="font-mono text-[10px] text-pb-faint mb-1">{label}</p>
      <p className="font-mono font-bold text-pb-text">{payload[0].value} runs</p>
    </div>
  )
}

const barColor = (runs) => {
  if (runs >= 100) return 'var(--pb-chart-milestone, #f5b542)'
  if (runs >= 50) return 'var(--pb-accent, #16c784)'
  return 'var(--pb-faintest, #3a3f50)'
}

export default function RunsChart({ innings = [] }) {
  const data = innings.slice(0, 15).reverse().map((inn, i) => ({
    match: inn.played_at
      ? new Date(inn.played_at).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })
      : `M${i + 1}`,
    runs: inn.runs ?? 0,
    notOut: inn.not_out,
  }))

  if (data.length === 0) {
    return <p className="font-mono text-[11px] text-pb-faint py-6 text-center">No innings data.</p>
  }

  return (
    <ResponsiveContainer width="100%" height={160}>
      <BarChart data={data} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" vertical={false} />
        <XAxis dataKey="match" tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 9 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: 'var(--pb-surface2, #1a2540)' }} />
        <Bar dataKey="runs" radius={[3, 3, 0, 0]}>
          {data.map((entry, i) => (
            <Cell key={i} fill={barColor(entry.runs)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
