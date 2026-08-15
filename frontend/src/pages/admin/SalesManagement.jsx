import { Link } from 'react-router-dom'
import AdminLayout from '../../components/admin/AdminLayout'
import { SALES_MANAGEMENT_ITEMS } from '../../lib/superNav'

// Landing page behind the CRM hub's single "Sales Management" tile — the
// seven sales tools (Workspace, Lists, Follow-ups, Performance, Pipeline,
// Targets, Automation) used to each be their own hub tile; collapsed here so
// the CRM hub reads as one thing rather than a wall of "Sales *" entries.
// Same tile look as SuperHub.jsx's ToolTile, kept local since it's the only
// other place this exact layout is used.

function ToolTile({ to, name, blurb }) {
  return (
    <Link
      to={to}
      className="block pb-card p-5 border-pb-accent/30 hover:border-pb-accent/50 transition-colors group"
      style={{ background: 'color-mix(in srgb, var(--pb-accent) 6%, transparent)' }}
    >
      <div className="flex items-center justify-between gap-4">
        <span className="font-display font-bold text-lg text-pb-text">{name}</span>
        <span className="text-2xl group-hover:translate-x-1 transition-transform" style={{ color: 'var(--pb-accent)' }}>→</span>
      </div>
      <div className="text-pb-faint text-sm mt-1">{blurb}</div>
    </Link>
  )
}

export default function SalesManagement() {
  return (
    <AdminLayout>
      <div className="max-w-4xl">
        <div className="mb-1">
          <Link to="/admin/super/hub/crm" className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">
            ← CRM
          </Link>
        </div>
        <h1 className="font-display font-bold text-2xl text-pb-text">Sales Management</h1>
        <p className="text-pb-faint text-sm mb-5">Everything for running the sales team — call queue through to targets.</p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-4">
          {SALES_MANAGEMENT_ITEMS.map(item => (
            <ToolTile key={item.to} to={item.to} name={item.label} blurb={item.blurb} />
          ))}
        </div>
      </div>
    </AdminLayout>
  )
}
