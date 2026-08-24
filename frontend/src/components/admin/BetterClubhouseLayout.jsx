import { useAuth } from '../../contexts/AuthContext'
import { CAP } from '../../lib/capabilities'
import { useClubhouseData, clubhouseModules } from '../../pages/admin/clubhouse/data'
import ModuleLayout from './ModuleLayout'
import ClubhouseContextControl from './ClubhouseContextControl'

// BetterAdmin — the club's back office as ONE module.
//
// BetterFees, BetterComms, BetterMerch and BetterClubManager used to be four
// surfaces with four sidebars, four accents and four ways of drawing a button.
// They are now six sections of one sidebar on one amber accent: People, Money,
// Stock, Comms, Club, Setup. The old names are headings, not brands.
//
// Nothing moved URL: every tool kept the route it already had, so bookmarks and
// deep links still work. What changed is which shell they render inside.
//
// Each item carries the gate it needs and is dropped when the gate fails:
//   cap    — a capability (an array means "any of these")
//   module — one of the umbrella's paid modules the club must hold
// The promoted ClubManager screens used to carry a `super` flag as well, which
// hid Directory, Roster, Committee, Diary, Events, Facilities and the whole
// Setup catalogue from anyone who was not a super admin. That dated from
// BetterClubManager being unlaunched; the screens run on real data now, and
// every router behind them already enforces its own capability, so the club's
// own admins get them.
// A heading whose items all fall away is dropped by ModuleLayout, so a
// treasurer holding only BetterFees sees Today, Money and nothing else.

function buildNav({ modules, counts, storefront }) {
  return [
    { to: '/admin/clubhouse', label: 'Today', icon: 'overview', exact: true, badge: counts.needsYou },

    { heading: 'People' },
    { to: '/admin/clubhouse/directory', label: 'Directory', icon: 'teams', cap: [CAP.MANAGE_MEMBERS, CAP.MANAGE_VOLUNTEERS, CAP.MANAGE_COMMITTEE, CAP.MANAGE_QUALIFICATIONS] },
    { to: '/admin/clubhouse/roster', label: 'Roster', icon: 'fixtures', cap: CAP.MANAGE_VOLUNTEERS },
    { to: '/admin/committee', label: 'Committee', icon: 'sheet', cap: CAP.MANAGE_COMMITTEE },

    { heading: 'Money' },
    { to: '/admin/fees', label: 'Accounts', icon: 'money', cap: CAP.MANAGE_FEES, module: 'fees', exact: true, badge: counts.owing },
    { to: '/admin/fees/payments', label: 'Payments', icon: 'list', cap: CAP.MANAGE_FEES, module: 'fees' },
    { to: '/admin/fees/schedule', label: 'Membership tiers', icon: 'sheet', cap: CAP.MANAGE_FEES, module: 'fees' },

    { heading: 'Stock' },
    { to: '/admin/merch/stock', label: 'Inventory', icon: 'list', cap: CAP.MANAGE_MERCH, module: 'merch', badge: counts.reorder },
    { to: '/admin/merch/equipment', label: 'Equipment', icon: 'settings', cap: CAP.MANAGE_MERCH, module: 'merch' },
    ...(storefront ? [{ to: '/admin/merch/orders', label: 'Online store', icon: 'sheet', cap: CAP.MANAGE_MERCH, module: 'merch' }] : []),

    { heading: 'Comms' },
    { to: '/admin/comms', label: 'Emails', icon: 'list', cap: CAP.MANAGE_COMMS, module: 'comms', exact: true, badge: counts.drafts },
    // An audience is not a place you go. It is the slot on an email, and what
    // fills it is a segment or a list — so those two get the items, named for
    // what they are. Both carry an "Email these N now" button that opens a
    // draft already addressed to them.
    { to: '/admin/comms/lists', label: 'Lists', icon: 'teams', cap: CAP.MANAGE_COMMS, module: 'comms' },
    { to: '/admin/comms/segments', label: 'Segments', icon: 'filter', cap: CAP.MANAGE_COMMS, module: 'comms' },
    { to: '/admin/comms/templates', label: 'Templates', icon: 'sheet', cap: CAP.MANAGE_COMMS, module: 'comms' },
    { to: '/admin/comms/settings', label: 'Email settings', icon: 'settings', cap: CAP.MANAGE_COMMS, module: 'comms' },

    { heading: 'Club' },
    { to: '/admin/club-diary', label: 'Diary', icon: 'ladders', cap: CAP.MANAGE_CLUB_DIARY },
    { to: '/admin/events', label: 'Events', icon: 'timer', cap: CAP.MANAGE_COMMITTEE },
    { to: '/admin/assets', label: 'Facilities & Assets', icon: 'nets', cap: CAP.MANAGE_ASSETS },

    { heading: 'Setup' },
    // The catalogue every other screen reads from: roles (a committee-flagged
    // role IS a committee position), activities, qualification types,
    // operational areas. Dropping it from the sidebar left the whole
    // configuration layer unreachable except by typing a URL.
    { to: '/admin/clubhouse/areas-roles', label: 'Areas & roles', icon: 'settings', cap: [CAP.MANAGE_VOLUNTEERS, CAP.MANAGE_QUALIFICATIONS] },
    { to: '/admin/clubhouse/integrations', label: 'Integrations', icon: 'share', cap: [CAP.MANAGE_FEES, CAP.MANAGE_MERCH, CAP.MANAGE_COMMS] },
    { to: '/admin/clubhouse/reports', label: 'Reports', icon: 'ladders', cap: [CAP.MANAGE_FEES, CAP.MANAGE_MERCH] },
    { to: '/admin/clubhouse/settings', label: 'Settings', icon: 'settings' },
  ].filter(i => {
    if (i.heading) return true
    if (i.module && !modules[i.module]) return false
    return true
  })
}

