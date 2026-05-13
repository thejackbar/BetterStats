import { useState, useEffect } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import AchievementsAdmin from '../AchievementsAdmin'

export default function AdminAwards() {
  const { user } = useAuth()
  const [orgId, setOrgId] = useState(null)

  useEffect(() => {
    if (user?.club_id) {
      setOrgId(user.club_id)
    } else {
      // Fetch from settings for super_admin who may not have club_id in token
      api.adminGetSettings().then(s => setOrgId(s.id)).catch(() => {})
    }
  }, [user])

  if (!orgId) return (
    <AdminLayout>
      <div className="font-mono text-[11px] text-pb-faint">Loading…</div>
    </AdminLayout>
  )

  return (
    <AdminLayout>
      <AchievementsAdmin embeddedOrgId={orgId} />
    </AdminLayout>
  )
}
