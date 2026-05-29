import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { CAP } from '../../lib/capabilities'

// BetterSelect runs as its own module surface — a focused nav with just the
// availability/selection tools, separate from the main admin "noise".
const NAV = [
  { to: '/admin/betterselect', label: 'Overview', icon: '◧', cap: null, exact: true },
  { to: '/admin/betterselect/fixtures', label: 'Fixtures', icon: '◴', cap: CAP.MANAGE_FIXTURES },
  { to: '/admin/betterselect/teams', label: 'Teams', icon: '⊞', cap: CAP.MANAGE_SELECTIONS },
  { to: '/admin/betterselect/availability', label: 'Availability', icon: '✓', cap: CAP.MANAGE_SELECTIONS },
]

export default function BetterSelectLayout({ children, title, actions }) {
  const { user, logout, hasCapability } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)

  const items = NAV.filter(i => i.cap == null || hasCapability(i.cap))

  const NavItems = ({ onNavigate }) => (
    <>
      {items.map(item => {
        const active = item.exact ? location.pathname === item.to : location.pathname.startsWith(item.to)
        return (
          <Link key={item.to} to={item.to} onClick={onNavigate}
            className={`flex items-center gap-3 px-4 py-2 text-sm transition-colors ${active ? 'bg-pb-accent/10 text-pb-accent border-r-2 border-pb-accent' : 'text-pb-faint hover:text-pb-text hover:bg-pb-surface2'}`}>
            <span className="text-base">{item.icon}</span>
            <span>{item.label}</span>
          </Link>
        )
      })}
    </>
  )

  const Brand = () => (
    <div className="px-4 py-4 border-b pb-hairline">
      <span className="font-display font-bold text-lg">Better<span className="text-pb-accent">Select</span></span>
      <Link to="/admin" className="block mt-1 text-[11px] font-mono text-pb-faintest hover:text-pb-faint">← Back to admin</Link>
    </div>
  )

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text flex">
      {/* Sidebar */}
      <aside className="w-60 border-r pb-hairline bg-pb-surface hidden md:flex flex-col sticky top-0 h-screen">
        <Brand />
        <nav className="flex-1 overflow-y-auto py-2"><NavItems /></nav>
      </aside>

      {/* Mobile sidebar */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setMobileOpen(false)} />
          <aside className="absolute left-0 top-0 bottom-0 w-60 bg-pb-surface border-r pb-hairline flex flex-col">
            <Brand />
            <nav className="flex-1 overflow-y-auto py-2"><NavItems onNavigate={() => setMobileOpen(false)} /></nav>
          </aside>
        </div>
      )}

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="sticky top-0 z-30 bg-pb-surface/80 backdrop-blur border-b pb-hairline px-4 md:px-6 py-3 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <button onClick={() => setMobileOpen(true)} className="md:hidden text-pb-faint">☰</button>
            <h1 className="font-display font-bold text-lg md:text-xl">{title}</h1>
          </div>
          <div className="flex items-center gap-3">
            {actions}
            <div className="hidden sm:flex items-center gap-2 text-sm text-pb-faint">
              <span>{user?.display_name || user?.username}</span>
              <button onClick={async () => { await logout(); navigate('/login') }} className="text-pb-faint hover:text-pb-text underline">Logout</button>
            </div>
          </div>
        </header>
        <main className="flex-1 p-4 md:p-6 max-w-[1400px] w-full mx-auto">{children}</main>
      </div>
    </div>
  )
}
