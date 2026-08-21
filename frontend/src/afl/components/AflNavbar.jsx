import { Link, NavLink, useLocation } from 'react-router-dom'
import { useEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import { useTheme } from '../../contexts/ThemeContext'
import { useAuth } from '../../contexts/AuthContext'
import { mediaUrl } from '../aflApi'
import AflPlayerSearch from './AflPlayerSearch'

// Seven top-level links had outgrown the bar, and two pairs of them are the
// same question asked twice — "what did we win" and "who played" — so they
// group rather than sitting side by side. A group's `paths` are what light it
// up, so the bar still shows where you are once the page itself is a level
// down.
const LINKS = [
  { to: '', label: 'Dashboard', end: true },
  { to: 'players', label: 'Players' },
  {
    label: 'Games',
    paths: ['games', 'team-lists'],
    items: [
      { to: 'games', label: 'Games' },
      { to: 'team-lists', label: 'Team lists' },
    ],
  },
  {
    label: 'Records',
    paths: ['records', 'leaderboard', 'premierships', 'honour-board'],
    items: [
      { to: 'records', label: 'Records' },
      { to: 'leaderboard', label: 'Leaderboard' },
      { to: 'premierships', label: 'Premierships' },
      { to: 'honour-board', label: 'Honour Board' },
    ],
  },
  { to: 'compare', label: 'Compare' },
]

function ChevronDown({ open }) {
  return (
    <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor" aria-hidden="true"
         className={clsx('ml-1 transition-transform duration-150', open && 'rotate-180')}>
      <path d="M0 0l4 5 4-5z" />
    </svg>
  )
}

const linkClass = ({ isActive }) => clsx(
  'px-3 py-2 text-sm font-medium rounded transition-colors',
  isActive ? 'text-pb-text border-b-2 border-[var(--pb-accent)]' : 'text-pb-dim hover:text-pb-text',
)

function NavDropdown({ group, base, active, onNavigate }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  // Closes on a click anywhere else and on Escape. Without the first, opening
  // a second menu leaves the first one hanging open behind it.
  useEffect(() => {
    if (!open) return
    const away = (e) => { if (!ref.current?.contains(e.target)) setOpen(false) }
    const esc = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', away)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        aria-haspopup="menu"
        className={clsx(
          'flex items-center px-3 py-2 text-sm font-medium rounded transition-colors',
          active ? 'text-pb-text border-b-2 border-[var(--pb-accent)]' : 'text-pb-dim hover:text-pb-text',
        )}
      >
        {group.label}<ChevronDown open={open} />
      </button>
      {open && (
        <div role="menu"
             className="absolute left-0 top-full mt-1 min-w-[11rem] rounded bg-pb-surface pb-hairline shadow-lg py-1 z-50">
          {group.items.map(item => (
            <NavLink
              key={item.to}
              to={`${base}/${item.to}`}
              role="menuitem"
              onClick={() => { setOpen(false); onNavigate?.() }}
              className={({ isActive }) => clsx(
                'block px-3 py-2 text-sm whitespace-nowrap',
                isActive ? 'text-[var(--pb-accent)]' : 'text-pb-dim hover:text-pb-text hover:bg-pb-surface2',
              )}
            >
              {item.label}
            </NavLink>
          ))}
        </div>
      )}
    </div>
  )
}

export default function AflNavbar({ club }) {
  const { theme, toggle } = useTheme()
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  const base = `/${club.slug}`

  const isActivePath = (to) => pathname === `${base}/${to}` || pathname.startsWith(`${base}/${to}/`)

  const links = LINKS.map(entry => entry.items
    ? (
      <NavDropdown
        key={entry.label}
        group={entry}
        base={base}
        active={entry.paths.some(isActivePath)}
        onNavigate={() => setOpen(false)}
      />
    )
    : (
      <NavLink
        key={entry.label}
        to={entry.to ? `${base}/${entry.to}` : base}
        end={entry.end}
        onClick={() => setOpen(false)}
        className={linkClass}
      >
        {entry.label}
      </NavLink>
    ))

  // On a phone the group is a heading with its pages listed under it — a
  // menu that has already been opened deliberately should not need a second
  // tap to reveal what is in it.
  const mobileLinks = LINKS.map(entry => entry.items
    ? (
      <div key={entry.label} className="flex flex-col">
        <span className="px-3 pt-2 pb-1 font-mono text-[10px] uppercase tracking-wide3 text-pb-faint">
          {entry.label}
        </span>
        {entry.items.map(item => (
          <NavLink key={item.to} to={`${base}/${item.to}`} onClick={() => setOpen(false)}
                   className={linkClass}>
            {item.label}
          </NavLink>
        ))}
      </div>
    )
    : (
      <NavLink key={entry.label} to={entry.to ? `${base}/${entry.to}` : base} end={entry.end}
               onClick={() => setOpen(false)} className={linkClass}>
        {entry.label}
      </NavLink>
    ))

  return (
    <header className="sticky top-0 z-40 bg-pb-surface/95 backdrop-blur pb-hairline-b">
      <div className="max-w-6xl mx-auto px-4 flex items-center gap-3 h-14">
        <Link to={base} className="flex items-center gap-2 min-w-0">
          {club.logo_url
            ? <img src={mediaUrl(club.logo_url)} alt="" className="h-8 w-8 rounded object-contain" />
            : <span className="h-8 w-8 rounded pb-gradient" />}
          <span className="font-bold text-pb-text truncate">{club.short_name || club.name}</span>
        </Link>
        {/* One breakpoint for the whole bar: the search box needs room, so the
            links collapse into the drawer at lg rather than md — otherwise the
            bar between 768 and 1024px has neither the links nor the search. */}
        <nav className="hidden lg:flex items-center gap-1 ml-4">{links}</nav>
        <div className="ml-auto flex items-center gap-2">
          <AflPlayerSearch club={club} />
          <button
            onClick={toggle}
            className="text-pb-dim hover:text-pb-text text-sm px-2 py-1"
            title="Toggle light/dark"
          >
            {theme === 'dark' ? '☀' : '☾'}
          </button>
          <Link
            to={user ? '/admin' : '/login'}
            className="text-xs font-mono uppercase tracking-wide text-pb-dim hover:text-pb-text border border-pb-hairline rounded px-2 py-1"
          >
            {user ? 'Admin' : 'Admin login'}
          </Link>
          <button
            className="lg:hidden text-pb-text px-2 py-1"
            onClick={() => setOpen(o => !o)}
            aria-label="Menu"
          >
            ☰
          </button>
        </div>
      </div>
      {open && (
        <nav className="lg:hidden flex flex-col px-4 pb-3 gap-2 bg-pb-surface pb-hairline-b">
          {/* Search is above the links on a phone, where the whole reason the
              menu is open is usually to reach one person's profile. */}
          <AflPlayerSearch club={club} variant="mobile" onSelect={() => setOpen(false)} />
          <div className="flex flex-col gap-1">{mobileLinks}</div>
        </nav>
      )}
    </header>
  )
}
