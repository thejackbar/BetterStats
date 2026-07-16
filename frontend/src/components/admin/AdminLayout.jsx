import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useState, useEffect, useCallback, useMemo } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { CAP } from '../../lib/capabilities'
import { dashboardTiles } from '../../lib/modules'
import { moduleBrand } from '../../lib/moduleBrand'
import ModuleLockup from '../ModuleLockup'
import BookmarkButton from './BookmarkButton'
import { api } from '../../lib/api'
import { SITE_VERSION } from '../../version'
import { CHANGELOG } from '../../data/changelog'
import NotificationBell from '../NotificationBell'
import NotificationModal from '../NotificationModal'
import ClubSwitcher from './ClubSwitcher'
import BrandLogo from '../BrandLogo'
import OnboardingWizardModal from './OnboardingWizardModal'

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
      { to: '/admin/players/import', label: 'Import Players', cap: CAP.MANAGE_PLAYERS },
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
      { to: '/admin/upload-scorecard', label: 'Upload Scorecard', cap: CAP.MANAGE_MANUAL_ENTRIES },
      { to: '/admin/import', label: 'Import Stats', cap: CAP.MANAGE_MANUAL_ENTRIES },
      { to: '/admin/merge', label: 'Merge Players', cap: CAP.MANAGE_MERGES },
      { to: '/admin/milestones', label: 'Milestones', cap: CAP.MANAGE_MILESTONES },
      { to: '/admin/partnerships', label: 'Partnership Rec.', cap: CAP.MANAGE_AWARDS },
      { to: '/admin/reports', label: 'Saved Reports', cap: CAP.MANAGE_REPORTS },
    ],
  },
  {
    heading: 'Account',
    items: [
      { to: '/admin/settings', label: 'Settings', cap: CAP.MANAGE_SETTINGS },
      { to: '/admin/users', label: 'Users', cap: CAP.MANAGE_USERS },
      { to: '/admin/account', label: 'Plan & Billing', cap: null },
    ],
  },
]

const SUPER_LINKS = [
  { to: '/admin/super', label: 'Platform Overview', exact: true },
  { to: '/admin/super/clubs', label: 'All Clubs' },
  { to: '/admin/super/users', label: 'Users' },
  { to: '/admin/super/onboarding', label: 'Onboarding Requests' },
  { to: '/admin/super/self-serve', label: 'Self-Serve Trial (Internal)', flag: 'selfServeRegistration' },
  { to: '/admin/super/meta-ads', label: 'Meta Ads' },
  { to: '/admin/super/login-attempts', label: 'Login Attempts' },
  { to: '/admin/super/module-requests', label: 'Module Requests', badge: 'moduleRequests' },
  { to: '/admin/super/comms-limits', label: 'Comms Limits', badge: 'commsRequests' },
  { to: '/admin/super/announce', label: 'Club Announcements' },
  { to: '/admin/usage', label: 'Usage' },
  { to: '/admin/super/migration', label: 'KlubPro Migration' },
  { to: '/admin/super/marketing', label: 'Club Directory' },
  { to: '/admin/super/coupons', label: 'Discount Coupons' },
  { to: '/admin/changelog', label: 'Changelog' },
]

