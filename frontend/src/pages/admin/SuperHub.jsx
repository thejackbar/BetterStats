import { useState, useEffect } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import { findSection, visibleSectionItems } from '../../lib/superNav'

// A Better HQ section landing page. Reads :sectionKey, lists that section's
// tools as tiles (same visual language as the Platform Overview cards). Badge
// counts + the self-serve flag are fetched here so the tiles match the sidebar.

function ToolTile({ to, name, blurb, badge }) {
  return (
    <Link
      to={to}
      className="block pb-card p-5 border-pb-accent/30 hover:border-pb-accent/50 transition-colors group"
      style={{ background: 'color-mix(in srgb, var(--pb-accent) 6%, transparent)' }}
    >
      <div className="flex items-center justify-between gap-4">
        <span className="font-display font-bold text-lg text-pb-text flex items-center gap-2">
          {name}
          {badge > 0 && (
            <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-amber-500/20 text-amber-300 text-[10px] font-semibold">
              {badge}
            </span>
          )}
        </span>
        <span className="text-2xl group-hover:translate-x-1 transition-transform" style={{ color: 'var(--pb-accent)' }}>→</span>
      </div>
      <div className="text-pb-faint text-sm mt-1">{blurb}</div>
    </Link>
  )
}

export default function SuperHub() {
  const { sectionKey } = useParams()
  const section = findSection(sectionKey)

  const [selfServeEnabled, setSelfServeEnabled] = useState(false)
  const [moduleReqCount, setModuleReqCount] = useState(0)
  const [commsReqCount, setCommsReqCount] = useState(0)

  useEffect(() => {
    let alive = true
    api.superCountModuleRequests()
      .then(d => { if (alive) setModuleReqCount(d?.outstanding || 0) })
      .catch(() => {})
    api.superCountCommsRequests()
      .then(d => { if (alive) setCommsReqCount(d?.total || 0) })
      .catch(() => {})
    api.superGetGeneralSettings()
      .then(s => { if (alive) setSelfServeEnabled(!!s?.self_serve_registration_enabled) })
      .catch(() => {})
    return () => { alive = false }
  }, [])

  // Unknown section key → back to the control room.
  if (!section) return <Navigate to="/admin/super" replace />

  const items = visibleSectionItems(section, { selfServeEnabled })

  // A single-item section is a straight link in the sidebar; if someone lands
  // on its hub directly, send them to the one tool it holds.
  if (items.length === 1) return <Navigate to={items[0].to} replace />

  const badgeFor = (item) => {
    if (item.badge === 'moduleRequests') return moduleReqCount
    if (item.badge === 'commsRequests') return commsReqCount
    return 0
  }

  return (
    <AdminLayout>
      <div className="max-w-4xl">
        <div className="mb-1">
          <Link to="/admin/super" className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">
            ← Better HQ
          </Link>
        </div>
        <h1 className="font-display font-bold text-2xl text-pb-text">{section.label}</h1>
        {section.blurb && <p className="text-pb-faint text-sm mb-5">{section.blurb}</p>}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-4">
          {items.map(item => (
            <ToolTile key={item.to} to={item.to} name={item.label} blurb={item.blurb} badge={badgeFor(item)} />
          ))}
        </div>
      </div>
    </AdminLayout>
  )
}
