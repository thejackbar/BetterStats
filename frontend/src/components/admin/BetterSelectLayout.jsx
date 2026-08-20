import { useState, useEffect } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { CAP } from '../../lib/capabilities'
import { api } from '../../lib/api'
import { useClubTheme } from '../../hooks/useClubTheme'
import { Icon } from '../../pages/admin/betterselect/ui'
import { moduleBrand } from '../../lib/moduleBrand'
import ModuleLockup from '../ModuleLockup'
import ModuleSwitcher from './ModuleSwitcher'
import BookmarkButton from './BookmarkButton'

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
// availability/selection tools, separate from the main admin "noise". The
// tools are organised into GROUPS (same pattern as BetterStatsLayout): the
// surface home shows one card per group, each group card opens a page
// listing its tools, and the sidebar flattens the same groups into headed
// sections. One source of truth, three views. URLs of the tools themselves
// are unchanged — only the surrounding chrome moved.
export const GROUPS = [
  {
    key: 'squad',
    label: 'Your Squad',
    desc: 'Your player pool and how it splits into teams.',
    items: [
      { to: '/admin/betterselect/players', label: 'Players', icon: 'player', cap: CAP.MANAGE_PLAYERS, desc: 'Your BetterSelect player pool.' },
      { to: '/admin/betterselect/teams', label: 'Squads', icon: 'teams', cap: CAP.MANAGE_SELECTIONS, desc: 'Set up your teams and squads.' },
    ],
  },
  {
    key: 'matchday',
    label: 'Match Day',
    desc: 'The weekly cycle — fixtures, availability and picking the XI.',
    items: [
      { to: '/admin/betterselect/fixtures', label: 'Fixtures', icon: 'fixtures', cap: CAP.MANAGE_FIXTURES, desc: 'Upcoming games and results.' },
      { to: '/admin/betterselect/availability', label: 'Availability', icon: 'availability', cap: CAP.MANAGE_SELECTIONS, desc: "Who's around each weekend." },
      { to: '/admin/betterselect/selection', label: 'Selection', icon: 'selection', cap: CAP.MANAGE_SELECTIONS, desc: 'Pick and share your XI.' },
    ],
  },
  {
    key: 'club',
    label: 'Club Life',
    desc: 'Training, best-player voting and competition ladders.',
    items: [
      { to: '/admin/betterselect/nets', label: 'Nets', icon: 'nets', cap: CAP.MANAGE_SELECTIONS, desc: 'Training and net sessions.' },
      { to: '/admin/betterselect/votes', label: 'Votes', icon: 'votes', cap: null, anyCaps: [CAP.MANAGE_VOTES, CAP.VIEW_VOTE_RESULTS], desc: 'Best-player votes, Brownlow style.' },
      { to: '/admin/betterselect/ladders', label: 'Ladders', icon: 'ladders', cap: CAP.MANAGE_SELECTIONS, desc: 'Competition ladders.' },
    ],
  },
]

// The sidebar flattens the groups: Overview, then a heading + its tools per group.
export const NAV = [
  // Non-exact so Overview stays highlighted on the group pages
  // (/admin/betterselect/:group) too — no tool route is nested under this path.
  { to: '/admin/betterselect', label: 'Overview', icon: 'overview', cap: null },
  ...GROUPS.flatMap(g => [
    { heading: g.label },
    ...g.items.map(({ to, label, icon, cap, exact, anyCaps }) => ({ to, label, icon, cap, exact, anyCaps })),
  ]),
]

