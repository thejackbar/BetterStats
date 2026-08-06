import { useState, useEffect, useCallback } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { api } from '../../lib/api'
import { useClubTheme } from '../../hooks/useClubTheme'
import { Icon } from '../../pages/admin/betterselect/ui'
import { moduleBrand } from '../../lib/moduleBrand'
import { TINT, Caption, HelpDot, initials } from './ui'
import ModuleLockup from '../ModuleLockup'
import ModuleSwitcher from './ModuleSwitcher'
import BookmarkButton from './BookmarkButton'

// Generic chrome for a Better module surface (BetterClubhouse, BetterSocials, …)
// — a focused sidebar with just that module's tools, separate from the main
// admin "noise". Parameterised by `moduleName` (the suffix after "Better") and a
// `nav` array. BetterSelect predates this and keeps its own copy
// (BetterSelectLayout) so it isn't disturbed.
//
// Shape follows the BetterClubhouse handoff: a 232px sidebar carrying the club
// identity, the module lockup, grouped nav and — in its footer — the platform
// chrome (module switcher, account, bookmarks). Moving the chrome down there is
// the load-bearing decision: it leaves the screen header free to carry the
// title, its caption, filters and stat readouts, and every screen inherits the
// chrome instead of each layout re-declaring it.
//
// Optional header slots (all default to nothing, so existing screens that only
// pass `title`/`actions` are unchanged):
//   caption   — the mono line under the title. Carries the live count.
//   onHelp    — renders the `?` that reopens the screen's introduction.
//   filters   — pills/search, sitting left of the `margin-left: auto` break.
//   stats     — right-aligned StatReadouts.
//   actions   — the primary action, last.
//   bare      — the screen manages its own padding and width (full-bleed
//               master-detail screens); otherwise children get the standard pad.
//   hideHeader— the screen draws its own sticky header. A transitional escape
//               hatch for the promoted ClubManager screens, which already had
//               one; below `lg` a slim bar still carries the ☰ so the sidebar
//               stays reachable.

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

// How far the sidebar nav is scrolled, kept outside the component on purpose.
//
// Following a nav item reset the list to the top or left it where it was,
// depending on nothing the person could see: routes whose pages are different
// components unmount ModuleLayout, so the <nav> is a brand new DOM node with
// scrollTop 0, while routes that happen to share a page component (the several
// that all render ClubManagerApp) reuse the instance and keep it. Holding the
// position out here survives the remount, so it never jumps to the top.
//
// Module scope, not per-instance: exactly one sidebar is on screen at a time,
// and the value has to outlive the unmount, which is the whole point.
let _navScroll = 0

// "2026/27" from today — the season line under the club name. Australian
// season rolls in July, matching services/votes.py's season_year_for.
function seasonLabel(d = new Date()) {
  const start = d.getMonth() >= 6 ? d.getFullYear() : d.getFullYear() - 1
  return `${start}/${String((start + 1) % 100).padStart(2, '0')} SEASON`
}

function NavBadge({ count, toneKey }) {
  if (!count) return null
  const warn = toneKey !== 'block'
  return (
    <span
      className="ml-auto font-mono text-[9px] rounded-full px-[5px] py-px shrink-0"
      style={warn
        ? { background: 'rgba(245,181,66,0.18)', color: '#f5b542' }
        : { background: 'rgba(239,91,91,0.18)', color: '#ef5b5b' }}
    >
      {count}
    </span>
  )
}

