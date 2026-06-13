import { useState, useEffect } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { CAP } from '../../lib/capabilities'
import { api } from '../../lib/api'
import { useClubTheme } from '../../hooks/useClubTheme'
import { Icon } from '../../pages/admin/betteriq/ui'
import { ContextBar } from '../../pages/admin/betteriq/Context'
import { moduleBrand } from '../../lib/moduleBrand'
import ModuleLockup from '../ModuleLockup'
import '../../pages/admin/betteriq/iq-theme.css'

const IQ_BRAND = moduleBrand('iq')

// Club branding is identical across BetterIQ pages — fetch once per session and
// reuse (mirrors BetterSelectLayout's cache).
let _clubCache = null
let _clubPromise = null
function loadClubBranding() {
  if (_clubCache) return Promise.resolve(_clubCache)
  if (!_clubPromise) {
    _clubPromise = api.adminGetSettings().then(s => { _clubCache = s; return s }).catch(() => null)
  }
  return _clubPromise
}

// Route table: drives grouped sidebar nav + the header eyebrow/title + the
// per-route key the ContextBar reads. `title`/`actions` props still override.
const ROUTES = [
  { key: 'overview', to: '/admin/betteriq', exact: true, label: 'Overview', icon: 'overview', eyebrow: 'BetterIQ', title: 'Overview', cap: null },
  { key: 'player', to: '/admin/betteriq/player', label: 'Player search', icon: 'search', eyebrow: 'BetterIQ', title: 'Player search', cap: CAP.MANAGE_IQ },
  { group: 'Scout the opposition' },
  { key: 'preview', to: '/admin/betteriq/preview', label: 'Match preview', icon: 'fixtures', eyebrow: 'Scout the opposition', title: 'Match preview', cap: CAP.MANAGE_IQ },
  { key: 'opposition', to: '/admin/betteriq/opposition', label: 'Opposition club', icon: 'search', eyebrow: 'Scout the opposition', title: 'Opposition analysis', cap: CAP.MANAGE_IQ },
  { key: 'opposition-player', to: '/admin/betteriq/opposition-player', label: 'Opposition player', icon: 'player', eyebrow: 'Scout the opposition', title: 'Opposition player', cap: CAP.MANAGE_IQ },
  { group: 'Know your club' },
  { key: 'selection', to: '/admin/betteriq/selection', label: 'Selection', icon: 'selection', eyebrow: 'Know your club', title: 'Selection analysis', cap: CAP.MANAGE_IQ },
  { key: 'trends', to: '/admin/betteriq/trends', label: 'Form & trends', icon: 'trend', eyebrow: 'Know your club', title: 'Form & trends', cap: CAP.MANAGE_IQ },
  { key: 'team', to: '/admin/betteriq/team', label: 'Team analysis', icon: 'teams', eyebrow: 'Know your club', title: 'Team analysis', cap: CAP.MANAGE_IQ },
  { key: 'review', to: '/admin/betteriq/review', label: 'Match review', icon: 'overview', eyebrow: 'Know your club', title: 'Match review', cap: CAP.MANAGE_IQ },
]
const NAV_ITEMS = ROUTES.filter(r => r.key)

// Pick the nav entry that best matches the current path (longest matching `to`,
// honouring `exact` for the overview root). opposition-player must not match the
// shorter opposition prefix.
function matchRoute(pathname) {
  let best = null
  for (const r of NAV_ITEMS) {
    if (r.exact) { if (pathname === r.to) best = r; continue }
    if (pathname === r.to || pathname.startsWith(r.to + '/') || pathname.startsWith(r.to + '?')) {
      if (!best || r.to.length > best.to.length) best = r
    }
  }
  return best || NAV_ITEMS[0]
}

