import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useAuth } from '../../contexts/AuthContext'
import { useToast } from '../../contexts/ToastContext'
import AdminLayout from '../../components/admin/AdminLayout'
import { Pill } from '../../components/admin/crm/ui'

const CARD = 'pb-card p-3'
const TH = 'text-right py-1.5 px-2 whitespace-nowrap'
const TD = 'text-right py-1.5 px-2 whitespace-nowrap'

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
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
        <Kpi label="Contacts" value={data.contacts} />
        <Kpi label="Calls" value={data.calls} />
        <Kpi label="Emails" value={data.emails} />
        <Kpi label="Clubs contacted" value={data.clubs_contacted} />
        <Kpi label="Positive" value={data.positive_conversations} />
        <Kpi label="Callbacks" value={data.callbacks_created} />
        <Kpi label="Trials started" value={data.trials_started} />
      </div>
    </div>
  )
}

// Both figures per stage: every deal there, and the ones the rep has actually
// reached out to. A muted 0 keeps a busy row readable — a zero is almost
// always noise on a table this wide.
function Cell({ total, contacted }) {
  if (!total) return <span className="text-pb-faintest">0</span>
  return (
    <>
      <span className="text-pb-text">{total}</span>
      <span className="text-pb-faintest ml-1">({contacted})</span>
    </>
  )
}

function StageTable({ rows, columns, totals }) {
  if (rows.length === 0) {
    return <p className="text-[12px] text-pb-faintest">No clubs in the pipeline yet.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="text-pb-faint border-b border-pb-hairline">
            <th className="text-left py-1.5 pr-2">Salesperson</th>
            <th className={TH} title="Assigned to them and not yet contacted">To contact</th>
            {columns.map(c => <th key={c.key} className={TH}>{c.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.owner_user_id} className="border-b border-pb-hairline/50">
              <td className="py-1.5 pr-2 text-pb-text font-medium">
                {r.owner_name}
                {r.unassigned && <span className="text-pb-faintest font-normal ml-1">(pool)</span>}
              </td>
              <td className={TD}>
                <span className={r.to_contact ? 'text-pb-text' : 'text-pb-faintest'}>{r.to_contact}</span>
              </td>
              {columns.map(c => (
                <td key={c.key} className={TD}><Cell {...r.stages[c.key]} /></td>
              ))}
            </tr>
          ))}
        </tbody>
        {totals && (
          <tfoot>
            <tr className="border-t border-pb-hairline text-pb-text font-medium">
              <td className="py-1.5 pr-2">All clubs</td>
              <td className={TD}>{totals.to_contact}</td>
              {columns.map(c => (
                <td key={c.key} className={TD}><Cell {...totals.stages[c.key]} /></td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  )
}

const ACTIVITY_COLS = [
  { key: 'contacts', label: 'Contacts' },
  { key: 'calls', label: 'Calls' },
  { key: 'emails', label: 'Emails' },
  { key: 'clubs_contacted', label: 'Clubs' },
]

function ActivityTable({ rows, totals }) {
  if (rows.length === 0) {
    return <p className="text-[12px] text-pb-faintest">Nobody has made contact this week yet.</p>
  }
  const cell = (row, window, key) => (
    <td key={`${window}-${key}`} className={TD}>
      <span className={row[window][key] ? 'text-pb-text' : 'text-pb-faintest'}>{row[window][key]}</span>
    </td>
  )
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="text-pb-faint">
            <th />
            <th className="text-center py-1 px-2 border-b border-pb-hairline" colSpan={ACTIVITY_COLS.length}>Today</th>
            <th className="text-center py-1 px-2 border-b border-pb-hairline" colSpan={ACTIVITY_COLS.length}>This week</th>
          </tr>
          <tr className="text-pb-faint border-b border-pb-hairline">
            <th className="text-left py-1.5 pr-2">Salesperson</th>
            {ACTIVITY_COLS.map(c => <th key={`t-${c.key}`} className={TH}>{c.label}</th>)}
            {ACTIVITY_COLS.map(c => <th key={`w-${c.key}`} className={TH}>{c.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.user_id || r.name} className="border-b border-pb-hairline/50">
              <td className="py-1.5 pr-2 text-pb-text font-medium">{r.name}</td>
              {ACTIVITY_COLS.map(c => cell(r, 'today', c.key))}
              {ACTIVITY_COLS.map(c => cell(r, 'week', c.key))}
            </tr>
          ))}
        </tbody>
        {totals && (
          <tfoot>
            <tr className="border-t border-pb-hairline text-pb-text font-medium">
              <td className="py-1.5 pr-2">Everyone</td>
              {ACTIVITY_COLS.map(c => <td key={`tt-${c.key}`} className={TD}>{totals.today[c.key]}</td>)}
              {ACTIVITY_COLS.map(c => <td key={`wt-${c.key}`} className={TD}>{totals.week[c.key]}</td>)}
            </tr>
          </tfoot>
        )}
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
    <div className="max-w-5xl">
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

          <div className={`${CARD} mb-4`}>
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-display font-bold text-[13px]">Contact activity</h3>
              <Pill tone="faint">who made contact, and when</Pill>
            </div>
            <ActivityTable rows={data.activity || []} totals={data.summary} />
            <p className="text-[11px] text-pb-faintest mt-2">
              A contact is a logged call, a follow-up recorded, or an email sent. Days run to
              Perth time and the week starts Monday.
            </p>
          </div>

          <div className={CARD}>
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-display font-bold text-[13px]">Pipeline by salesperson</h3>
              <Pill tone="faint">every club, all time</Pill>
            </div>
            <StageTable
              rows={data.by_rep || []}
              columns={data.stage_columns || []}
              totals={data.totals}
            />
            <p className="text-[11px] text-pb-faintest mt-2">
              To contact = assigned to them and not yet contacted, so it is what is left before
              they need more clubs. Each stage shows every club there, with the number they have
              made contact with in brackets.
            </p>
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