export default function ModuleLayout({
  moduleName, nav = [], children, title, caption, onHelp, filters, stats, actions,
  bare = false, hideHeader = false, sidebarFooterTop = null,
}) {
  // Each module surface wears its own brand colour (BetterSocials magenta,
  // BetterClubhouse amber). moduleName ("Socials" / "Clubhouse") resolves to the
  // right brand via the shared registry.
  const brand = moduleBrand((moduleName || '').toLowerCase())
  const { user, logout, hasCapability } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [club, setClub] = useState(_clubCache)
  useEffect(() => { loadClubBranding().then(s => { if (s) setClub(s) }) }, [])
  useClubTheme(club)  // inject the club's white-label palette first…

  // Close the off-canvas sidebar whenever the route changes, so following a
  // nav item on a phone doesn't leave the drawer covering what you asked for.
  useEffect(() => { setMobileOpen(false) }, [location.pathname])

  // Nav may include `{ heading }` separators — kept regardless of cap (they
  // carry no `to`/`cap`); ordinary items are filtered by capability. A heading
  // left with no visible items under it (all cap-filtered away, or trailing) is
  // dropped so a label never dangles. This filter is what stops one large
  // sidebar feeling large: a treasurer sees Today, Money and People and nothing
  // else.
  const items = nav
    .filter(i => i.heading || i.cap == null || (Array.isArray(i.cap) ? i.cap.some(hasCapability) : hasCapability(i.cap)))
    .filter((i, idx, arr) => !i.heading || (arr[idx + 1] && !arr[idx + 1].heading))

  // Label stored when bookmarking the current page — module name + page so the
  // bookmark reads clearly alongside ones from other surfaces.
  const activeNav = items.find(i => i.to && (i.exact ? location.pathname === i.to : location.pathname.startsWith(i.to)))
  const pageName = title || activeNav?.label
  const bookmarkLabel = `Better${moduleName}` + (pageName ? ` · ${pageName}` : '')

  // Restore on attach, record on scroll. The ref callback is memoised so React
  // only calls it when the node mounts or unmounts; an inline arrow would re-run
  // on every render and fight the person mid-scroll. The visibility check keeps
  // the off-canvas copy — which renders alongside the desktop one and can't
  // scroll while it is hidden — from recording a 0 over a real position.
  const attachNav = useCallback((el) => { if (el) el.scrollTop = _navScroll }, [])
  const onNavScroll = useCallback((e) => {
    const el = e.currentTarget
    if (el.offsetParent !== null) _navScroll = el.scrollTop
  }, [])

  const renderNavItems = () => (
    <>
      {items.map((item, idx) => {
        if (item.heading) {
          return (
            <div key={`h-${idx}`} className="px-4 pt-[15px] pb-1 font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">
              {item.heading}
            </div>
          )
        }
        const active = item.exact ? location.pathname === item.to : location.pathname.startsWith(item.to)
        return (
          <Link
            key={item.to} to={item.to}
            className={`flex items-center gap-[11px] w-full px-4 py-[9px] text-[13.5px] border-r-2 transition-colors ${active ? 'border-pb-accent' : 'border-transparent text-pb-faint hover:text-pb-text hover:bg-pb-surface2'}`}
            style={active ? { background: TINT.nav, color: 'var(--pb-accent-ink)' } : undefined}
          >
            <Icon name={item.icon} size={17} className="shrink-0" />
            <span className="truncate">{item.label}</span>
            <NavBadge count={item.badge} toneKey={item.badgeTone} />
          </Link>
        )
      })}
    </>
  )

  // Club identity + module lockup. The `← Back to admin` link the older layouts
  // carried is gone — the switcher in the footer replaces it.
  const renderBrand = () => (
    <div className="p-4 border-b pb-hairline shrink-0">
      <div className="flex items-center gap-2.5">
        {club?.logo_url
          ? <img src={club.logo_url} alt="" className="w-8 h-8 rounded-[5px] object-contain bg-pb-surface2 shrink-0" />
          : <span
              className="w-8 h-8 rounded-[5px] font-display font-bold text-[15px] flex items-center justify-center shrink-0"
              style={{ background: TINT.chip, color: 'var(--pb-accent-ink)' }}
            >{(club?.name || 'B')[0]}</span>}
        <div className="min-w-0">
          <div className="font-display font-bold text-sm leading-[1.2] truncate" title={club?.name || ''}>{club?.name || 'BetterCricket'}</div>
          {/* Acting on BetterCricket's own outreach org rather than a club. The
              season line is meaningless there, and the mode has to be obvious
              from any screen — sending a club campaign while you thought you
              were internal is the failure this guards against. Super admins
              only, so a club admin never sees it whatever the org is flagged. */}
          {user?.can_switch_clubs && user?.is_marketing_org
            ? <div className="font-mono text-[10px] tracking-wide2" style={{ color: 'var(--pb-accent-ink)' }}>INTERNAL MODE</div>
            : <div className="font-mono text-[10px] tracking-wide2 text-pb-faintest">{seasonLabel()}</div>}
        </div>
      </div>
      <ModuleLockup
        name={`Better${moduleName}`} logo={brand.logo} size={26}
        accent="var(--pb-accent-ink)"
        textClassName="font-display font-bold text-sm leading-none"
        className="mt-3"
      />
    </div>
  )

  // The platform chrome the per-module sidebars used to leave to the header.
  const renderSidebarFooter = () => (
    <div className="border-t pb-hairline px-3 py-[11px] shrink-0">
      {/* A module may put its own control above the switcher — BetterClubhouse
          uses it for the club ⇄ BetterCricket-internal switch. */}
      {sidebarFooterTop}
      <div className="font-mono text-[9px] tracking-[0.12em] uppercase text-pb-faintest mb-1.5">Switch module</div>
      <ModuleSwitcher wrap compact className="flex gap-1" />
      <div className="flex items-center gap-2 mt-2.5 pt-2.5 border-t pb-hairline">
        <span className="w-6 h-6 rounded-full bg-pb-surface2 border border-pb-hairline2 text-pb-dim font-display font-semibold text-[9px] flex items-center justify-center shrink-0">
          {initials(user?.display_name || user?.username)}
        </span>
        <span className="text-[12.5px] text-pb-dim truncate flex-1 min-w-0" title={user?.display_name || user?.username}>
          {user?.display_name || user?.username}
        </span>
        <BookmarkButton pageLabel={bookmarkLabel} drop="up" />
        <button
          onClick={async () => { await logout(); navigate('/login') }}
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
      <nav ref={attachNav} onScroll={onNavScroll} className="flex-1 overflow-y-auto py-2 pb-scroll">{renderNavItems()}</nav>
      {renderSidebarFooter()}
    </>
  )

  return (
    // Module chrome wears the module's own brand colour, NOT the club's
    // white-labelled public site. A club's accent can be any colour (e.g.
    // Applecross is red), which reads as alarming on headers/labels/status dots.
    // Re-point --pb-accent to the module's brand colour for everything inside the
    // module — custom properties inherit, so this one override cascades to every
    // child without touching the rest of the app. `pb-ink` re-derives the
    // light-mode-safe text version of it from this element (see theme.css).
    <div className="min-h-screen bg-pb-bg text-pb-text flex pb-ink"
      style={{ '--pb-accent': brand.accent, '--pb-accent-rgb': brand.accentRgb }}>
      {/* Sidebar — one breakpoint for the whole module: a column at ≥1024px,
          a drawer behind ☰ below it. */}
      <aside className="w-[232px] flex-none border-r pb-hairline bg-pb-surface hidden lg:flex flex-col sticky top-0 h-screen">
        {renderSidebar()}
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setMobileOpen(false)} />
          <aside className="absolute left-0 top-0 bottom-0 w-[232px] bg-pb-surface border-r pb-hairline flex flex-col ch-rise">
            {renderSidebar()}
          </aside>
        </div>
      )}

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        {hideHeader ? (
          <div className="lg:hidden sticky top-0 z-40 bg-pb-surface border-b pb-hairline px-5 py-2">
            <button onClick={() => setMobileOpen(true)} className="text-pb-dim border border-pb-hairline2 rounded-lg px-2.5 py-[7px] leading-none" aria-label="Open menu">☰</button>
          </div>
        ) : (
        <header className="sticky top-0 z-40 bg-pb-surface border-b pb-hairline px-5 py-3.5 flex items-center gap-3.5 flex-wrap">
          <button onClick={() => setMobileOpen(true)} className="lg:hidden text-pb-dim border border-pb-hairline2 rounded-lg px-2.5 py-[7px] leading-none" aria-label="Open menu">☰</button>
          <div className="flex items-center gap-2 min-w-0">
            <div className="min-w-0">
              {title
                ? <h1 className="font-display font-bold text-[19px] tracking-[-0.01em] truncate">{title}</h1>
                : <span className="font-mono text-[11px] tracking-wide2 text-pb-faint">Better<span style={{ color: 'var(--pb-accent-ink)' }}>{moduleName}</span></span>}
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
