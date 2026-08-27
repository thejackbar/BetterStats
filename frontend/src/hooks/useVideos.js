import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useAuth } from '../contexts/AuthContext'

/**
 * The instructional video library.
 *
 * Reads the PUBLIC endpoint even for a super admin, deliberately: the manager
 * and the page a visitor sees must never disagree about what is published or
 * what order it is in, and the public list is already the same rows in the
 * same order. The admin endpoints are writes only.
 *
 * `canManage` is presentation. Every write is re-checked server-side, so this
 * flag decides whether the controls are drawn, never whether they are allowed.
 */
export function useVideos() {
  const { user } = useAuth()
  const canManage = user?.role === 'super_admin'

  const [videos, setVideos] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    return api.publicVideos()
      .then((r) => { setVideos(Array.isArray(r?.videos) ? r.videos : []); setError(null) })
      .catch((e) => setError(e.message || 'Could not load the videos.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  return { videos, setVideos, loading, error, reload: load, canManage }
}
