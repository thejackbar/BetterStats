import { useState, useEffect } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { api } from '../../lib/api'
import { useClubTheme } from '../../hooks/useClubTheme'
import { Icon } from '../../pages/admin/betterselect/ui'
import { moduleBrand } from '../../lib/moduleBrand'
import ModuleLockup from '../ModuleLockup'

// Generic chrome for a Better module surface (BetterFees, BetterSocials, …) —
// a focused sidebar with just that module's tools, separate from the main admin
// "noise", exactly like BetterSelect. Parameterised by `moduleName` (the suffix
// after "Better") and a `nav` array. BetterSelect predates this and keeps its
// own copy (BetterSelectLayout) so it isn't disturbed.

// Club branding is identical across a module's pages, so fetch settings once per
// session and reuse them — navigating between tools shouldn't refetch.
let _clubCache = null
let _clubPromise = null
function loadClubBranding() {
  if (_clubCache) return Promise.resolve(_clubCache)
  if (!_clubPromise) {
    _clubPromise = api.adminGetSettings().then(s => { _clubCache = s; return s }).catch(() => null)
  }
  return _clubPromise
}

export default function ModuleLayout({ moduleName, nav = [], children, title, actions }) {
  // Each module surface wears its own brand colour (BetterSocials magenta,
  // BetterFees / BetterComms the BetterAdmin amber). moduleName ("Socials" /
  // "Fees" / "Comms") resolves to the right brand via the shared registry.
  const brand = moduleBrand((moduleName || '').toLowerCase())
  const { user, logout, hasCapability } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [club, setClub] = useState(_clubCache)
  useEffect(() => { loadClubBranding().then(s => { if (s) setClub(s) }) }, [])
  useClubTheme(club)  // inject the club's white-label palette first…

  const items = nav.filter(i => i.cap == null || hasCapability(i.cap))

  const NavItems = ({ onNavigate }) => (
    <>
      {items.map(item => {
        const active = item.exact ? location.pathname === item.to : location.pathname.startsWith(item.to)
        return (
          <Link key={item.to} to={item.to} onClick={onNavigate}
            className={`flex items-center gap-3 px-4 py-2 text-sm transition-colors ${active ? 'bg-pb-accent/10 text-pb-accent border-r-2 border-pb-accent' : 'text-pb-faint hover:text-pb-text hover:bg-pb-surface2'}`}>
            <Icon name={item.icon} size={18} className="shrink-0" />
            <span>{item.label}</span>
          </Link>
        )
      })}
    </>
  )

  const Brand = () => (
    <div className="px-4 py-4 border-b pb-hairline">
      <div className="flex items-center gap-2.5">
        {club?.logo_url
          ? <img src={club.logo_url} alt="" className="w-8 h-8 rounded object-contain bg-pb-surface2 shrink-0" />
          : <span className="w-8 h-8 rounded bg-pb-accent/15 text-pb-accent font-display font-bold flex items-center justify-center shrink-0">{(club?.name || 'B')[0]}</span>}
        <div className="min-w-0">
          <div className="font-display font-bold text-sm leading-tight truncate" title={club?.name || ''}>{club?.name || 'BetterStats'}</div>
        </div>
      </div>
      {/* Module lockup — which Better module this surface is */}
      <ModuleLockup name={`Better${moduleName}`} logo={brand.logo} className="mt-3" />
      <Link to="/admin" className="block mt-3 text-[11px] font-mono text-pb-faintest hover:text-pb-faint">← Back to admin</Link>
    </div>
  )

  return (
    // Module chrome wears the module's own brand colour, NOT the club's
    // white-labelled public site. A club's accent can be any colour (e.g.
    // Applecross is red), which reads as alarming on headers/labels/status dots.
    // Re-point --pb-accent to the module's brand colour for everything inside the
    // module — custom properties inherit, so this one override cascades to every
    // child without touching the rest of the app.
    <div className="min-h-screen bg-pb-bg text-pb-text flex"
      style={{ '--pb-accent': brand.accent, '--pb-accent-rgb': brand.accentRgb }}>
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
            {title
              ? <h1 className="font-display font-bold text-lg md:text-xl">{title}</h1>
              : <span className="font-mono text-[11px] tracking-wide2 text-pb-faint">Better<span className="text-pb-accent">{moduleName}</span></span>}
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
