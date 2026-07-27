import { Link } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { Icon } from '../../pages/admin/betterselect/ui'

// Overview landing grid for a Core module surface (BetterStats / ClubManager).
// Turns a layout's `nav` array (with `{ heading }` separators and cap-gated
// items) into grouped tiles, so the surface's home page and its sidebar always
// list the same tools. The "Overview" item itself is skipped.
export default function ModuleOverviewGrid({ nav = [] }) {
  const { hasCapability } = useAuth()

  // Fold the flat nav (heading, item, item, heading, …) into groups, dropping
  // the Overview self-link and any item the user lacks the capability for.
  const groups = []
  let current = { heading: null, items: [] }
  for (const entry of nav) {
    if (entry.heading) {
      if (current.items.length) groups.push(current)
      current = { heading: entry.heading, items: [] }
      continue
    }
    if (entry.label === 'Overview') continue
    if (entry.cap != null && !hasCapability(entry.cap)) continue
    current.items.push(entry)
  }
  if (current.items.length) groups.push(current)

  return (
    <div className="space-y-6">
      {groups.map((g, i) => (
        <div key={g.heading || i}>
          {g.heading && (
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-2">{g.heading}</div>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {g.items.map(item => (
              <Link
                key={item.to}
                to={item.to}
                className="flex items-center gap-3 pb-card p-4 border-pb-accent/25 hover:border-pb-accent/50 transition-colors group"
                style={{ background: 'color-mix(in srgb, var(--pb-accent) 5%, transparent)' }}
              >
                <span
                  className="shrink-0 w-9 h-9 rounded-lg flex items-center justify-center"
                  style={{ background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)', color: 'var(--pb-accent)' }}
                >
                  <Icon name={item.icon} size={18} />
                </span>
                <span className="font-display font-bold text-sm text-pb-text">{item.label}</span>
                <span className="ml-auto text-lg group-hover:translate-x-0.5 transition-transform" style={{ color: 'var(--pb-accent)' }}>→</span>
              </Link>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
