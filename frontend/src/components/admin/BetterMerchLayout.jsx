import { useState, useEffect } from 'react'
import { CAP } from '../../lib/capabilities'
import { api } from '../../lib/api'
import ModuleLayout from './ModuleLayout'

// BetterMerch runs as its own module surface under the BetterAdmin brand —
// stock, equipment, activity and reports grouped together, away from the main
// admin nav.
const BASE_NAV = [
  { to: '/admin/merch', label: 'Overview', icon: 'overview', cap: CAP.MANAGE_MERCH, exact: true },
  { to: '/admin/merch/stock', label: 'Stock', icon: 'list', cap: CAP.MANAGE_MERCH },
  { to: '/admin/merch/equipment', label: 'Equipment', icon: 'settings', cap: CAP.MANAGE_MERCH },
  { to: '/admin/merch/activity', label: 'Activity', icon: 'sheet', cap: CAP.MANAGE_MERCH },
  { to: '/admin/merch/reports', label: 'Reports', icon: 'ladders', cap: CAP.MANAGE_MERCH },
  { to: '/admin/merch/square', label: 'Square', icon: 'share', cap: CAP.MANAGE_MERCH },
]
const ORDERS_NAV_ITEM = { to: '/admin/merch/orders', label: 'Online Store', icon: 'sheet', cap: CAP.MANAGE_MERCH }

export default function BetterMerchLayout({ children, title, actions }) {
  // Merch storefront (migration 179) — off by default; per direct
  // instruction invisible until a super admin switches
  // platform_settings.merch_storefront_enabled on (globally or for this
  // club). Every viewer here already holds MANAGE_MERCH, so this is the
  // only extra gate the "Online Store" tab needs.
  const [storefrontEnabled, setStorefrontEnabled] = useState(false)
  useEffect(() => {
    let cancelled = false
    api.merchStorefrontStatus()
      .then(s => { if (!cancelled) setStorefrontEnabled(!!s?.enabled) })
      .catch(() => { if (!cancelled) setStorefrontEnabled(false) })
    return () => { cancelled = true }
  }, [])

  const nav = storefrontEnabled ? [...BASE_NAV, ORDERS_NAV_ITEM] : BASE_NAV

  return (
    <ModuleLayout moduleName="Merch" nav={nav} title={title} actions={actions}>
      {children}
    </ModuleLayout>
  )
}
