import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { CAP } from '../../lib/capabilities'
import { MODULE_INFO, tierLabel } from '../../lib/modules'
import { api } from '../../lib/api'
import { SITE_VERSION } from '../../version'
import { CHANGELOG } from '../../data/changelog'
import NotificationBell from '../NotificationBell'
import NotificationModal from '../NotificationModal'
import betterStatsLogo from '../../assets/betterstatslogo_white.png'

function compareVersions(a, b) {
  const parse = v => (v || '').replace('v', '').split('.').map(Number)
  const av = parse(a)
  const bv = parse(b)
  for (let i = 0; i < Math.max(av.length, bv.length); i++) {
    const diff = (av[i] || 0) - (bv[i] || 0)
    if (diff !== 0) return diff
  }
  return 0
}

// `cap: null` means everyone gets it (dashboard, read-only listing pages).
// `cap: <CAP>` hides the link from users without that capability.
// BetterSelect / BetterSocials / BetterFees are NOT here — each is its own
// module surface (own layout + nav), reached from the dashboard module tiles.
const NAV_SECTIONS = [
  { items: [{ to: '/admin', label: 'Dashboard', exact: true, cap: null }] },
  {
    heading: 'Cricket Data',
    items: [
      { to: '/admin/games', label: 'Matches', cap: null },
      { to: '/admin/players', label: 'Players', cap: CAP.MANAGE_PLAYERS },
      { to: '/admin/seasons', label: 'Seasons', cap: null },
    ],
  },
  {
    heading: 'Content',
    items: [
      { to: '/admin/award-definitions', label: 'Award Types', cap: CAP.MANAGE_AWARDS },
      { to: '/admin/awards', label: 'Awards', cap: CAP.MANAGE_AWARDS },
      { to: '/admin/sponsors', label: 'Sponsors', cap: CAP.MANAGE_SPONSORS },
      { to: '/admin/yearbook', label: 'Yearbooks', cap: CAP.MANAGE_YEARBOOKS },
    ],
  },
  {
    heading: 'Tools',
    items: [
      { to: '/admin/activity', label: 'Activity Log', cap: CAP.MANAGE_USERS },
      { to: '/admin/sync', label: 'Data Sync', cap: CAP.RUN_SYNC },
      { to: '/admin/families', label: 'Families', cap: CAP.MANAGE_FAMILIES },
      { to: '/admin/grades', label: 'Merge Grades', cap: CAP.MANAGE_MERGES },
      { to: '/admin/manual-entries', label: 'Manual Entries', cap: CAP.MANAGE_MANUAL_ENTRIES },
      { to: '/admin/merge', label: 'Merge Players', cap: CAP.MANAGE_MERGES },
      { to: '/admin/milestones', label: 'Milestones', cap: CAP.MANAGE_MILESTONES },
      { to: '/admin/partnerships', label: 'Partnership Rec.', cap: CAP.MANAGE_AWARDS },
      { to: '/admin/reports', label: 'Saved Reports', cap: CAP.MANAGE_REPORTS },
    ],
  },
  {
    heading: 'Account',
    items: [
      { to: '/admin/changelog', label: 'Changelog', cap: null },
      { to: '/admin/settings', label: 'Settings', cap: CAP.MANAGE_SETTINGS },
      { to: '/admin/users', label: 'Users', cap: CAP.MANAGE_USERS },
    ],
  },
]

const SUPER_LINKS = [
  { to: '/admin/super/clubs', label: 'All Clubs' },
  { to: '/admin/super/users', label: 'Users' },
  { to: '/admin/usage', label: 'Usage' },
]

