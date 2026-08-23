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

// Every figure on this screen opens the clubs behind it. A zero has nothing
// to open, so it stays plain text rather than a button that leads to an empty
// list — and it keeps a wide table readable.
function Figure({ value, onOpen, active, title, muted }) {
  if (!value) return <span className="text-pb-faintest">0</span>
  const base = muted ? 'text-pb-faintest' : 'text-pb-text'
  return (
    <button
      type="button"
      onClick={onOpen}
      title={title}
      className={`${base} cursor-pointer underline decoration-dotted decoration-pb-faint
        underline-offset-2 hover:decoration-solid hover:text-pb-accent-ink rounded-sm
        ${active ? 'text-pb-accent-ink decoration-solid' : ''}`}
    >
      {value}
    </button>
  )
}

function StageCell({ stage, onOpen, activeKey, cellKey }) {
  if (!stage.total) return <span className="text-pb-faintest">0</span>
  return (
    <>
      <Figure value={stage.total} active={activeKey === cellKey}
              title="Every club in this stage" onOpen={() => onOpen(false)} />
      <span className="text-pb-faintest ml-1">
        (<Figure value={stage.contacted} muted active={activeKey === `${cellKey}:c`}
                 title="The ones this rep has made contact with"
                 onOpen={() => onOpen(true)} />)
      </span>
    </>
  )
}

