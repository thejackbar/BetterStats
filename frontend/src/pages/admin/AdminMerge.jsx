import { useState, useEffect } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { api } from '../../lib/api'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import MergeTools from '../MergeTools'

export default function AdminMerge() {
  const { user } = useAuth()
  const [orgId, setOrgId] = useState(null)

  useEffect(() => {
    if (user?.club_id) {
      setOrgId(user.club_id)
    } else {
      api.adminGetSettings().then(s => setOrgId(s.id)).catch(() => {})
    }
  }, [user])

  if (!orgId) return (
    <BetterStatsLayout>
      <div className="font-mono text-[11px] text-pb-faint">Loading…</div>
    </BetterStatsLayout>
  )

  return (
    <BetterStatsLayout>
      <MergeTools embeddedOrgId={orgId} />
    </BetterStatsLayout>
  )
}
