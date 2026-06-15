import { CAP } from '../../lib/capabilities'
import ModuleLayout from './ModuleLayout'

// BetterMerch runs as its own module surface under the BetterAdmin brand —
// stock, equipment, activity and reports grouped together, away from the main
// admin nav.
const NAV = [
  { to: '/admin/merch', label: 'Overview', icon: 'overview', cap: CAP.MANAGE_MERCH, exact: true },
  { to: '/admin/merch/stock', label: 'Stock', icon: 'list', cap: CAP.MANAGE_MERCH },
  { to: '/admin/merch/equipment', label: 'Equipment', icon: 'settings', cap: CAP.MANAGE_MERCH },
  { to: '/admin/merch/activity', label: 'Activity', icon: 'sheet', cap: CAP.MANAGE_MERCH },
  { to: '/admin/merch/reports', label: 'Reports', icon: 'ladders', cap: CAP.MANAGE_MERCH },
]

export default function BetterMerchLayout({ children, title, actions }) {
  return (
    <ModuleLayout moduleName="Merch" nav={NAV} title={title} actions={actions}>
      {children}
    </ModuleLayout>
  )
}