function StageTable({ rows, columns, totals, onOpen, activeKey }) {
  if (rows.length === 0) {
    return <p className="text-[12px] text-pb-faintest">No clubs in the pipeline yet.</p>
  }
  const body = (r, ownerKey, label) => (
    <>
      <td className="py-1.5 pr-2 text-pb-text font-medium">
        {label}
        {r.unassigned && <span className="text-pb-faintest font-normal ml-1">(pool)</span>}
      </td>
      <td className={TD}>
        <Figure value={r.to_contact} active={activeKey === `${ownerKey}|to_contact`}
                title="Assigned and not yet contacted"
                onOpen={() => onOpen({ owner: ownerKey, cell: 'to_contact', label,
                                       what: 'still to contact' })} />
      </td>
      {columns.map(c => (
        <td key={c.key} className={TD}>
          <StageCell
            stage={r.stages[c.key]} cellKey={`${ownerKey}|${c.key}`} activeKey={activeKey}
            onOpen={(contactedOnly) => onOpen({
              owner: ownerKey, cell: c.key, contacted_only: contactedOnly, label,
              what: contactedOnly ? `${c.label}, contacted` : c.label,
            })}
          />
        </td>
      ))}
    </>
  )
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
              {body(r, r.owner_user_id, r.owner_name)}
            </tr>
          ))}
        </tbody>
        {totals && (
          <tfoot>
            <tr className="border-t border-pb-hairline text-pb-text font-medium">
              {body({ ...totals, unassigned: false }, 'all', 'All clubs')}
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
const WINDOW_LABEL = { today: 'today', week: 'this week' }

function ActivityTable({ rows, totals, onOpen, activeKey }) {
  if (rows.length === 0) {
    return <p className="text-[12px] text-pb-faintest">Nobody has made contact this week yet.</p>
  }
  const cell = (row, userKey, name, window, col) => (
    <td key={`${window}-${col.key}`} className={TD}>
      <Figure
        value={row[window][col.key]}
        active={activeKey === `${userKey}|${window}|${col.key}`}
        onOpen={() => onOpen({
          user_id: userKey, window, metric: col.key, label: name,
          what: `${col.label.toLowerCase()} ${WINDOW_LABEL[window]}`,
        })}
      />
    </td>
  )
  const line = (row, userKey, name) => (
    <>
      <td className="py-1.5 pr-2 text-pb-text font-medium">{name}</td>
      {ACTIVITY_COLS.map(c => cell(row, userKey, name, 'today', c))}
      {ACTIVITY_COLS.map(c => cell(row, userKey, name, 'week', c))}
    </>
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
              {line(r, r.user_id || 'everyone', r.name)}
            </tr>
          ))}
        </tbody>
        {totals && (
          <tfoot>
            <tr className="border-t border-pb-hairline text-pb-text font-medium">
              {line(totals, 'everyone', 'Everyone')}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  )
}

// The clubs behind whichever figure was clicked. Rendered under the table it
// came from rather than in a dialog, so the cell stays on screen and a run of
// cells can be compared without reopening anything.
function Drilldown({ open, onClose }) {
  if (!open) return null
  const { title, loading, error, data } = open
  return (
    <div className="mt-3 border-t border-pb-hairline pt-3">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div>
          <h4 className="font-display font-bold text-[12px] text-pb-text">{title}</h4>
          {data && (
            <p className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mt-0.5">
              {data.club_count} club{data.club_count === 1 ? '' : 's'}
              {data.total !== data.club_count && ` · ${data.total} in total`}
            </p>
          )}
        </div>
        <button type="button" onClick={onClose}
          className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text
                     border pb-hairline rounded px-2 py-1 shrink-0">
          CLOSE
        </button>
      </div>
      {loading && <p className="text-[12px] text-pb-faintest">Loading…</p>}
      {error && <p className="text-[12px] text-pb-red-ink">{error}</p>}
      {data && data.clubs.length === 0 && (
        <p className="text-[12px] text-pb-faintest">No clubs behind this figure.</p>
      )}
      {data && data.clubs.length > 0 && (
        <ul className="max-h-72 overflow-y-auto divide-y divide-pb-hairline/50">
          {data.clubs.map(c => (
            <li key={c.deal_id} className="py-1.5 flex items-center justify-between gap-3">
              <Link
                to={`/admin/super/crm/workspace?club=${c.deal_id}`}
                className="text-[12px] text-pb-text hover:text-pb-accent-ink truncate"
              >
                {c.club_name}
              </Link>
              <span className="font-mono text-[10px] text-pb-faintest whitespace-nowrap">
                {c.state || '—'}
                {c.engagement_score !== null && c.engagement_score !== undefined
                  && ` · ${c.engagement_score}`}
                {c.count > 1 && ` · ×${c.count}`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function SalesPerformance() {
  const { user } = useAuth()
  const toast = useToast()
  const isSuper = user?.role === 'super_admin'
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  // One drill-down at a time, and which panel it belongs under, so clicking a
  // pipeline cell closes an activity one rather than leaving two lists open.
  const [drill, setDrill] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    api.salesWorkspacePerformance().then(setData)
      .catch(() => toast?.error('Could not load performance')).finally(() => setLoading(false))
  }, [toast])

  useEffect(() => { load() }, [load])

  const openCell = useCallback((panel, key, title, params) => {
    setDrill({ panel, key, title, loading: true })
    api.salesWorkspaceDrilldown({ panel, ...params })
      .then(res => setDrill(d => (d && d.key === key
        ? { ...d, loading: false, data: res } : d)))
      .catch(() => setDrill(d => (d && d.key === key
        ? { ...d, loading: false, error: 'Could not load the clubs behind this figure.' } : d)))
  }, [])

  const openActivity = useCallback(({ user_id, window, metric, label, what }) => {
    openCell('activity', `${user_id}|${window}|${metric}`, `${label}, ${what}`,
      { user_id, window, metric })
  }, [openCell])

  const openPipeline = useCallback(({ owner, cell, contacted_only, label, what }) => {
    openCell('pipeline', `${owner}|${cell}${contacted_only ? ':c' : ''}`, `${label}, ${what}`,
      { owner, cell, contacted_only: contacted_only ? 'true' : undefined })
  }, [openCell])

  const panelDrill = (panel) => (drill && drill.panel === panel ? drill : null)
  const activeKey = (panel) => (drill && drill.panel === panel ? drill.key : null)

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
            <ActivityTable rows={data.activity || []} totals={data.summary}
                           onOpen={openActivity} activeKey={activeKey('activity')} />
            <p className="text-[11px] text-pb-faintest mt-2">
              A contact is a logged call, a follow-up recorded, or an email sent. Days run to
              Perth time and the week starts Monday. Click any figure for the clubs behind it.
            </p>
            <Drilldown open={panelDrill('activity')} onClose={() => setDrill(null)} />
          </div>

          <div className={CARD}>
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-display font-bold text-[13px]">
                Deals in pipeline stage by salesperson
              </h3>
              <Pill tone="faint">every club, all time</Pill>
            </div>
            <StageTable
              rows={data.by_rep || []}
              columns={data.stage_columns || []}
              totals={data.totals}
              onOpen={openPipeline}
              activeKey={activeKey('pipeline')}
            />
            <p className="text-[11px] text-pb-faintest mt-2">
              To contact = assigned to them and not yet contacted, so it is what is left before
              they need more clubs. Each stage shows every club there, with the number they have
              made contact with in brackets. Click any figure for the clubs behind it.
            </p>
            <Drilldown open={panelDrill('pipeline')} onClose={() => setDrill(null)} />
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
