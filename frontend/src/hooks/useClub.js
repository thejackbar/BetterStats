import { useState, useEffect } from 'react'
import { api } from '../lib/api'

/**
 * Resolves a club slug to its full club object (including UUID).
 * Returns { club, orgId, loading, inactive }.
 * `inactive` is true when the API responds with 403 (club exists but is_active=false).
 */
export function useClub(slug) {
  const [club, setClub] = useState(null)
  const [loading, setLoading] = useState(true)
  const [inactive, setInactive] = useState(false)

  useEffect(() => {
    if (!slug) { setLoading(false); return }
    setLoading(true)
    setInactive(false)
    api.getClubBySlug(slug)
      .then(c => { setClub(c); setLoading(false) })
      .catch(err => {
        if (err.message && err.message.includes('not available')) {
          setInactive(true)
        }
        setLoading(false)
      })
  }, [slug])

  return { club, orgId: club?.id || null, loading, inactive }
}
