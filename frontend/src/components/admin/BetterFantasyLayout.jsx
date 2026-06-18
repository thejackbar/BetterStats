import { CAP } from '../../lib/capabilities'
import ModuleLayout from './ModuleLayout'

// BetterFantasyCricket runs as its own module surface (cyan), like BetterSelect
// and BetterIQ. The member-facing play lives on the public link; this is the
// admin's setup and oversight, split into focused pages so no one screen is a
// long scroll.
const NAV = [
  { to: '/admin/fantasy', label: 'Overview', icon: 'overview', cap: CAP.MANAGE_FANTASY, exact: true },
  { to: '/admin/fantasy/settings', label: 'Team & budget', icon: 'settings', cap: CAP.MANAGE_FANTASY },
  { to: '/admin/fantasy/scoring', label: 'Scoring', icon: 'bolt', cap: CAP.MANAGE_FANTASY },
  { to: '/admin/fantasy/pool', label: 'Player pool', icon: 'list', cap: CAP.MANAGE_FANTASY },
  { to: '/admin/fantasy/players', label: 'Registered players', icon: 'teams', cap: CAP.MANAGE_FANTASY },
  { to: '/admin/fantasy/leagues', label: 'Draft leagues', icon: 'ladders', cap: CAP.MANAGE_FANTASY },
]

export default function BetterFantasyLayout({ children, title, actions }) {
  return (
    <ModuleLayout moduleName="FantasyCricket" nav={NAV} title={title} actions={actions}>
      {children}
    </ModuleLayout>
  )
}
