import { useState, useEffect } from 'react'
import BetterClubManagerLayout, { NAV, MEMBER_PORTAL_ITEM } from '../../components/admin/BetterClubManagerLayout'
import ModuleOverviewGrid from '../../components/admin/ModuleOverviewGrid'
import { api } from '../../lib/api'

// BetterClubManager surface home — the club back-office tools, grouped.
export default function BetterClubManagerHome() {
  const [memberPortalVisible, setMemberPortalVisible] = useState(false)
  useEffect(() => {
    let alive = true
    api.memberPortalStatus()
      .then(s => { if (alive) setMemberPortalVisible(!!s?.enabled) })
      .catch(() => {})
    return () => { alive = false }
  }, [])

  const nav = memberPortalVisible
    ? (() => {
        const i = NAV.findIndex(n => n.heading === 'Club')
        return [...NAV.slice(0, i), MEMBER_PORTAL_ITEM, ...NAV.slice(i)]
      })()
    : NAV

  return (
    <BetterClubManagerLayout title="BetterClubManager">
      <p className="text-pb-faint text-sm mb-6 max-w-2xl">
        The club back office in one place. Committee and volunteers, families, events and the
        facilities and diary that keep the club running.
      </p>
      <ModuleOverviewGrid nav={nav} />
    </BetterClubManagerLayout>
  )
}
