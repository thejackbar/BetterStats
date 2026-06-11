import { useState, useEffect } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { CAP } from '../../lib/capabilities'
import { api } from '../../lib/api'
import { useClubTheme } from '../../hooks/useClubTheme'
import { Icon } from '../../pages/admin/betterselect/ui'
import { moduleBrand } from '../../lib/moduleBrand'

const BRAND = moduleBrand('select')

// Club branding is identical for every BetterSelect page, so fetch the club
// settings once per session and reuse them — navigating between tools shouldn't
// refetch. Feeds the layout the club's palette (useClubTheme), logo and name.
let _clubCache = null
let _clubPromise = null
function loadClubBranding() {
  if (_clubCache) return Promise.resolve(_clubCache)
  if (!_clubPromise) {
    _clubPromise = api.adminGetSettings().then(s => { _clubCache = s; return s }).catch(() => null)
  }
  return _clubPromise
}

// BetterSelect runs as its own module surface — a focused nav with just the
// availability/selection tools, separate from the main admin "noise".
const NAV = [
  { to: '/admin/betterselect', label: 'Overview', icon: 'overview', cap: null, exact: true },
  { to: '/admin/betterselect/players', label: 'Players', icon: 'player', cap: CAP.MANAGE_PLAYERS },
  { to: '/admin/betterselect/fixtures', label: 'Fixtures', icon: 'fixtures', cap: CAP.MANAGE_FIXTURES },
  { to: '/admin/betterselect/teams', label: 'Squads', icon: 'teams', cap: CAP.MANAGE_SELECTIONS },
  { to: '/admin/betterselect/availability', label: 'Availability', icon: 'availability', cap: CAP.MANAGE_SELECTIONS },
  { to: '/admin/betterselect/selection', label: 'Selection', icon: 'selection', cap: CAP.MANAGE_SELECTIONS },
  { to: '/admin/betterselect/nets', label: 'Nets', icon: 'nets', cap: CAP.MANAGE_SELECTIONS },
  { to: '/admin/betterselect/ladders', label: 'Ladders', icon: 'ladders', cap: CAP.MANAGE_SELECTIONS },
]

export default function BetterSelectLayout({ children, title, actions, headerLeft }) {
  const { user, logout, hasCapability } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [club, setClub] = useState(_clubCache)
  useEffect(() => { loadClubBranding().then(s => { if (s) setClub(s) }) }, [])
  useClubTheme(club)  // inject the club's white-label palette (accent etc.)

  const items = NAV.filter(i => i.cap == null || hasCapability(i.cap))

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
          <div className="font-mono text-[10px] text-pb-faint">Better<span style={{ color: 'var(--pb-accent)' }}>Select</span></div>
        </div>
      </div>
      <Link to="/admin" className="block mt-2 text-[11px] font-mono text-pb-faintest hover:text-pb-faint">← Back to admin</Link>
    </div>
  )

  return (
    // BetterSelect is module-branded chrome, NOT the club's white-labelled public
    // site. A club's accent can be any colour (e.g. Applecross is red), which
    // reads as alarming/error-like on headers, labels and status dots. Re-point
    // --pb-accent to BetterSelect's own brand colour for everything inside this
    // module — custom properties inherit, so this one override cascades to every
    // child (text-pb-accent, bg-pb-accent, color-mix tints, the lot) without
    // touching the rest of the app, where the club accent still applies.
    <div className="min-h-screen bg-pb-bg text-pb-text flex"
      style={{ '--pb-accent': BRAND.accent, '--pb-accent-rgb': BRAND.accentRgb }}>
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
          <div className="flex items-center gap-3 min-w-0">
            <button onClick={() => setMobileOpen(true)} className="md:hidden text-pb-faint">☰</button>
            <h1 className="font-display font-bold text-lg md:text-xl">{title}</h1>
            {headerLeft && <><span className="h-[22px] w-px bg-pb-hairline2 hidden sm:block" />{headerLeft}</>}
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
