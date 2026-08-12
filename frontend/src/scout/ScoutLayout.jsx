import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useScoutAuth } from './contexts/ScoutAuthContext'

const NAV_LINKS = [
  { to: '/betterscout/app', label: 'Dashboard', end: true },
  { to: '/betterscout/app/discover', label: 'Discover' },
  { to: '/betterscout/app/watchlists', label: 'Watchlists' },
  { to: '/betterscout/app/players', label: 'My players' },
  { to: '/betterscout/app/compare', label: 'Compare' },
]

export default function ScoutLayout() {
  const { user, logout } = useScoutAuth()
  const navigate = useNavigate()

  const doLogout = async () => {
    await logout()
    navigate('/betterscout/login')
  }

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <header className="border-b border-pb-hairline bg-pb-surface">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-baseline gap-3">
            <span className="font-bold">Better<span className="pb-gradient-text">Scout</span></span>
            <span className="text-sm text-pb-dim">{user?.scout_org_name}</span>
          </div>
          <button onClick={doLogout} className="text-sm text-pb-dim hover:text-pb-text">
            Log out
          </button>
        </div>
        <nav className="max-w-7xl mx-auto px-4 flex gap-4 text-sm">
          {NAV_LINKS.map(({ to, label, end }) => (
            <NavLink
              key={to} to={to} end={end}
              className={({ isActive }) =>
                `py-2 border-b-2 ${isActive ? 'border-[var(--pb-accent)] text-pb-text' : 'border-transparent text-pb-dim hover:text-pb-text'}`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="max-w-7xl mx-auto px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}
