import { useState, useCallback } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useScoutAuth } from './contexts/ScoutAuthContext'
import { Icon } from '../pages/admin/betterselect/ui'
import { moduleBrand } from '../lib/moduleBrand'
import { Caption, HelpDot, initials, TINT } from '../components/admin/ui'
import ModuleLockup from '../components/ModuleLockup'

// BetterScout's own module shell — visually the same shape as
// components/admin/ModuleLayout.jsx (232px sticky sidebar, brand block,
// Icon+label nav rows with the 2px active right border + accent tint, a
// sticky header with title/caption/stats/actions slots, the `bare`/
// `hideHeader` escape hatches, an off-canvas drawer below `lg`), but fed by
// useScoutAuth() instead of the club AuthContext — a Scout Org has no
// club, no capabilities, no module entitlements, and none of ModuleLayout's
// club-coupled reads (useAuth, api.adminGetSettings, useClubTheme,
// hasCapability, ModuleSwitcher) apply here. Kept as a deliberate fork
// rather than parameterising ModuleLayout itself — the two shells' data
// sources are different enough that sharing one component would mean
// threading club-shaped optionals through code that has no club.
//
// No ModuleSwitcher in the footer: a Scout Org genuinely cannot reach
// BetterStats/Select/Admin/IQ (different tenant, no club entitlements), so
// showing pills that go nowhere would be a broken affordance. The footer is
// just the signed-in user + log out.

const NAV = [
  { to: '/betterscout/app', label: 'Overview', icon: 'overview', exact: true },
  { to: '/betterscout/app/discover', label: 'Discover clubs', icon: 'search' },
  { to: '/betterscout/app/search', label: 'Player search', icon: 'player' },
  { to: '/betterscout/app/hot-form', label: 'Hot form feed', icon: 'bolt' },
  { to: '/betterscout/app/watchlists', label: 'Watchlists', icon: 'cols' },
  { to: '/betterscout/app/players', label: 'My players', icon: 'teams', badgeKey: 'tracked' },
  { to: '/betterscout/app/compare', label: 'Compare', icon: 'ladders' },
  { to: '/betterscout/app/milestones', label: 'Milestones', icon: 'selection', badgeKey: 'milestones' },
  { to: '/betterscout/app/settings', label: 'Settings', icon: 'settings' },
]

// "2026/27" from today — cricket season rolls in July. Same rule
// ModuleLayout's own seasonLabel() and services/votes.py's
// season_year_for use; BetterScout has no per-club diary_start_month to
// read, so this generic version is the right one here.
function seasonLabel(d = new Date()) {
  const start = d.getMonth() >= 6 ? d.getFullYear() : d.getFullYear() - 1
  return `${start}/${String((start + 1) % 100).padStart(2, '0')}`
}

function NavBadge({ count, tone = 'amber' }) {
  if (!count) return null
  const style = tone === 'accent'
    ? { background: 'color-mix(in srgb, var(--pb-accent) 18%, transparent)', color: 'var(--pb-accent-ink)' }
    : { background: 'rgba(245,181,66,0.18)', color: '#f5b542' }
  return (
    <span className="ml-auto font-mono text-[9px] rounded-full px-[5px] py-px shrink-0" style={style}>
      {count}
    </span>
  )
}

