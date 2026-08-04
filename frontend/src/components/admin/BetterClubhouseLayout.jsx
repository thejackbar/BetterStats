import { useAuth } from '../../contexts/AuthContext'
import { CAP } from '../../lib/capabilities'
import { useClubhouseData, clubhouseModules } from '../../pages/admin/clubhouse/data'
import ModuleLayout from './ModuleLayout'

// BetterClubhouse — the club's back office as ONE module.
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
//   super  — the promoted ClubManager screens. They run on real data, but are
//            still gated to super_admin in App.jsx while their CRUD is
//            finished, so the nav must hide them the same way.
// A heading whose items all fall away is dropped by ModuleLayout, so a
// treasurer holding only BetterFees sees Today, Money and nothing else.

function buildNav({ modules, isSuper, counts, storefront }) {
  return [
    { to: '/admin/clubhouse', label: 'Today', icon: 'overview', exact: true, badge: counts.needsYou },

    { heading: 'People' },
    { to: '/admin/clubhouse/directory', label: 'Directory', icon: 'teams', super: true },
    { to: '/admin/clubhouse/roster', label: 'Roster', icon: 'fixtures', super: true },
    { to: '/admin/committee', label: 'Committee', icon: 'sheet', super: true },

    { heading: 'Money' },
    { to: '/admin/fees', label: 'Accounts', icon: 'money', cap: CAP.MANAGE_FEES, module: 'fees', exact: true, badge: counts.owing },
    { to: '/admin/fees/payments', label: 'Payments', icon: 'list', cap: CAP.MANAGE_FEES, module: 'fees' },
    { to: '/admin/fees/schedule', label: 'Rate card', icon: 'sheet', cap: CAP.MANAGE_FEES, module: 'fees' },

    { heading: 'Stock' },
    { to: '/admin/merch/stock', label: 'Inventory', icon: 'list', cap: CAP.MANAGE_MERCH, module: 'merch', badge: counts.reorder },
    { to: '/admin/merch/equipment', label: 'Equipment', icon: 'settings', cap: CAP.MANAGE_MERCH, module: 'merch' },
    ...(storefront ? [{ to: '/admin/merch/orders', label: 'Online store', icon: 'sheet', cap: CAP.MANAGE_MERCH, module: 'merch' }] : []),

    { heading: 'Comms' },
    { to: '/admin/comms', label: 'Emails', icon: 'list', cap: CAP.MANAGE_COMMS, module: 'comms', exact: true, badge: counts.drafts },
    { to: '/admin/clubhouse/audiences', label: 'Audiences', icon: 'filter', cap: CAP.MANAGE_COMMS, module: 'comms' },

    { heading: 'Club' },
    { to: '/admin/club-diary', label: 'Diary', icon: 'ladders', super: true },
    { to: '/admin/events', label: 'Events', icon: 'timer', super: true },
    { to: '/admin/assets', label: 'Facilities', icon: 'nets', super: true },

    { heading: 'Setup' },
    // The catalogue every other screen reads from: roles (a committee-flagged
    // role IS a committee position), activities, qualification types,
    // operational areas. Dropping it from the sidebar left the whole
    // configuration layer unreachable except by typing a URL.
    { to: '/admin/clubhouse/areas-roles', label: 'Areas & roles', icon: 'settings', super: true },
    { to: '/admin/clubhouse/integrations', label: 'Integrations', icon: 'share', cap: [CAP.MANAGE_FEES, CAP.MANAGE_MERCH, CAP.MANAGE_COMMS] },
    { to: '/admin/clubhouse/reports', label: 'Reports', icon: 'ladders', cap: [CAP.MANAGE_FEES, CAP.MANAGE_MERCH] },
    { to: '/admin/clubhouse/settings', label: 'Settings', icon: 'settings' },
  ].filter(i => {
    if (i.heading) return true
    if (i.super && !isSuper) return false
    if (i.module && !modules[i.module]) return false
    return true
  })
}

export default function BetterClubhouseLayout({
  children, title, caption, onHelp, filters, stats, actions, bare, hideHeader, storefront = false,
}) {
  const { user, hasModule } = useAuth()
  const modules = clubhouseModules(hasModule)
  const { counts } = useClubhouseData(modules)
  const nav = buildNav({ modules, isSuper: user?.role === 'super_admin', counts, storefront })

  return (
    <ModuleLayout
      moduleName="Clubhouse" nav={nav}
      title={title} caption={caption} onHelp={onHelp}
      filters={filters} stats={stats} actions={actions} bare={bare} hideHeader={hideHeader}
    >
      {children}
    </ModuleLayout>
  )
}
