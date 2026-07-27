import { Link, Navigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { Icon } from '../../pages/admin/betterselect/ui'

// Two-level landing for a Core module surface (BetterStats / ClubManager).
//   - no groupKey  → Overview: one card per group (label + description).
//   - groupKey set → that group's page: one card per tool (label + description).
// Both views read the SAME grouped config the sidebar is built from, so nothing
// drifts. Tools the user lacks the capability for are dropped; a group with no
// accessible tools left is hidden (overview) or sends you back (group page).

function Card({ to, icon, title, desc, meta }) {
  return (
    <Link
      to={to}
      className="flex items-start gap-3 pb-card p-4 border-pb-accent/25 hover:border-pb-accent/50 transition-colors group"
      style={{ background: 'color-mix(in srgb, var(--pb-accent) 5%, transparent)' }}
    >
      <span
        className="shrink-0 w-9 h-9 rounded-lg flex items-center justify-center mt-0.5"
        style={{ background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)', color: 'var(--pb-accent)' }}
      >
        <Icon name={icon} size={18} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="font-display font-bold text-sm text-pb-text">{title}</span>
          {meta && <span className="font-mono text-[10px] text-pb-faintest">{meta}</span>}
        </span>
        {desc && <span className="block text-pb-faint text-[12.5px] leading-snug mt-0.5">{desc}</span>}
      </span>
      <span className="shrink-0 text-lg group-hover:translate-x-0.5 transition-transform self-center" style={{ color: 'var(--pb-accent)' }}>→</span>
    </Link>
  )
}

export default function ModuleHub({ groups, basePath, groupKey }) {
  const { hasCapability } = useAuth()
  const accessible = items => items.filter(i => i.cap == null || hasCapability(i.cap))

  // A group's page — one card per tool.
  if (groupKey) {
    const group = groups.find(g => g.key === groupKey)
    if (!group) return <Navigate to={basePath} replace />
    const items = accessible(group.items)
    return (
      <div>
        <Link to={basePath} className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">← Overview</Link>
        <h2 className="font-display font-bold text-xl text-pb-text mt-2">{group.label}</h2>
        {group.desc && <p className="text-pb-faint text-sm mb-5">{group.desc}</p>}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-1">
          {items.map(item => (
            <Card key={item.to} to={item.to} icon={item.icon} title={item.label} desc={item.desc} />
          ))}
        </div>
        {items.length === 0 && (
          <div className="font-mono text-[11px] text-pb-faint py-4">Nothing here you can access.</div>
        )}
      </div>
    )
  }

  // Overview — one card per group.
  const shown = groups.filter(g => accessible(g.items).length > 0)
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {shown.map(g => {
        const n = accessible(g.items).length
        return (
          <Card
            key={g.key}
            to={`${basePath}/${g.key}`}
            icon={g.icon}
            title={g.label}
            desc={g.desc}
            meta={`${n} tool${n === 1 ? '' : 's'}`}
          />
        )
      })}
    </div>
  )
}
