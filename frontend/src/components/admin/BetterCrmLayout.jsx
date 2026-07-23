import { useState, useEffect } from 'react'
import { CAP } from '../../lib/capabilities'
import { api } from '../../lib/api'
import ModuleLayout from './ModuleLayout'

// BetterCRM runs as its own module surface under the BetterAdmin brand. Its
// pipelines are opt-in "trackers" (Sponsors / Grants / Alumni & Fundraising,
// or a fully custom one) — a club may have none, one or several, so the nav
// is built from whichever ones are actually switched on, not a fixed list.
// "Deal" stays in the underlying API/schema (plumbing, not user-facing) —
// see services/crm.py.
export default function BetterCrmLayout({ children, title, actions }) {
  const [trackers, setTrackers] = useState([])

  useEffect(() => {
    let live = true
    api.crmActiveTrackers().then(d => { if (live) setTrackers(d.trackers || []) }).catch(() => {})
    return () => { live = false }
  }, [])

  const nav = [
    { to: '/admin/crm', label: 'Overview', icon: 'overview', cap: CAP.MANAGE_CRM, exact: true },
    ...trackers.map(t => ({ to: `/admin/crm/${t.id}`, label: t.name, icon: 'list', cap: CAP.MANAGE_CRM })),
    { to: '/admin/crm/people', label: 'Contacts', icon: 'settings', cap: CAP.MANAGE_CRM },
  ]

  return (
    <ModuleLayout moduleName="CRM" nav={nav} title={title} actions={actions}>
      {children}
    </ModuleLayout>
  )
}
