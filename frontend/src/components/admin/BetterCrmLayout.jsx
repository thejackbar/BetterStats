import { CAP } from '../../lib/capabilities'
import ModuleLayout from './ModuleLayout'

// BetterCRM runs as its own module surface under the BetterAdmin brand —
// pipeline, deals list and contacts, away from the main admin nav.
const NAV = [
  { to: '/admin/crm', label: 'Pipeline', icon: 'overview', cap: CAP.MANAGE_CRM, exact: true },
  { to: '/admin/crm/deals', label: 'Deals', icon: 'list', cap: CAP.MANAGE_CRM },
  { to: '/admin/crm/people', label: 'Contacts', icon: 'settings', cap: CAP.MANAGE_CRM },
]

export default function BetterCrmLayout({ children, title, actions }) {
  return (
    <ModuleLayout moduleName="CRM" nav={NAV} title={title} actions={actions}>
      {children}
    </ModuleLayout>
  )
}
