import { Link, Navigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import HubCard from './HubCard'

// Two-level landing for a Core module surface (BetterStats / ClubManager).
//   - no groupKey  → Overview: one card per group (label + description).
//   - groupKey set → that group's page: one card per tool (label + description).
// Both views read the SAME grouped config the sidebar is built from, so nothing
// drifts. Cards use the shared HubCard (the BetterAdmin house style). Tools the
// user lacks the capability for are dropped; a group with no accessible tools
// is hidden (overview) or sends you back (group page).
export default function ModuleHub({ groups, basePath, groupKey }) {
  const { hasCapability } = useAuth()
  // anyCaps: show the item when the user holds ANY of the listed capabilities
  // (e.g. BetterSelect's Votes is open to managers and designated leaderboard
  // viewers alike). Falls back to the plain single-cap check otherwise.
  const accessible = items => items.filter(i => i.anyCaps
    ? i.anyCaps.some(c => hasCapability(c))
    : (i.cap == null || hasCapability(i.cap)))

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
            <HubCard key={item.to} to={item.to} title={item.label} desc={item.desc} />
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
      {shown.map(g => (
        <HubCard key={g.key} to={`${basePath}/${g.key}`} title={g.label} desc={g.desc} />
      ))}
    </div>
  )
}
