import { CAP } from '../../lib/capabilities'
import ModuleLayout from './ModuleLayout'
import CommsContextBar from './CommsContextBar'

// BetterComms — bulk email — runs as its own module surface (part of the
// BetterAdmin umbrella), mirroring BetterFees.
const NAV = [
  { to: '/admin/comms', label: 'Emails', icon: 'list', cap: CAP.MANAGE_COMMS, exact: true },
  { to: '/admin/comms/contacts', label: 'Contacts', icon: 'teams', cap: CAP.MANAGE_COMMS },
  { to: '/admin/comms/settings', label: 'Settings', icon: 'settings', cap: CAP.MANAGE_COMMS },
]

export default function BetterCommsLayout({ children, title, actions }) {
  return (
    <ModuleLayout moduleName="Comms" nav={NAV} title={title} actions={actions}>
      <CommsContextBar />
      {children}
    </ModuleLayout>
  )
}
