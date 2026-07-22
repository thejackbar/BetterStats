import { CAP } from '../../lib/capabilities'
import ModuleLayout from './ModuleLayout'

// BetterCRM runs as its own module surface under the BetterAdmin brand.
// Launched scoped to Sponsors (the relationship-tracking need with the
// clearest demand — see the "Pipeline/Deals" terminology discussion this
// naming came out of); nav labels are plain words a club officer already
// uses, not sales-pipeline jargon. "Deal" stays in the underlying API/schema
// (plumbing, not user-facing) — see services/crm.py.
const NAV = [
  { to: '/admin/crm', label: 'Sponsors', icon: 'overview', cap: CAP.MANAGE_CRM, exact: true },
  { to: '/admin/crm/list', label: 'All Sponsors', icon: 'list', cap: CAP.MANAGE_CRM },
  { to: '/admin/crm/people', label: 'Contacts', icon: 'settings', cap: CAP.MANAGE_CRM },
]

export default function BetterCrmLayout({ children, title, actions }) {
  return (
    <ModuleLayout moduleName="CRM" nav={NAV} title={title} actions={actions}>
      {children}
    </ModuleLayout>
  )
}
