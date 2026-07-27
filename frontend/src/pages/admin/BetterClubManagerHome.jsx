import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import BetterClubManagerLayout, { withPortal } from '../../components/admin/BetterClubManagerLayout'
import ModuleHub from '../../components/admin/ModuleHub'
import { api } from '../../lib/api'

// BetterClubManager surface home. /admin/betterclub shows the group cards;
// /admin/betterclub/:group shows that group's tools. Member Portal appears in
// the People group only when its platform flag is on.
export default function BetterClubManagerHome() {
  const { group } = useParams()
  const [memberPortalVisible, setMemberPortalVisible] = useState(false)
  useEffect(() => {
    let alive = true
    api.memberPortalStatus()
      .then(s => { if (alive) setMemberPortalVisible(!!s?.enabled) })
      .catch(() => {})
    return () => { alive = false }
  }, [])

  return (
    <BetterClubManagerLayout title="BetterClubManager">
      {!group && (
        <p className="text-pb-faint text-sm mb-6 max-w-2xl">
          The club back office in one place. Committee and volunteers, families, events and the
          facilities and diary that keep the club running.
        </p>
      )}
      <ModuleHub groups={withPortal(memberPortalVisible)} basePath="/admin/betterclub" groupKey={group} />
    </BetterClubManagerLayout>
  )
}
