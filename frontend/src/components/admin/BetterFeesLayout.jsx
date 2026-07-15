import { CAP } from '../../lib/capabilities'
import ModuleLayout from './ModuleLayout'

// BetterFees runs as its own module surface — members, payments, schedule and
// reports grouped together, away from the main admin nav.
const NAV = [
  { to: '/admin/fees', label: 'Members', icon: 'teams', cap: CAP.MANAGE_FEES, exact: true },
  { to: '/admin/fees/payments', label: 'Payments', icon: 'money', cap: CAP.MANAGE_FEES },
  { to: '/admin/fees/schedule', label: 'Fee Schedule', icon: 'list', cap: CAP.MANAGE_FEES },
  { to: '/admin/fees/reports', label: 'Reports', icon: 'ladders', cap: CAP.MANAGE_FEES },
  { to: '/admin/fees/square', label: 'Square', icon: 'share', cap: CAP.MANAGE_FEES },
]

export default function BetterFeesLayout({ children, title, actions }) {
  return (
    <ModuleLayout moduleName="Fees" nav={NAV} title={title} actions={actions}>
      {children}
    </ModuleLayout>
  )
}
