import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import BetterClubhouseLayout from './BetterClubhouseLayout'

// The Merch screens are the Stock section of BetterClubhouse now. The one thing
// this wrapper still owns is the storefront flag (migration 179) — "Online
// store" stays invisible until a super admin switches
// platform_settings.merch_storefront_enabled on (globally or for this club), so
// the merged sidebar has to be told whether to show it. Every viewer here
// already holds MANAGE_MERCH, so that flag is the only extra gate it needs.
export default function BetterMerchLayout(props) {
  const [storefront, setStorefront] = useState(false)
  useEffect(() => {
    let cancelled = false
    api.merchStorefrontStatus()
      .then(s => { if (!cancelled) setStorefront(!!s?.enabled) })
      .catch(() => { if (!cancelled) setStorefront(false) })
    return () => { cancelled = true }
  }, [])

  return <BetterClubhouseLayout storefront={storefront} {...props} />
}