export default function ScoutModuleLayout({
  children, title, caption, onHelp, filters, stats, actions, bare = false, hideHeader = false,
}) {
  const brand = moduleBrand('scout')
  const { user, logout } = useScoutAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)

  const badgeCounts = {
    tracked: user?.usage?.player_count,
    // Reached-but-not-yet-marked-seen — see services/scout_milestones.py's
    // ScoutMilestoneSeen. "In reach" players are a call-to-action, not an
    // unread count, so the badge is deliberately the latter.
    milestones: user?.milestones_unseen_count,
  }

  const doLogout = useCallback(async () => {
    await logout()
    navigate('/betterscout/login')
  }, [logout, navigate])

  const renderNavItems = () => (
    <>
      {NAV.map(item => {
        const active = item.exact ? location.pathname === item.to : location.pathname.startsWith(item.to)
        return (
          <Link
            key={item.to} to={item.to}
            className={`flex items-center gap-[11px] w-full px-4 py-[9px] text-[13.5px] border-r-2 transition-colors ${active ? 'border-pb-accent' : 'border-transparent text-pb-faint hover:text-pb-text hover:bg-pb-surface2'}`}
            style={active ? { background: TINT.nav, color: 'var(--pb-accent-ink)' } : undefined}
          >
            <Icon name={item.icon} size={17} className="shrink-0" />
            <span className="truncate">{item.label}</span>
            {item.badgeKey && <NavBadge count={badgeCounts[item.badgeKey]} tone={item.badgeKey === 'milestones' ? 'accent' : 'amber'} />}
          </Link>
        )
      })}
    </>
  )

  const renderBrand = () => (
    <div className="p-4 border-b pb-hairline shrink-0">
      <div className="flex items-center gap-2.5">
        <span
          className="w-8 h-8 rounded-[5px] font-display font-bold text-[15px] flex items-center justify-center shrink-0"
          style={{ background: TINT.chip, color: 'var(--pb-accent-ink)' }}
        >{(user?.scout_org_name || 'S')[0]}</span>
        <div className="min-w-0">
          <div className="font-display font-bold text-sm leading-[1.2] truncate" title={user?.scout_org_name || ''}>
            {user?.scout_org_name || 'Scout Org'}
          </div>
          <div className="font-mono text-[10px] tracking-wide2 text-pb-faintest truncate">
            SCOUT ORG · {seasonLabel()}
          </div>
        </div>
      </div>
      <ModuleLockup
        name="BetterScout" logo={brand.logo} size={26}
        accent="var(--pb-accent-ink)"
        textClassName="font-display font-bold text-sm leading-none"
        className="mt-3"
      />
    </div>
  )

  const renderSidebarFooter = () => (
    <div className="border-t pb-hairline px-3 py-[11px] shrink-0">
      <div className="flex items-center gap-2">
        <span className="w-6 h-6 rounded-full bg-pb-surface2 border border-pb-hairline2 text-pb-dim font-display font-semibold text-[9px] flex items-center justify-center shrink-0">
          {initials(user?.display_name || user?.username)}
        </span>
        <span className="text-[12.5px] text-pb-dim truncate flex-1 min-w-0" title={user?.display_name || user?.username}>
          {user?.display_name || user?.username}
        </span>
        <button
          onClick={doLogout}
          title="Log out" aria-label="Log out"
          className="text-pb-faint hover:text-pb-text shrink-0"
        >
          <Icon name="back" size={15} />
        </button>
      </div>
    </div>
  )

  const renderSidebar = () => (
    <>
      {renderBrand()}
      <nav className="flex-1 overflow-y-auto py-2 pb-scroll">{renderNavItems()}</nav>
      {renderSidebarFooter()}
    </>
  )

  return (
    // BetterScout wears its own brand colour everywhere inside this shell —
    // re-pointing --pb-accent here (same mechanism ModuleLayout uses per
    // club module) cascades to every descendant with no further wiring.
    <div className="min-h-screen bg-pb-bg text-pb-text flex pb-ink"
      style={{ '--pb-accent': brand.accent, '--pb-accent-rgb': brand.accentRgb }}>
      <aside className="scout-no-print w-[232px] flex-none border-r pb-hairline bg-pb-surface hidden lg:flex flex-col sticky top-0 h-screen">
        {renderSidebar()}
      </aside>

      {mobileOpen && (
        <div className="scout-no-print fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setMobileOpen(false)} />
          <aside className="absolute left-0 top-0 bottom-0 w-[232px] bg-pb-surface border-r pb-hairline flex flex-col ch-rise">
            {renderSidebar()}
          </aside>
        </div>
      )}

      <div className="flex-1 flex flex-col min-w-0">
        {hideHeader ? (
          <div className="scout-no-print lg:hidden sticky top-0 z-40 bg-pb-surface border-b pb-hairline px-5 py-2">
            <button onClick={() => setMobileOpen(true)} className="text-pb-dim border border-pb-hairline2 rounded-lg px-2.5 py-[7px] leading-none" aria-label="Open menu">☰</button>
          </div>
        ) : (
        <header className="scout-no-print sticky top-0 z-40 bg-pb-surface border-b pb-hairline px-5 py-3.5 flex items-center gap-3.5 flex-wrap">
          <button onClick={() => setMobileOpen(true)} className="lg:hidden text-pb-dim border border-pb-hairline2 rounded-lg px-2.5 py-[7px] leading-none" aria-label="Open menu">☰</button>
          <div className="flex items-center gap-2 min-w-0">
            <div className="min-w-0">
              {title
                ? <h1 className="font-display font-bold text-[19px] tracking-[-0.01em] truncate">{title}</h1>
                : <span className="font-mono text-[11px] tracking-wide2 text-pb-faint">Better<span style={{ color: 'var(--pb-accent-ink)' }}>Scout</span></span>}
              {caption && <Caption screen className="mt-0.5">{caption}</Caption>}
            </div>
            {onHelp && <HelpDot onClick={onHelp} />}
          </div>
          {filters}
          <div className="ml-auto flex items-center gap-[26px]">
            {stats}
            {actions && <div className="flex items-center gap-2">{actions}</div>}
          </div>
        </header>
        )}
        {bare
          ? <div className="flex-1 min-w-0 min-h-0 flex flex-col">{children}</div>
          : <main className="flex-1 p-5 md:px-6 md:py-[22px] max-w-[1400px] w-full">{children}</main>}
      </div>
    </div>
  )
}
