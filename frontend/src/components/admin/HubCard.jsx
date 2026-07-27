import { Link } from 'react-router-dom'
import { ModuleWordmark } from '../ModuleLockup'

// The standard BetterCricket menu card — matches BetterAdmin's sub-cards, which
// are the house style for every menu card: the name (+ any badges) and an arrow
// on top, a description below, an accent-tinted panel. A `title` starting with
// "Better" gets the coloured-suffix wordmark; anything else renders plain bold.
//
// state:
//   'open' → a link (the arrow shows, hover lifts the border)
//   'soon' → greyed, not clickable (for a not-yet-released card); no arrow.

function Badge({ children }) {
  return (
    <span className="font-mono text-[10px] tracking-wide2 text-pb-faint border pb-hairline rounded px-2 py-0.5 uppercase shrink-0">
      {children}
    </span>
  )
}

export default function HubCard({ to, title, desc, badges = [], state = 'open' }) {
  const heading = (
    <div className="flex items-center justify-between gap-3">
      <span className="flex items-center gap-2 min-w-0 flex-wrap">
        <ModuleWordmark name={title} className="font-display font-bold text-lg text-pb-text" />
        {badges.map((b, i) => <Badge key={i}>{b}</Badge>)}
      </span>
      {state === 'open' && (
        <span className="text-2xl group-hover:translate-x-1 transition-transform shrink-0" style={{ color: 'var(--pb-accent)' }}>→</span>
      )}
    </div>
  )
  const body = desc && <div className="text-pb-faint text-sm mt-1">{desc}</div>

  if (state === 'open') {
    return (
      <Link
        to={to}
        className="block pb-card p-5 border-pb-accent/30 hover:border-pb-accent/50 transition-colors group"
        style={{ background: 'color-mix(in srgb, var(--pb-accent) 6%, transparent)' }}
      >
        {heading}
        {body}
      </Link>
    )
  }
  return (
    <div className="pb-card p-5 opacity-70 select-none cursor-default">
      {heading}
      {body}
    </div>
  )
}
