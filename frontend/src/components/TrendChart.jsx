import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer
} from 'recharts'

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-navy-800 border border-navy-600 rounded-lg px-3 py-2 text-sm">
      <p className="text-slate-400 text-xs mb-1">{label}</p>
      <p className="text-white font-bold stat-number">{payload[0].value} runs</p>
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
    return <p className="text-slate-500 text-sm py-6 text-center">Not enough data.</p>
  }

  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={data} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1a2540" />
        <XAxis dataKey="label" tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} />
        <Tooltip content={<CustomTooltip />} />
        <ReferenceLine y={avg} stroke="#16c784" strokeDasharray="4 4" strokeOpacity={0.5} />
        <Line
          type="monotone"
          dataKey="runs"
          stroke="#16c784"
          strokeWidth={2}
          dot={{ fill: '#16c784', r: 3, strokeWidth: 0 }}
          activeDot={{ r: 5, fill: '#4dd9a0' }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