export default function AdminLayout({ children }) {
  const { user, logout, switchClub, hasCapability, hasModule, justLoggedIn, clearJustLoggedIn } = useAuth()

  // Super-admin module-request queue badge — refreshed on mount.
  useEffect(() => {
    if (user?.role !== 'super_admin') return
    let alive = true
    api.superCountModuleRequests()
      .then(d => { if (alive) setModuleReqCount(d?.outstanding || 0) })
      .catch(() => {})
    api.superCountCommsRequests()
      .then(d => { if (alive) setCommsReqCount(d?.total || 0) })
      .catch(() => {})
    api.superGetGeneralSettings()
      .then(s => { if (alive) setSelfServeEnabled(!!s?.self_serve_registration_enabled) })
      .catch(() => {})
    return () => { alive = false }
  }, [user?.role])
  const location = useLocation()
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)
  // Outstanding module requests (super-admin queue badge).
  const [moduleReqCount, setModuleReqCount] = useState(0)
  // Pending BetterComms tier requests + breaker-suspended clubs (badge).
  const [commsReqCount, setCommsReqCount] = useState(0)
  // Self-serve trial registration platform flag — off by default; hides the
  // internal-only menu item until a super admin turns it on (General Settings).
  const [selfServeEnabled, setSelfServeEnabled] = useState(false)
  const [bellOpen, setBellOpen] = useState(false)
  const [bellSummary, setBellSummary] = useState(null)
  const [bellError, setBellError] = useState(null)
  const [bellRefresh, setBellRefresh] = useState(0)
  // Onboarding wizard (Phase 15) — availability is only known once the first
  // state fetch succeeds (the endpoint 404s outright when the platform flag
  // is off, same "doesn't exist" convention as the self-serve flag).
  const [wizardAvailable, setWizardAvailable] = useState(false)
  const [wizardOpen, setWizardOpen] = useState(false)

  // Filter nav: drop links the user lacks the cap for. Empty sections are
  // dropped too so a heading never renders with nothing under it. (Club admins
  // hold every capability, so in practice they see the full set.)
  const visibleSections = NAV_SECTIONS.map(s => ({
    ...s,
    items: s.items.filter(i => i.cap == null || hasCapability(i.cap)),
  })).filter(s => s.items.length > 0)

  // Flag-gated Better HQ links (currently just self-serve registration) — hidden
  // until a super admin turns the platform flag on, same reasoning as the cap
  // filter above.
  const visibleSuperLinks = SUPER_LINKS.filter(l =>
    l.flag !== 'selfServeRegistration' || selfServeEnabled)

  // Give a bookmarked page a sensible name. Known nav routes carry their own
  // label; anything else (a deep/dynamic page) falls back to a tidied-up last
  // path segment so the bookmark still reads cleanly.
  const labelForPath = useMemo(() => {
    const map = {}
    NAV_SECTIONS.forEach(s => s.items.forEach(i => { map[i.to] = i.label }))
    SUPER_LINKS.forEach(l => { map[l.to] = l.label })
    dashboardTiles().forEach(m => { if (m.to) map[m.to] = m.name })
    return (path) => {
      if (map[path]) return map[path]
      const seg = path.split('/').filter(Boolean).pop() || 'Page'
      return seg.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
    }
  }, [])

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

  // Mark all read without closing — clears the unread (sync runs, milestones,
  // what's new), refetches so the panel settles on what's coming up, and
  // refreshes the bell badge. Marking seen is the load-bearing step; the
  // refetch is best-effort so a hiccup there still leaves the badge cleared.
  const clearBell = useCallback(async () => {
    try {
      await api.markNotificationsSeen(SITE_VERSION)
    } catch {
      return
    }
    try {
      const s = await api.getNotificationsSummary()
      setBellSummary(s)
    } catch {}
    setBellRefresh(r => r + 1)
  }, [])

  // Auto-open on login if there's anything unseen (sync runs, milestones,
  // pending requests, or a changelog entry newer than last_seen_version).
  // Super Admin only — the bell itself only renders for that role now.
  useEffect(() => {
    if (!justLoggedIn || !user) return
    let cancelled = false
    ;(async () => {
      if (user.role === 'super_admin') {
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
      }
      clearJustLoggedIn()
    })()
    return () => { cancelled = true }
  }, [justLoggedIn, user, clearJustLoggedIn])

  // Onboarding wizard: availability (the SETUP GUIDE button) is checked on
  // every mount, not gated to justLoggedIn — every admin page wraps itself
  // in its own <AdminLayout>, so this component remounts on every in-app
  // navigation, and a check tied to justLoggedIn (a one-shot flag cleared
  // right after the first effect run following a real login) would only
  // ever catch the very first page after login, vanishing on the next click.
  // The auto-open POPUP still only fires on a genuine fresh login (read from
  // justLoggedIn's value at the moment this runs, not as a dependency) so it
  // doesn't re-pop on every ordinary navigation — should_auto_open's own
  // dismissed_at/sync_steps_shown_at gating is what makes that safe to check
  // this often. 404 (flag off) is treated the same as "nothing to show" —
  // silently. Club-admin-only (the mirror of the bell's own super_admin-only
  // gate above): onboarding guidance belongs to the club's own admin, not a
  // super admin just visiting/acting-as the club.
  useEffect(() => {
    if (!user || user.role === 'super_admin') { setWizardAvailable(false); return }
    let cancelled = false
    ;(async () => {
      try {
        const s = await api.getOnboardingWizardState()
        if (cancelled) return
        setWizardAvailable(true)
        if (justLoggedIn && s.should_auto_open) setWizardOpen(true)
      } catch {
        // 404 (flag off) or any other failure — just hide the entry point
        if (!cancelled) setWizardAvailable(false)
      }
    })()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user])

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
              <BrandLogo className="w-7 h-7 object-contain" />
              <span className="font-display font-bold text-base tracking-wider uppercase text-pb-text group-hover:text-pb-accent transition-colors">
                BetterCricket
              </span>
            </Link>
            <span className="hidden sm:block text-pb-faintest text-sm">/</span>
            <span className="hidden sm:block font-mono text-[11px] tracking-wide2 text-pb-faint">ADMIN</span>
          </div>

          <div className="flex items-center gap-3">
            <ClubSwitcher />
            {user?.club_slug && (
              <Link
                to={`/${user.club_slug}`}
                className="hidden sm:inline-flex items-center gap-1.5 font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors border pb-hairline rounded px-3 py-1.5"
                title="Open your public club site"
              >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M14 5h5v5M19 5l-7 7M11 5H7a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4" />
                </svg>
                VIEW PUBLIC PAGE
              </Link>
            )}
            <BookmarkButton pageLabel={labelForPath(location.pathname)} />
            {wizardAvailable && (
              <button
                onClick={() => setWizardOpen(true)}
                title="Setup guide"
                className="hidden sm:inline-flex items-center gap-1.5 font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors border pb-hairline rounded px-3 py-1.5"
              >
                SETUP GUIDE
              </button>
            )}
            {user?.role === 'super_admin' && (
              <NotificationBell onOpen={openBell} refreshTrigger={bellRefresh} />
            )}
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

      {/* Acting-as banner — a persistent reminder that a Better staff member is
          scoped to a club other than their own, so changes land on the right
          club. */}
      {user?.acting_as_club && (
        <div
          className="text-center font-mono text-[10px] tracking-wide2 py-1.5 px-4"
          style={{ background: 'color-mix(in srgb, var(--pb-accent) 18%, transparent)', color: 'var(--pb-text)' }}
        >
          MANAGING <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{(user.club_name || user.club_slug || '').toUpperCase()}</span> AS SUPER ADMIN ·{' '}
          <button onClick={() => switchClub(null)} className="underline hover:no-underline">
            return to {user.home_club_name || 'home club'}
          </button>
        </div>
      )}

      <div className="flex flex-1 max-w-7xl mx-auto w-full">
        {/* Mobile drawer backdrop — dims the page and closes the menu on tap.
            Sits below the sidebar (z-40) and the header (z-50); mobile only. */}
        {mobileOpen && (
          <div
            className="fixed inset-0 z-30 bg-black/60 md:hidden"
            onClick={() => setMobileOpen(false)}
          />
        )}
        {/* Sidebar — an inline column on desktop, but a fixed slide-in drawer on
            mobile so it overlays the page instead of fighting <main> for width in
            the same flex row (which made the content overlap / go askew when the
            burger was tapped). The header (z-50) stays above the z-40 drawer so
            the burger/✕ remains tappable to close it. */}
        <aside className={`
          ${mobileOpen
            ? 'fixed left-0 top-14 bottom-0 z-40 w-64 max-w-[80vw] overflow-y-auto bg-pb-surface shadow-2xl'
            : 'hidden'}
          md:static md:z-auto md:block md:w-40 md:max-w-none md:overflow-visible md:bg-transparent md:shadow-none
          shrink-0 border-r pb-hairline-r pt-3 pb-6 px-1.5
        `}>
          <nav>
            {/* The core surface is BetterStats — its lockup sits at the top of
                the main admin sidebar, mirroring how each module surface shows
                its own lockup. The "Stats" suffix stays the fixed brand green
                (--pb-brand), never the club's white-label accent. */}
            <Link
              to="/admin"
              onClick={() => setMobileOpen(false)}
              className="block px-2 py-2 mb-1 border-b pb-hairline-b"
            >
              <ModuleLockup
                name="BetterStats"
                logo={moduleBrand('stats').logo}
                accent="var(--pb-brand)"
                size={24}
                textClassName="font-display font-bold text-[14px] leading-none"
              />
            </Link>

            {/* Better HQ — staff-only platform tools. Pinned to the TOP because
                for a super admin this is their primary surface (the club admin
                sections below are whichever club they're acting as). */}
            {user?.role === 'super_admin' && (
              <div
                className="pb-2 mb-1 border-b pb-hairline-b rounded"
                style={{ background: 'color-mix(in srgb, var(--pb-accent) 7%, transparent)' }}
              >
                <div className="pb-1 px-2 pt-1 font-mono text-[10px] tracking-wide3 uppercase" style={{ color: 'var(--pb-accent)' }}>
                  Better HQ
                </div>
                {visibleSuperLinks.map(link => (
                  <Link
                    key={link.to}
                    to={link.to}
                    onClick={() => setMobileOpen(false)}
                    className={`flex items-center justify-between gap-2 px-2 py-1.5 rounded transition-colors font-mono text-[11px] tracking-wide2 ${
                      isActive(link.to, link.exact)
                        ? 'bg-pb-surface2 text-pb-text'
                        : 'text-pb-faint hover:text-pb-text hover:bg-pb-surface2'
                    }`}
                    style={isActive(link.to, link.exact) ? { color: 'var(--pb-accent)' } : {}}
                  >
                    <span>{link.label.toUpperCase()}</span>
                    {link.badge === 'moduleRequests' && moduleReqCount > 0 && (
                      <span className="inline-flex items-center justify-center min-w-[16px] h-4 px-1 rounded-full bg-amber-500/20 text-amber-300 text-[9px] font-semibold">
                        {moduleReqCount}
                      </span>
                    )}
                    {link.badge === 'commsRequests' && commsReqCount > 0 && (
                      <span className="inline-flex items-center justify-center min-w-[16px] h-4 px-1 rounded-full bg-amber-500/20 text-amber-300 text-[9px] font-semibold">
                        {commsReqCount}
                      </span>
                    )}
                  </Link>
                ))}
              </div>
            )}

            {/* Modules — the headline Better products. Bolder + on top of the
                admin sections below; each opens its own module surface. Modules
                the club's plan doesn't include are greyed out (with the plan
                that unlocks them); BetterIQ shows "Soon". */}
            <div className="pb-2 mb-1 border-b pb-hairline-b">
              <div className="pb-1 px-2 font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Modules</div>
              {dashboardTiles().map(mod => {
                const entitled = mod.alwaysOpen || (mod.isGroup ? mod.members.some(m => hasModule(m.key)) : hasModule(mod.key))
                const brand = moduleBrand(mod.key)
                const suffix = mod.name.startsWith('Better') ? mod.name.slice('Better'.length) : null
                const Label = ({ muted }) => (
                  <span className="truncate">
                    {suffix
                      ? <>Better<span style={muted ? undefined : { color: brand.accent }}>{suffix}</span></>
                      : mod.name}
                  </span>
                )
                if (mod.built && entitled) {
                  return (
                    <Link
                      key={mod.key}
                      to={mod.to}
                      onClick={() => setMobileOpen(false)}
                      className={`flex items-center gap-2 px-2 py-1.5 rounded transition-colors font-display font-bold text-[13px] text-pb-text ${
                        isActive(mod.to) ? 'bg-pb-surface2' : 'hover:bg-pb-surface2'
                      }`}
                    >
                      <img src={brand.logo} alt="" className="w-4 h-4 rounded shrink-0" />
                      <Label />
                    </Link>
                  )
                }
                const locked = mod.built  // built but not entitled
                return (
                  <div
                    key={mod.key}
                    title={locked ? 'Available as an add-on' : 'Coming soon'}
                    className="flex items-center gap-2 px-2 py-1.5 rounded font-display font-bold text-[13px] text-pb-faintest cursor-default select-none"
                  >
                    <img src={brand.logo} alt="" className="w-4 h-4 rounded shrink-0 grayscale opacity-50" />
                    <Label muted />
                    <span className="font-mono text-[9px] ml-auto">{locked ? '🔒' : 'SOON'}</span>
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
          </nav>
        </aside>

        {/* Main content */}
        <main className="flex-1 px-6 py-6 min-w-0">
          {children}
        </main>
      </div>

      {user?.role === 'super_admin' && (
        <NotificationModal isOpen={bellOpen} summary={bellSummary} error={bellError} onClose={closeBell} onClear={clearBell} />
      )}
      {wizardOpen && <OnboardingWizardModal onClose={() => setWizardOpen(false)} />}
    </div>
  )
}
