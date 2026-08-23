import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useAuth } from '../../contexts/AuthContext'
import { useToast } from '../../contexts/ToastContext'
import AdminLayout from '../../components/admin/AdminLayout'
import { Btn, Pill } from '../../components/admin/crm/ui'
import { outcomeLabel } from '../../lib/salesOutcomes'

const CARD = 'pb-card p-3'
const BUCKETS = [
  { key: 'overdue', label: 'Overdue', tone: 'red' },
  { key: 'today', label: 'Today', tone: 'amber' },
  { key: 'upcoming', label: 'Upcoming', tone: 'faint' },
]

function FollowUpRow({ f, onDone }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-pb-hairline/50 py-2 text-[12px]">
      <div className="min-w-0">
        <Link to={`/admin/super/crm/workspace?club=${f.deal_id}`} className="text-pb-text hover:underline font-medium">
          {f.club_name || 'Untitled'}
        </Link>
        {f.contact_name && <span className="text-pb-faint ml-1.5">{f.contact_name}</span>}
        {f.owner_name && <span className="text-pb-faintest ml-1.5">· {f.owner_name}</span>}
        {f.outcome && <div className="text-pb-faintest text-[10.5px] mt-0.5">{outcomeLabel(f.outcome)}{f.notes ? `, ${f.notes}` : ''}</div>}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <span className="text-pb-faintest text-[10.5px] whitespace-nowrap">
          {f.due_at ? new Date(f.due_at).toLocaleString('en-AU') : ''}
        </span>
        <Btn sm variant="subtle" onClick={() => onDone(f.activity_id)}>Mark done</Btn>
      </div>
    </div>
  )
}

export default function SalesFollowUps() {
  const { user } = useAuth()
  const toast = useToast()
  const isSuper = user?.role === 'super_admin'
  const [followUps, setFollowUps] = useState([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    api.salesWorkspaceFollowUps().then((d) => setFollowUps(d.follow_ups || []))
      .catch(() => toast?.error('Could not load follow-ups')).finally(() => setLoading(false))
  }, [toast])

  useEffect(() => { load() }, [load])

  const markDone = async (activityId) => {
    try {
      await api.salesWorkspaceCompleteFollowUp(activityId)
      setFollowUps(fs => fs.filter(f => f.activity_id !== activityId))
    } catch (err) {
      toast?.error(err.message)
    }
  }

  const grouped = useMemo(() => {
    const by = { overdue: [], today: [], upcoming: [] }
    for (const f of followUps) (by[f.bucket] || by.upcoming).push(f)
    return by
  }, [followUps])

  const content = (
    <div className="max-w-4xl">
      <div className="mb-4">
        <h1 className="font-display font-bold text-2xl text-pb-text">{isSuper ? 'All Follow-ups' : 'My Follow-ups'}</h1>
        <p className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mt-0.5">
          Callbacks and requested follow-ups from logged calls
        </p>
      </div>

      {loading ? (
        <p className="text-[12px] text-pb-faintest">Loading…</p>
      ) : followUps.length === 0 ? (
        <div className={CARD}><p className="text-[12px] text-pb-faintest">Nothing due. Every follow-up is caught up.</p></div>
      ) : (
        <div className="space-y-3">
          {BUCKETS.map(b => grouped[b.key].length > 0 && (
            <div key={b.key} className={CARD}>
              <div className="flex items-center gap-2 mb-2">
                <h3 className="font-display font-bold text-[13px]">{b.label}</h3>
                <Pill tone={b.tone}>{grouped[b.key].length}</Pill>
              </div>
              {grouped[b.key].map(f => <FollowUpRow key={f.activity_id} f={f} onDone={markDone} />)}
            </div>
          ))}
        </div>
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
