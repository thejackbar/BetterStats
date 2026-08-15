import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useAuth } from '../../contexts/AuthContext'
import { useToast } from '../../contexts/ToastContext'
import AdminLayout from '../../components/admin/AdminLayout'
import { Pill } from '../../components/admin/crm/ui'

const CARD = 'pb-card p-3'

function Kpi({ label, value }) {
  return (
    <div className={CARD}>
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">{label}</div>
      <div className="font-display font-bold text-xl text-pb-text">{value}</div>
    </div>
  )
}

function KpiRow({ title, data }) {
  if (!data) return null
  return (
    <div className="mb-4">
      <h3 className="font-display font-bold text-[13px] mb-2">{title}</h3>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
        <Kpi label="Calls" value={data.calls} />
        <Kpi label="Clubs contacted" value={data.clubs_contacted} />
        <Kpi label="Positive" value={data.positive_conversations} />
        <Kpi label="Callbacks" value={data.callbacks_created} />
        <Kpi label="Trials started" value={data.trials_started} />
      </div>
    </div>
  )
}

const FUNNEL_COLS = [
  { key: 'assigned', label: 'Assigned' },
  { key: 'attempted', label: 'Attempted', rate: 'attempt_rate' },
  { key: 'contacted', label: 'Contacted', rate: 'contact_rate' },
  { key: 'engaged', label: 'Engaged', rate: 'engaged_rate' },
  { key: 'trial', label: 'Trial', rate: 'trial_rate' },
  { key: 'won', label: 'Subscriber', rate: 'win_rate' },
]

function FunnelTable({ rows }) {
  if (rows.length === 0) {
    return <p className="text-[12px] text-pb-faintest">No clubs assigned yet.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="text-pb-faint border-b border-pb-hairline">
            <th className="text-left py-1.5 pr-2">Salesperson</th>
            {FUNNEL_COLS.map(c => <th key={c.key} className="text-right py-1.5 px-2 whitespace-nowrap">{c.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.owner_user_id} className="border-b border-pb-hairline/50">
              <td className="py-1.5 pr-2 text-pb-text font-medium">{r.owner_name}</td>
              {FUNNEL_COLS.map(c => (
                <td key={c.key} className="text-right py-1.5 px-2 whitespace-nowrap">
                  <span className="text-pb-text">{r[c.key]}</span>
                  {c.rate && <span className="text-pb-faintest ml-1">({r[c.rate]}%)</span>}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function SalesPerformance() {
  const { user } = useAuth()
  const toast = useToast()
  const isSuper = user?.role === 'super_admin'
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    api.salesWorkspacePerformance().then(setData)
      .catch(() => toast?.error('Could not load performance')).finally(() => setLoading(false))
  }, [toast])

  useEffect(() => { load() }, [load])

  const content = (
    <div className="max-w-4xl">
      <div className="mb-4">
        <h1 className="font-display font-bold text-2xl text-pb-text">Sales Performance</h1>
        <p className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mt-0.5">
          {isSuper ? 'Every salesperson' : 'Your own numbers'}
        </p>
      </div>

      {loading || !data ? (
        <p className="text-[12px] text-pb-faintest">Loading…</p>
      ) : (
        <>
          <KpiRow title="Today" data={data.summary?.today} />
          <KpiRow title="This week" data={data.summary?.week} />

          <div className={CARD}>
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-display font-bold text-[13px]">Conversion funnel</h3>
              <Pill tone="faint">assigned clubs, all time</Pill>
            </div>
            <FunnelTable rows={data.by_rep || []} />
          </div>
        </>
      )}
    </div>
  )

  if (!isSuper) {
    return (
      <div className="min-h-screen bg-pb-bg">
        <header className="flex items-center justify-between px-4 py-3 border-b pb-hairline-b">
          <span className="font-display font-bold text-pb-text">BetterCricket Sales</span>
          <Link to="/admin/super/crm/workspace" className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors border pb-hairline rounded px-3 py-1.5">
            WORKSPACE
          </Link>
        </header>
        <main className="p-4">{content}</main>
      </div>
    )
  }
  return <AdminLayout>{content}</AdminLayout>
}