export default function BetterSelectLayout({ children, title, actions, headerLeft }) {
  const { user, logout, hasCapability } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [club, setClub] = useState(_clubCache)
  useEffect(() => { loadClubBranding().then(s => { if (s) setClub(s) }) }, [])
  useClubTheme(club)  // inject the club's white-label palette (accent etc.)

  // Nav may include `{ heading }` separators (kept regardless of cap — they
  // carry no `to`/`cap`); ordinary items are filtered by capability, with
  // anyCaps meaning "show when the user holds ANY of the listed capabilities"
  // (e.g. Votes is open to managers and designated leaderboard viewers alike).
  // A heading left with no visible items under it is dropped so a label never
  // dangles — same pattern as the generic ModuleLayout.
  const items = NAV
    .filter(i => i.heading || (i.anyCaps ? i.anyCaps.some(c => hasCapability(c)) : (i.cap == null || hasCapability(i.cap))))
    .filter((i, idx, arr) => !i.heading || (arr[idx + 1] && !arr[idx + 1].heading))

  // Label stored when bookmarking the current page.
  const activeNav = items.find(i => i.to && (i.exact ? location.pathname === i.to : location.pathname.startsWith(i.to)))
  const pageName = title || activeNav?.label
  const bookmarkLabel = 'BetterSelect' + (pageName ? ` · ${pageName}` : '')

  const NavItems = ({ onNavigate }) => (
    <>
      {items.map((item, idx) => {
        if (item.heading) {
          return (
            <div key={`h-${idx}`} className="px-4 pt-4 pb-1 font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">
              {item.heading}
            </div>
          )
        }
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
          <div className="font-display font-bold text-sm leading-tight truncate" title={club?.name || ''}>{club?.name || 'BetterCricket'}</div>
        </div>
      </div>
      {/* Module lockup — which Better module this surface is */}
      <ModuleLockup name="BetterSelect" logo={BRAND.logo} className="mt-3" />
      <Link to="/admin" className="block mt-3 text-[11px] font-mono text-pb-faintest hover:text-pb-faint">← Back to admin</Link>
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
            <div className="px-3 py-2.5 border-b pb-hairline"><ModuleSwitcher wrap className="flex" onNavigate={() => setMobileOpen(false)} /></div>
            <nav className="flex-1 overflow-y-auto py-2"><NavItems onNavigate={() => setMobileOpen(false)} /></nav>
          </aside>
        </div>
      )}

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* The three groups WRAP rather than collide. Reported from the
            Selection screen: its Dual rail / Team sheet toggle was being
            painted over by the module pills and the Share button from about
            1440px down. The first group carried min-w-0, so flex shrank the
            BOX below its content while the title and the toggle inside it
            could not shrink — the overflow slid under the later siblings,
            which paint on top. Three rules keep it apart now: the TITLE is
            the thing that gives way (truncate), the toggle and the actions
            never shrink, and anything that still does not fit moves to a
            second line. Tab rows wrap in this app; they do not scroll
            sideways and they certainly do not overlap. */}
        <header className="sticky top-0 z-30 bg-pb-surface/80 backdrop-blur border-b pb-hairline px-4 md:px-6 py-3 flex flex-wrap xl:flex-nowrap items-center justify-between gap-x-4 gap-y-2">
          <div className="flex items-center gap-3">
            <button onClick={() => setMobileOpen(true)} className="md:hidden text-pb-faint">☰</button>
            <h1 className="font-display font-bold text-lg md:text-xl truncate min-w-0">{title}</h1>
            {headerLeft && (
              <>
                <span className="h-[22px] w-px bg-pb-hairline2 hidden sm:block shrink-0" />
                <span className="shrink-0">{headerLeft}</span>
              </>
            )}
          </div>
          <ModuleSwitcher className="hidden md:flex min-w-0" />
          <div className="flex items-center gap-3 shrink-0">
            {actions}
            <BookmarkButton pageLabel={bookmarkLabel} />
            {/* Who you are signed in as, from xl up. It used to show from sm,
                which is ~110px of the least useful thing in the bar at exactly
                the widths where the bar has too much in it. Below xl the
                header wraps instead, and this is what it can most afford to
                drop; logging out stays reachable from the admin dashboard. */}
            <div className="hidden xl:flex items-center gap-2 text-sm text-pb-faint">
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
