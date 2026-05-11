import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { useAuth } from '../../contexts/AuthContext'

const NAV_LINKS = [
  { to: '/admin', label: 'Dashboard', exact: true },
  { to: '/admin/players', label: 'Players' },
  { to: '/admin/games', label: 'Matches' },
  { to: '/admin/seasons', label: 'Seasons' },
  { to: '/admin/awards', label: 'Awards' },
  { to: '/admin/merge', label: 'Merge Players' },
  { to: '/admin/sync', label: 'Data Sync' },
  { to: '/admin/partnerships', label: 'Partnership Rec.' },
  { to: '/admin/phq-match', label: 'PHQ ID Match' },
  { to: '/admin/settings', label: 'Settings' },
]

const SUPER_LINKS = [
  { to: '/admin/super/clubs', label: 'All Clubs' },
  { to: '/admin/super/users', label: 'Users' },
]

export default function AdminLayout({ children }) {
  const { user, logout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  const isActive = (to, exact) =>
    exact ? location.pathname === to : location.pathname.startsWith(to)

  return (
    <div className="min-h-screen bg-navy-950 flex flex-col">
      {/* Top bar */}
      <header className="bg-navy-900 border-b border-navy-700 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 flex items-center justify-between h-14">
          <div className="flex items-center gap-3">
            <Link to="/" className="flex items-center gap-2 group">
              <span className="w-6 h-6 rounded bg-accent flex items-center justify-center">
                <svg viewBox="0 0 24 24" className="w-4 h-4 fill-navy-950">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="4" x2="12" y2="20" stroke="#070b14" strokeWidth="2" />
                  <line x1="4" y1="12" x2="20" y2="12" stroke="#070b14" strokeWidth="2" />
                </svg>
              </span>
              <span className="font-display font-bold text-lg tracking-wider uppercase text-white group-hover:text-accent transition-colors">
                Better<span className="text-accent">Stats</span>
              </span>
            </Link>
            <span className="hidden sm:block text-navy-600 text-sm">/ Admin</span>
            <span className="hidden sm:block text-slate-700 text-xs font-mono">v3.0.2</span>
          </div>

          <div className="flex items-center gap-3">
            <span className="hidden sm:block text-slate-400 text-sm">
              {user?.display_name || user?.username}
              {user?.role === 'super_admin' && (
                <span className="ml-1 text-accent text-xs">(super)</span>
              )}
            </span>
            <button onClick={handleLogout} className="btn-ghost text-sm text-slate-400 hover:text-white">
              Log out
            </button>
            <button
              className="md:hidden text-slate-400 hover:text-white p-1"
              onClick={() => setMobileOpen(o => !o)}
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                {mobileOpen
                  ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                }
              </svg>
            </button>
          </div>
        </div>
      </header>

      <div className="flex flex-1 max-w-7xl mx-auto w-full">
        {/* Sidebar */}
        <aside className={`
          ${mobileOpen ? 'block' : 'hidden'} md:block
          w-full md:w-48 shrink-0 border-r border-navy-800 pt-4 pb-8 px-2
        `}>
          <nav className="space-y-1">
            {NAV_LINKS.map(link => (
              <Link
                key={link.to}
                to={link.to}
                onClick={() => setMobileOpen(false)}
                className={`block px-3 py-2 rounded text-sm transition-colors ${
                  isActive(link.to, link.exact)
                    ? 'bg-navy-800 text-accent'
                    : 'text-slate-400 hover:text-white hover:bg-navy-800'
                }`}
              >
                {link.label}
              </Link>
            ))}

            {user?.role === 'super_admin' && (
              <>
                <div className="pt-4 pb-1 px-3 text-xs text-slate-600 uppercase tracking-wider">Super Admin</div>
                {SUPER_LINKS.map(link => (
                  <Link
                    key={link.to}
                    to={link.to}
                    onClick={() => setMobileOpen(false)}
                    className={`block px-3 py-2 rounded text-sm transition-colors ${
                      isActive(link.to)
                        ? 'bg-navy-800 text-accent'
                        : 'text-slate-400 hover:text-white hover:bg-navy-800'
                    }`}
                  >
                    {link.label}
                  </Link>
                ))}
              </>
            )}
          </nav>
        </aside>

        {/* Main content */}
        <main className="flex-1 px-6 py-6 min-w-0">
          {children}
        </main>
      </div>
    </div>
  )
}
