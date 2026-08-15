import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useAuth } from '../../contexts/AuthContext'
import { useToast } from '../../contexts/ToastContext'
import AdminLayout from '../../components/admin/AdminLayout'
import { Pill } from '../../components/admin/crm/ui'

// Sales Lists — imported batches of clubs, ready to assign.
//
// A thin provenance/import layer over the SAME crm_deals rows the Sales
// Workspace and Sales Pipeline already manage: importing a list here never
// creates a second record of a club's history, it just remembers which
// clubs came in together and gives each one an open deal so it shows up in
// the workspace queue. Assigning a list's clubs to a rep is done from the
// Sales Workspace itself (filter to this list, select, assign) — this page
// is for browsing what's been imported and where it stands, not a second
// assignment surface.
//
// Importing from Wizard Clubs happens on that page itself (Clubs Searched
// or Selected in the Wizard → "Import to Sales List"), since the club
// picker already lives there.

const CARD = 'pb-card p-3'

const fmtDate = (iso) => {
  if (!iso) return '–'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '–'
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

const SOURCE_LABEL = { wizard_clubs: 'Wizard Clubs', manual: 'Manual' }

function ListRow({ l, active, onClick }) {
  return (
    <button
      type="button" onClick={onClick}
      className={`w-full text-left px-3 py-2.5 border-b border-pb-hairline last:border-0 transition-colors ${
        active ? 'bg-pb-surface2' : 'hover:bg-pb-surface2/60'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[13px] text-pb-text font-medium truncate">{l.name}</span>
        <Pill tone="faint">{l.club_count}</Pill>
      </div>
      <div className="text-[11px] text-pb-faintest mt-0.5">
        {SOURCE_LABEL[l.source_type] || l.source_type} · {fmtDate(l.created_at)}
        {l.created_by_name && <> · {l.created_by_name}</>}
      </div>
      {l.description && <div className="text-[11px] text-pb-faint mt-1 line-clamp-2">{l.description}</div>}
    </button>
  )
}

function DetailPane({ detail, loading }) {
  if (loading) return <p className="text-[12px] text-pb-faintest p-3">Loading…</p>
  if (!detail) return <p className="text-[12px] text-pb-faintest p-3">Pick a list on the left.</p>

  return (
    <div>
      <div className="flex items-start justify-between gap-3 flex-wrap mb-3">
        <div>
          <h2 className="font-display font-bold text-[15px] text-pb-text">{detail.name}</h2>
          <p className="text-[11px] text-pb-faintest mt-0.5">
            {SOURCE_LABEL[detail.source_type] || detail.source_type} · Imported {fmtDate(detail.created_at)}
            {detail.created_by_name && <> by {detail.created_by_name}</>}
          </p>
          {detail.description && <p className="text-[12px] text-pb-faint mt-1">{detail.description}</p>}
        </div>
        <Link
          to={`/admin/super/crm/workspace?list_id=${detail.id}&list_name=${encodeURIComponent(detail.name)}`}
          className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text uppercase border pb-hairline rounded px-3 py-1.5"
        >
          Open in Workspace →
        </Link>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-pb-faint border-b border-pb-hairline">
              <th className="text-left py-1.5 pr-2">Club</th>
              <th className="text-left py-1.5 px-2">Stage</th>
              <th className="text-left py-1.5 px-2">Owner</th>
              <th className="text-right py-1.5 pl-2">Added</th>
            </tr>
          </thead>
          <tbody>
            {(detail.clubs || []).length === 0 && (
              <tr><td colSpan={4} className="py-6 text-center text-pb-faintest">No clubs in this list.</td></tr>
            )}
            {(detail.clubs || []).map(c => (
              <tr key={c.marketing_club_id} className="border-b border-pb-hairline/50">
                <td className="py-1.5 pr-2 text-pb-text font-medium">{c.club_name}</td>
                <td className="py-1.5 px-2 text-pb-faint">{c.stage_name || '–'}</td>
                <td className="py-1.5 px-2 text-pb-faint">{c.owner_name || <span className="text-pb-faintest">Unassigned</span>}</td>
                <td className="py-1.5 pl-2 text-right text-pb-faintest whitespace-nowrap">{fmtDate(c.added_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function SalesLists() {
  const { user } = useAuth()
  const toast = useToast()
  const isSuper = user?.role === 'super_admin'

  const [lists, setLists] = useState([])
  const [loadingLists, setLoadingLists] = useState(true)
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  const loadLists = useCallback(() => {
    setLoadingLists(true)
    api.salesWorkspaceLists().then((d) => {
      const rows = d.lists || []
      setLists(rows)
      if (!selectedId && rows.length > 0) setSelectedId(rows[0].id)
    }).catch(() => toast?.error('Could not load Sales Lists')).finally(() => setLoadingLists(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [toast])

  useEffect(() => { loadLists() }, [loadLists])

  useEffect(() => {
    if (!selectedId) { setDetail(null); return }
    setLoadingDetail(true)
    api.salesWorkspaceList(selectedId).then(setDetail)
      .catch(() => toast?.error('Could not load this list')).finally(() => setLoadingDetail(false))
  }, [selectedId, toast])

  const content = (
    <div className="max-w-5xl">
      <div className="mb-4">
        <h1 className="font-display font-bold text-2xl text-pb-text">Sales Lists</h1>
        <p className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mt-0.5">
          Imported batches of clubs, ready to assign
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[280px_1fr] gap-3">
        <div className={`${CARD} !p-0 overflow-hidden`}>
          {loadingLists ? (
            <p className="text-[12px] text-pb-faintest p-3">Loading…</p>
          ) : lists.length === 0 ? (
            <p className="text-[12px] text-pb-faintest p-3">
              No lists yet. Import one from{' '}
              <Link to="/admin/super/crm/wizard-clubs" className="underline hover:text-pb-text">Clubs Searched or Selected in the Wizard</Link>.
            </p>
          ) : lists.map(l => (
            <ListRow key={l.id} l={l} active={l.id === selectedId} onClick={() => setSelectedId(l.id)} />
          ))}
        </div>
        <div className={CARD}>
          <DetailPane detail={detail} loading={loadingDetail} />
        </div>
      </div>
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