function ThemeToggle({ theme, onToggle }) {
  const dark = theme === 'dark'
  return (
    <button onClick={onToggle} title="Toggle theme"
      className="flex items-center justify-center transition hover:brightness-125"
      style={{ width: 34, height: 34, borderRadius: 9, border: '1px solid var(--pb-hairline2)', background: 'var(--pb-surface2)', color: 'var(--pb-dim)' }}>
      {dark ? (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
      )}
    </button>
  )
}

export default function IQLayout({ children, title, eyebrow, actions }) {
  const { user, logout, hasCapability } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [club, setClub] = useState(_clubCache)
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('iq.theme') || 'dark' } catch { return 'dark' }
  })
  useEffect(() => { loadClubBranding().then(s => { if (s) setClub(s) }) }, [])
  useClubTheme(club)
  const toggleTheme = () => setTheme(t => { const n = t === 'dark' ? 'light' : 'dark'; try { localStorage.setItem('iq.theme', n) } catch { /* ignore */ } return n })

  const current = matchRoute(location.pathname)
  const head = { title: title || current.title, eyebrow: eyebrow || current.eyebrow }

  const Brand = () => (
    <div className="px-5 pt-5 pb-4" style={{ borderBottom: '1px solid var(--pb-hairline)' }}>
      <div className="flex items-center gap-3">
        {club?.logo_url
          ? <img src={club.logo_url} alt="" className="shrink-0 object-contain" style={{ width: 38, height: 38, borderRadius: 11, background: 'var(--pb-surface2)' }} />
          : <div className="flex items-center justify-center shrink-0 iq-display font-bold" style={{ width: 38, height: 38, borderRadius: 11, fontSize: 16, background: 'linear-gradient(150deg, var(--iq-violet-bright), var(--iq-violet-deep))', color: '#fff', boxShadow: '0 6px 18px -8px var(--pb-accent)' }}>{(club?.name || 'B')[0]}</div>}
        <div className="min-w-0">
          <div className="iq-display font-bold text-[15px] leading-none truncate" title={club?.name || ''}>{club?.name || 'BetterStats'}</div>
        </div>
      </div>
      {/* Module lockup — which Better module this surface is */}
      <ModuleLockup name="BetterIQ" logo={IQ_BRAND.logo} className="mt-3" textClassName="iq-display font-bold text-[15px] leading-none" />
      <Link to="/admin" className="mt-3 block iq-mono text-left whitespace-nowrap transition-colors hover:text-pb-faint" style={{ fontSize: 11, color: 'var(--pb-faintest)' }}>← Back to admin</Link>
    </div>
  )

  const NavList = ({ onNavigate }) => (
    <nav className="flex flex-col gap-0.5 px-3 py-3">
      {ROUTES.map((item, idx) => {
        if (item.group) return (
          <div key={'g' + idx} className="iq-eyebrow px-3 pt-4 pb-1.5" style={{ fontSize: 9, color: 'var(--pb-faintest)' }}>{item.group}</div>
        )
        if (item.cap != null && !hasCapability(item.cap)) return null
        const active = current.key === item.key
        return (
          <Link key={item.key} to={item.to} onClick={onNavigate} title={item.label}
            className="group relative flex items-center gap-3 transition-colors text-left"
            style={{ padding: '9px 12px', borderRadius: 10, fontSize: 13.5,
              color: active ? 'var(--pb-accent)' : 'var(--pb-dim)',
              background: active ? 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' : 'transparent',
              fontWeight: active ? 600 : 500 }}
            onMouseEnter={e => { if (!active) { e.currentTarget.style.color = 'var(--pb-text)'; e.currentTarget.style.background = 'var(--pb-surface2)' } }}
            onMouseLeave={e => { if (!active) { e.currentTarget.style.color = 'var(--pb-dim)'; e.currentTarget.style.background = 'transparent' } }}>
            {active && <span className="absolute left-0 top-1/2 -translate-y-1/2" style={{ width: 3, height: 18, borderRadius: 99, background: 'var(--pb-accent)' }} />}
            <Icon name={item.icon} size={17} className="shrink-0" />
            <span className="iq-display flex-1">{item.label}</span>
          </Link>
        )
      })}
    </nav>
  )

  const SIDEBAR_W = 248
  return (
    <div className="iq-root" data-theme={theme} data-card="hairline">
      <div className="flex min-h-screen">
        {/* Desktop sidebar */}
        <aside className="hidden md:flex flex-col sticky top-0 shrink-0"
          style={{ width: SIDEBAR_W, height: '100vh', background: 'var(--pb-surface)', borderRight: '1px solid var(--pb-hairline)' }}>
          <Brand />
          <div className="flex-1 overflow-y-auto iq-scroll"><NavList /></div>
          <div className="px-5 py-4 iq-mono" style={{ fontSize: 10, letterSpacing: '0.16em', color: 'var(--pb-faintest)', borderTop: '1px solid var(--pb-hairline)', textTransform: 'uppercase' }}>
            BetterIQ · Analytics
          </div>
        </aside>

        {/* Mobile drawer */}
        {mobileOpen && (
          <div className="fixed inset-0 z-50 md:hidden">
            <div className="absolute inset-0" style={{ background: 'rgba(0,0,0,0.6)' }} onClick={() => setMobileOpen(false)} />
            <aside className="absolute left-0 top-0 bottom-0 flex flex-col" style={{ width: SIDEBAR_W, background: 'var(--pb-surface)', borderRight: '1px solid var(--pb-hairline)' }}>
              <Brand />
              <div className="flex-1 overflow-y-auto iq-scroll"><NavList onNavigate={() => setMobileOpen(false)} /></div>
            </aside>
          </div>
        )}

        {/* Main column */}
        <div className="flex-1 flex flex-col min-w-0">
          <header className="sticky top-0 z-30 flex items-center justify-between gap-4 px-5 md:px-8"
            style={{ height: 64, background: 'color-mix(in srgb, var(--pb-surface) 80%, transparent)', backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)', borderBottom: '1px solid var(--pb-hairline)' }}>
            <div className="flex items-center gap-3 min-w-0">
              <button onClick={() => setMobileOpen(true)} className="md:hidden text-pb-dim" style={{ fontSize: 20 }}>☰</button>
              <div className="min-w-0">
                {head.eyebrow && <div className="iq-eyebrow leading-none" style={{ fontSize: 9 }}>{head.eyebrow}</div>}
                <h1 className="iq-display font-bold text-[18px] md:text-[20px] leading-tight truncate" style={{ letterSpacing: '-0.01em', marginTop: head.eyebrow ? 3 : 0 }}>{head.title}</h1>
              </div>
            </div>
            <div className="flex items-center gap-2.5 shrink-0">
              {actions}
              <ThemeToggle theme={theme} onToggle={toggleTheme} />
              <div className="hidden sm:flex items-center gap-2.5 pl-2.5" style={{ borderLeft: '1px solid var(--pb-hairline)' }}>
                <div className="text-right leading-tight whitespace-nowrap">
                  <div className="text-[12.5px] font-medium">{user?.display_name || user?.username}</div>
                  <button onClick={async () => { await logout(); navigate('/login') }} className="iq-mono hover:text-pb-text transition-colors" style={{ fontSize: 9.5, color: 'var(--pb-faint)' }}>Logout</button>
                </div>
                <div className="flex items-center justify-center iq-display font-bold" style={{ width: 32, height: 32, borderRadius: 9, background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline2)', fontSize: 12, color: 'var(--pb-dim)' }}>
                  {(user?.display_name || user?.username || '?').replace(/^[A-Z]\.\s*/, '').slice(0, 2).toUpperCase()}
                </div>
              </div>
            </div>
          </header>
          <ContextBar route={current.key} />
          <main className="flex-1 px-5 md:px-8 py-7 md:py-9 w-full mx-auto" style={{ maxWidth: 1320 }}>{children}</main>
        </div>
      </div>
    </div>
  )
}
