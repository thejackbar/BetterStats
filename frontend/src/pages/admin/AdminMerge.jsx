import { useState, useEffect } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
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
    <AdminLayout>
      <div className="text-slate-400 text-sm">Loading…</div>
    </AdminLayout>
  )

  return (
    <AdminLayout>
      <MergeTools embeddedOrgId={orgId} />
    </AdminLayout>
  )
}