export default function AdminLayout({ children }) {
  const { user, logout, hasCapability, hasModule, justLoggedIn, clearJustLoggedIn } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [bellOpen, setBellOpen] = useState(false)
  const [bellSummary, setBellSummary] = useState(null)
  const [bellError, setBellError] = useState(null)
  const [bellRefresh, setBellRefresh] = useState(0)

  // Filter nav: drop links the user lacks the cap for. Empty sections are
  // dropped too so club_member users don't see a bare heading with nothing
  // under it.
  const visibleSections = NAV_SECTIONS.map(s => ({
    ...s,
    items: s.items.filter(i => i.cap == null || hasCapability(i.cap)),
  })).filter(s => s.items.length > 0)

  // Open the modal immediately, then fetch the summary in the background.
  // If we wait for the fetch to resolve and it errors, the modal silently
  // never opens — which presents as "clicking the bell does nothing".
  const openBell = useCallback(async () => {
    setBellError(null)
    setBellOpen(true)
    try {
      const s = await api.getNotificationsSummary()
      setBellSummary(s)
    } catch (e) {
      setBellError(e?.message || 'Failed to load notifications')
    }
  }, [])

  const closeBell = useCallback(async () => {
    setBellOpen(false)
    try {
      await api.markNotificationsSeen(SITE_VERSION)
      setBellRefresh(r => r + 1)
    } catch {}
  }, [])

  // Auto-open on login if there's anything unseen (sync runs, milestones,
  // pending requests, or a changelog entry newer than last_seen_version).
  useEffect(() => {
    if (!justLoggedIn || !user) return
    let cancelled = false
    ;(async () => {
      try {
        const s = await api.getNotificationsSummary()
        if (cancelled) return
        const hasNewChangelog = CHANGELOG.some(
          e => compareVersions(e.version, s.last_seen_version) > 0
        )
        if ((s.unseen_count || 0) > 0 || hasNewChangelog) {
          setBellSummary(s)
          setBellOpen(true)
        }
      } catch {}
      clearJustLoggedIn()
    })()
    return () => { cancelled = true }
  }, [justLoggedIn, user, clearJustLoggedIn])

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
            <NotificationBell onOpen={openBell} refreshTrigger={bellRefresh} />
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
          w-full md:w-40 shrink-0 border-r pb-hairline-r pt-3 pb-6 px-1.5
        `}>
          <nav>
            {/* Modules — the headline Better products. Bolder + on top of the
                admin sections below; each opens its own module surface. Modules
                the club's plan doesn't include are greyed out (with the plan
                that unlocks them); BetterIQ shows "Soon". */}
            <div className="pb-2 mb-1 border-b pb-hairline-b">
              <div className="pb-1 px-2 font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Modules</div>
              {MODULE_INFO.map(mod => {
                if (mod.built && hasModule(mod.key)) {
                  return (
                    <Link
                      key={mod.key}
                      to={mod.to}
                      onClick={() => setMobileOpen(false)}
                      className={`block px-2 py-1.5 rounded transition-colors font-display font-bold text-[13px] ${
                        isActive(mod.to)
                          ? 'bg-pb-surface2 text-pb-text'
                          : 'text-pb-text hover:bg-pb-surface2'
                      }`}
                      style={isActive(mod.to) ? { color: 'var(--pb-accent)' } : {}}
                    >
                      {mod.name}
                    </Link>
                  )
                }
                const locked = mod.built  // built but not entitled
                return (
                  <div
                    key={mod.key}
                    title={locked ? `Included in the ${tierLabel(mod.requiredTier)} plan` : 'Coming soon'}
                    className="flex items-center justify-between px-2 py-1.5 rounded font-display font-bold text-[13px] text-pb-faintest opacity-50 cursor-default select-none"
                  >
                    <span>{mod.name}</span>
                    <span className="font-mono text-[9px]">{locked ? '🔒' : 'SOON'}</span>
                  </div>
                )
              })}
            </div>

            {visibleSections.map((section, i) => (
              <div
                key={section.heading || `section-${i}`}
                className={i > 0 ? 'mt-3 pt-3 border-t pb-hairline-t' : ''}
              >
                {section.heading && (
                  <div className="pb-1 px-2 font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">
                    {section.heading}
                  </div>
                )}
                {section.items.map(link => (
                  <Link
                    key={link.to}
                    to={link.to}
                    onClick={() => setMobileOpen(false)}
                    className={`block px-2 py-1.5 rounded transition-colors font-mono text-[11px] tracking-wide2 ${
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
              <div className="mt-3 pt-3 border-t pb-hairline-t">
                <div className="pb-1 px-2 font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Super Admin</div>
                {SUPER_LINKS.map(link => (
                  <Link
                    key={link.to}
                    to={link.to}
                    onClick={() => setMobileOpen(false)}
                    className={`block px-2 py-1.5 rounded transition-colors font-mono text-[11px] tracking-wide2 ${
                      isActive(link.to)
                        ? 'bg-pb-surface2'
                        : 'text-pb-faint hover:text-pb-text hover:bg-pb-surface2'
                    }`}
                    style={isActive(link.to) ? { color: 'var(--pb-accent)' } : {}}
                  >
                    {link.label.toUpperCase()}
                  </Link>
                ))}
              </div>
            )}
          </nav>
        </aside>

        {/* Main content */}
        <main className="flex-1 px-6 py-6 min-w-0">
          {children}
        </main>
      </div>

      <NotificationModal isOpen={bellOpen} summary={bellSummary} error={bellError} onClose={closeBell} />
    </div>
  )
}