// The nav while a super admin is working on BetterCricket's own outreach org.
//
// BetterCricket is not a cricket club: it has no members to charge, no stock,
// no roster and no committee, so those groups would read empty and — worse —
// make it easy to forget you had switched. What is left is the two things the
// platform surface is actually for.
//
// Segments is the same URL as a club's, /admin/comms/segments — SegmentsRoute
// mounts the directory builder instead of the club one while acting as the
// outreach org. That is the whole scope rule in one line: the two field sets
// live in two components, and which one you get is a route, not a runtime flag
// inside one screen. The item used to point out of the module entirely, at
// /admin/super/directory-audiences, which dropped you on the plain admin chrome
// halfway through a Clubhouse task.
function buildInternalNav({ counts }) {
  return [
    { to: '/admin/clubhouse', label: 'Today', icon: 'overview', exact: true },

    { heading: 'BetterCricket' },
    { to: '/admin/clubhouse/internal/directory', label: 'Directory', icon: 'teams' },

    { heading: 'Comms' },
    { to: '/admin/comms', label: 'Emails', icon: 'list', exact: true, badge: counts.drafts },
    { to: '/admin/comms/lists', label: 'Lists', icon: 'teams' },
    { to: '/admin/comms/segments', label: 'Segments', icon: 'filter' },
    { to: '/admin/comms/templates', label: 'Templates', icon: 'sheet' },
    { to: '/admin/comms/settings', label: 'Email settings', icon: 'settings' },
  ]
}

export default function BetterClubhouseLayout({
  children, title, caption, onHelp, filters, stats, actions, tabs, twoRow, bare, hideHeader, storefront = false,
}) {
  const { user, hasModule } = useAuth()
  const modules = clubhouseModules(hasModule)
  const { counts } = useClubhouseData(modules)
  // `is_marketing_org` rides on /auth/me, so the shell knows which mode it is in
  // synchronously. Deriving it from a fetch would flash the club nav first, and
  // the one thing this must never be is ambiguous. The `can_switch_clubs` half
  // means an ordinary club admin can never land in this branch, even if someone
  // mis-designates a real club as the outreach org.
  const internal = !!(user?.can_switch_clubs && user?.is_marketing_org)
  const nav = internal ? buildInternalNav({ counts }) : buildNav({ modules, counts, storefront })

  return (
    <ModuleLayout
      moduleName="Admin" nav={nav}
      title={title} caption={caption} onHelp={onHelp}
      filters={filters} stats={stats} actions={actions} tabs={tabs} twoRow={twoRow}
      bare={bare} hideHeader={hideHeader}
      sidebarFooterTop={<ClubhouseContextControl />}
    >
      {children}
    </ModuleLayout>
  )
}
