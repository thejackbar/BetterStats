import { Link, NavLink } from 'react-router-dom'
import { useState } from 'react'
import clsx from 'clsx'
import { useTheme } from '../../contexts/ThemeContext'
import { useAuth } from '../../contexts/AuthContext'

const LINKS = [
  { to: '', label: 'Dashboard', end: true },
  { to: 'players', label: 'Players' },
  { to: 'games', label: 'Games' },
  { to: 'records', label: 'Records' },
  { to: 'leaderboard', label: 'Leaderboard' },
  { to: 'compare', label: 'Compare' },
]

export default function AflNavbar({ club }) {
  const { theme, toggle } = useTheme()
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  const base = `/${club.slug}`

  const links = LINKS.map(({ to, label, end }) => (
    <NavLink
      key={label}
      to={to ? `${base}/${to}` : base}
      end={end}
      onClick={() => setOpen(false)}
      className={({ isActive }) => clsx(
        'px-3 py-2 text-sm font-medium rounded transition-colors',
        isActive
          ? 'text-pb-text border-b-2 border-[var(--pb-accent)]'
          : 'text-pb-dim hover:text-pb-text',
      )}
    >
      {label}
    </NavLink>
  ))

  return (
    <header className="sticky top-0 z-40 bg-pb-surface/95 backdrop-blur pb-hairline-b">
      <div className="max-w-6xl mx-auto px-4 flex items-center gap-3 h-14">
        <Link to={base} className="flex items-center gap-2 min-w-0">
          {club.logo_url
            ? <img src={club.logo_url} alt="" className="h-8 w-8 rounded object-contain" />
            : <span className="h-8 w-8 rounded pb-gradient" />}
          <span className="font-bold text-pb-text truncate">{club.short_name || club.name}</span>
        </Link>
        <nav className="hidden md:flex items-center gap-1 ml-4">{links}</nav>
        <div className="ml-auto flex items-center gap-2">
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
            className="md:hidden text-pb-text px-2 py-1"
            onClick={() => setOpen(o => !o)}
            aria-label="Menu"
          >
            ☰
          </button>
        </div>
      </div>
      {open && (
        <nav className="md:hidden flex flex-col px-4 pb-3 gap-1 bg-pb-surface pb-hairline-b">
          {links}
        </nav>
      )}
    </header>
  )
}
