import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer } from 'recharts'

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-navy-800 border border-navy-600 rounded-lg px-3 py-2 text-sm">
      <p className="text-slate-400 text-xs mb-1">{label}</p>
      <p className="text-white font-bold stat-number">{payload[0].value} runs</p>
    </div>
  )
}

const barColor = (runs) => {
  if (runs >= 100) return '#f59e0b'
  if (runs >= 50) return '#16c784'
  return '#243352'
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
    return <p className="text-slate-500 text-sm py-6 text-center">No innings data.</p>
  }

  return (
    <ResponsiveContainer width="100%" height={160}>
      <BarChart data={data} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1a2540" vertical={false} />
        <XAxis dataKey="match" tick={{ fill: '#64748b', fontSize: 9 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: '#1a2540' }} />
        <Bar dataKey="runs" radius={[3, 3, 0, 0]}>
          {data.map((entry, i) => (
            <Cell key={i} fill={barColor(entry.runs)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
