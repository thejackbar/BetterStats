import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import betterStatsLogo from '../../assets/betterstatslogo_white.png'

const NAV_SECTIONS = [
  { items: [{ to: '/admin', label: 'Dashboard', exact: true }] },
  {
    heading: 'Cricket Data',
    items: [
      { to: '/admin/players', label: 'Players' },
      { to: '/admin/games', label: 'Matches' },
      { to: '/admin/seasons', label: 'Seasons' },
    ],
  },
  {
    heading: 'Content',
    items: [
      { to: '/admin/yearbook', label: 'Yearbooks' },
      { to: '/admin/awards', label: 'Awards' },
      { to: '/admin/award-definitions', label: 'Award Types' },
      { to: '/admin/sponsors', label: 'Sponsors' },
      { to: '/admin/social-post', label: 'Social Posts' },
    ],
  },
  {
    heading: 'Tools',
    items: [
      { to: '/admin/milestones', label: 'Milestones' },
      { to: '/admin/sync', label: 'Data Sync' },
      { to: '/admin/merge', label: 'Merge Players' },
      { to: '/admin/grades', label: 'Merge Grades' },
      { to: '/admin/partnerships', label: 'Partnership Rec.' },
      { to: '/admin/activity', label: 'Activity Log' },
    ],
  },
  { items: [{ to: '/admin/settings', label: 'Settings' }] },
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
    <div className="min-h-screen bg-pb-bg text-pb-text flex flex-col">
      {/* Top bar */}
      <header className="bg-pb-surface border-b pb-hairline-b sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 flex items-center justify-between h-14">
          <div className="flex items-center gap-3">
            <Link to="/" className="flex items-center gap-2 group">
              <img
                src={betterStatsLogo}
                alt="BetterStats"
                className="w-7 h-7 object-contain"
              />
              <span className="font-display font-bold text-base tracking-wider uppercase text-pb-text group-hover:text-pb-accent transition-colors">
                BetterStats
              </span>
            </Link>
            <span className="hidden sm:block text-pb-faintest text-sm">/</span>
            <span className="hidden sm:block font-mono text-[11px] tracking-wide2 text-pb-faint">ADMIN</span>
          </div>

          <div className="flex items-center gap-3">
            <span className="hidden sm:block font-mono text-[11px] text-pb-faint">
              {user?.display_name || user?.username}
              {user?.role === 'super_admin' && (
                <span className="ml-1 text-[10px]" style={{ color: 'var(--pb-accent)' }}>(SUPER)</span>
              )}
            </span>
            <button
              onClick={handleLogout}
              className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors border pb-hairline rounded px-3 py-1.5"
            >
              LOG OUT
            </button>
            <button
              className="md:hidden text-pb-faint hover:text-pb-text p-1"
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
          w-full md:w-48 shrink-0 border-r pb-hairline-r pt-4 pb-8 px-2
        `}>
          <nav className="space-y-0.5">
            {NAV_SECTIONS.map((section, i) => (
              <div key={section.heading || `section-${i}`} className={i > 0 ? 'pt-3' : ''}>
                {section.heading && (
                  <div className="pb-1 px-3 font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase">
                    {section.heading}
                  </div>
                )}
                {section.items.map(link => (
                  <Link
                    key={link.to}
                    to={link.to}
                    onClick={() => setMobileOpen(false)}
                    className={`block px-3 py-2 rounded text-sm transition-colors font-mono text-[11px] tracking-wide2 ${
                      isActive(link.to, link.exact)
                        ? 'bg-pb-surface2 text-pb-text'
                        : 'text-pb-faint hover:text-pb-text hover:bg-pb-surface2'
                    }`}
                    style={isActive(link.to, link.exact) ? { color: 'var(--pb-accent)' } : {}}
                  >
                    {link.label.toUpperCase()}
                  </Link>
                ))}
              </div>
            ))}

            {user?.role === 'super_admin' && (
              <>
                <div className="pt-5 pb-1 px-3 font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase">Super Admin</div>
                {SUPER_LINKS.map(link => (
                  <Link
                    key={link.to}
                    to={link.to}
                    onClick={() => setMobileOpen(false)}
                    className={`block px-3 py-2 rounded text-sm transition-colors font-mono text-[11px] tracking-wide2 ${
                      isActive(link.to)
                        ? 'bg-pb-surface2'
                        : 'text-pb-faint hover:text-pb-text hover:bg-pb-surface2'
                    }`}
                    style={isActive(link.to) ? { color: 'var(--pb-accent)' } : {}}
                  >
                    {link.label.toUpperCase()}
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
