import { CAP } from '../../lib/capabilities'
import ModuleLayout from './ModuleLayout'

// BetterFantasyCricket runs as its own module surface (cyan), like BetterSelect
// and BetterIQ. The member-facing play lives on the public link; this is the
// admin's setup and oversight. More pages (leagues, draft) land in later phases.
const NAV = [
  { to: '/admin/fantasy', label: 'Overview', icon: 'overview', cap: CAP.MANAGE_FANTASY, exact: true },
  { to: '/admin/fantasy/leagues', label: 'Draft leagues', icon: 'ladders', cap: CAP.MANAGE_FANTASY },
]

export default function BetterFantasyLayout({ children, title, actions }) {
  return (
    <ModuleLayout moduleName="FantasyCricket" nav={NAV} title={title} actions={actions}>
      {children}
    </ModuleLayout>
  )
}
