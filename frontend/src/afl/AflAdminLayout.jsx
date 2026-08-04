import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import LoadingSpinner from '../components/LoadingSpinner'
import { aflApi } from './aflApi'

// Self-contained AFL admin shell — deliberately NOT built on cricket's
// ModuleLayout/ModuleSwitcher/BookmarkButton/TrialBanner, which assume the
// cricket module marketplace, billing and setup wizard AFL doesn't have yet.
// Mirrors the same idea (a sidebar of tools) with none of that coupling.

const NAV = [
  { heading: 'Club Data' },
  { to: '/admin', label: 'Data Sync', end: true },
  { to: '/admin/players', label: 'Players' },
  { to: '/admin/players/import', label: 'Import Players' },
  { heading: 'Clean Your Data' },
  { to: '/admin/merge-grades', label: 'Merge Grades' },
  { heading: 'Records & Content' },
  { to: '/admin/award-definitions', label: 'Award Types' },
  { to: '/admin/awards', label: 'Awards' },
  { to: '/admin/sponsors', label: 'Sponsors' },
  { heading: 'Account' },
  { to: '/admin/users', label: 'Users' },
]

const SUPER_NAV = [
  { heading: 'Better HQ' },
  { to: '/admin/super/clubs', label: 'All Clubs' },
  { to: '/admin/super/users', label: 'Users (platform)' },
]

export default function AflAdminLayout() {
  const { user, loading: authLoading, logout } = useAuth()
  const navigate = useNavigate()
  const [settings, setSettings] = useState(null)
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    if (authLoading) return
    if (!user) { navigate('/login'); return }
    aflApi.getAdminSettings().then(setSettings).catch(() => {})
  }, [authLoading, user, navigate])

  if (authLoading) {
    return <div className="min-h-screen bg-pb-bg pt-24 flex justify-center"><LoadingSpinner /></div>
  }
  if (!user) return null

  const isSuper = user.role === 'super_admin'
  const items = isSuper ? [...NAV, ...SUPER_NAV] : NAV

  const NavItems = ({ onNavigate }) => (
    <>
      {items.map((item, idx) => item.heading ? (
        <div key={`h-${idx}`} className="px-4 pt-4 pb-1 font-mono text-[10px] uppercase tracking-wide3 text-pb-faint">
          {item.heading}
        </div>
      ) : (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          onClick={onNavigate}
          className={({ isActive }) =>
            `block px-4 py-2 text-sm transition-colors ${isActive
              ? 'bg-[color-mix(in_srgb,var(--pb-accent)_12%,transparent)] text-[var(--pb-accent)] border-r-2 border-[var(--pb-accent)]'
              : 'text-pb-dim hover:text-pb-text hover:bg-pb-surface2'}`
          }
        >
          {item.label}
        </NavLink>
      ))}
    </>
  )

  const Brand = () => (
    <div className="px-4 py-4 pb-hairline-b">
      <div className="flex items-center gap-2.5">
        {settings?.logo_url
          ? <img src={settings.logo_url} alt="" className="w-8 h-8 rounded object-contain bg-pb-surface2 shrink-0" />
          : <span className="w-8 h-8 rounded pb-gradient shrink-0" />}
        <div className="min-w-0">
          <div className="font-bold text-sm leading-tight truncate">{settings?.name || 'BetterFootball'}</div>
        </div>
      </div>
      <div className="mt-3 font-mono text-[11px] tracking-wide2 text-pb-faint">
        Better<span className="text-[var(--pb-accent)]">Football</span> Admin
      </div>
      {settings?.slug && (
        <Link to={`/${settings.slug}`} className="block mt-2 text-[11px] font-mono text-pb-faintest hover:text-pb-faint">
          View public page →
        </Link>
      )}
    </div>
  )

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text flex">
      <aside className="w-60 pb-hairline-r bg-pb-surface hidden md:flex flex-col sticky top-0 h-screen">
        <Brand />
        <nav className="flex-1 overflow-y-auto py-2"><NavItems /></nav>
        <div className="px-4 py-3 pb-hairline-t text-sm text-pb-faint flex items-center justify-between">
          <span className="truncate">{user.display_name || user.username}</span>
          <button onClick={async () => { await logout(); navigate('/login') }} className="text-pb-dim hover:text-pb-text underline shrink-0 ml-2">
            Sign out
          </button>
        </div>
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setMobileOpen(false)} />
          <aside className="absolute left-0 top-0 bottom-0 w-64 bg-pb-surface pb-hairline-r flex flex-col">
            <Brand />
            <nav className="flex-1 overflow-y-auto py-2"><NavItems onNavigate={() => setMobileOpen(false)} /></nav>
          </aside>
        </div>
      )}

      <div className="flex-1 flex flex-col min-w-0">
        <header className="sticky top-0 z-30 bg-pb-surface/80 backdrop-blur pb-hairline-b px-4 py-3 flex items-center justify-between gap-4 md:hidden">
          <button onClick={() => setMobileOpen(true)} className="text-pb-faint">☰</button>
          <span className="font-mono text-[11px] tracking-wide2 text-pb-faint">
            Better<span className="text-[var(--pb-accent)]">Football</span> Admin
          </span>
          <button onClick={async () => { await logout(); navigate('/login') }} className="text-pb-dim hover:text-pb-text text-sm">
            Sign out
          </button>
        </header>
        <main className="flex-1 p-4 md:p-6 max-w-[1200px] w-full mx-auto">
          <Outlet context={{ settings }} />
        </main>
      </div>
    </div>
  )
}
