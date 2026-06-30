import { useState, useEffect } from 'react'
import { api } from '../lib/api'

/**
 * Resolves a club slug to its full club object (including UUID).
 * Returns { club, orgId, loading, inactive, notFound }.
 * `inactive` is true when the API responds with 403 (club exists but is_active=false).
 * `notFound` is true when the slug doesn't match any club (404) — used to show the
 * "get your club online" sign-up CTA instead of a blank page.
 */
export function useClub(slug) {
  const [club, setClub] = useState(null)
  const [loading, setLoading] = useState(true)
  const [inactive, setInactive] = useState(false)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    if (!slug) { setLoading(false); return }
    setLoading(true)
    setInactive(false)
    setNotFound(false)
    api.getClubBySlug(slug)
      .then(c => {
        setClub(c)
        setLoading(false)
        if (c?.slug) sessionStorage.setItem('bs_last_slug', c.slug)
      })
      .catch(err => {
        if (err.status === 403 || (err.message && err.message.includes('not available'))) {
          setInactive(true)
        } else if (err.status === 404 || (err.message && err.message.includes('not found'))) {
          setNotFound(true)
        }
        setLoading(false)
      })
  }, [slug])

  return { club, orgId: club?.id || null, loading, inactive, notFound }
}
