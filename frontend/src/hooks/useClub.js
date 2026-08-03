import { useState, useEffect, useCallback } from 'react'
import { api } from '../lib/api'

/**
 * Resolves a club slug to its full club object (including UUID).
 * Returns { club, orgId, loading, inactive, notFound, locked, unlock, requestAccess }.
 * `inactive` is true when the API responds with 403 (club exists but is_active=false).
 * `notFound` is true when the slug doesn't match any club (404) — used to show the
 * "get your club online" sign-up CTA instead of a blank page.
 * `locked` is the structured lock payload ({reason, name, short_name, logo_url,
 * message}) when the API responds with 423 (club is password-protected and this
 * browser hasn't unlocked it yet) — see ClubPinGate.jsx.
 */
export function useClub(slug) {
  const [club, setClub] = useState(null)
  const [loading, setLoading] = useState(true)
  const [inactive, setInactive] = useState(false)
  const [notFound, setNotFound] = useState(false)
  const [locked, setLocked] = useState(null)

  const load = useCallback(() => {
    if (!slug) { setLoading(false); return }
    setLoading(true)
    setInactive(false)
    setNotFound(false)
    setLocked(null)
    api.getClubBySlug(slug)
      .then(c => {
        setClub(c)
        setLoading(false)
        if (c?.slug) sessionStorage.setItem('bs_last_slug', c.slug)
      })
      .catch(err => {
        if (err.status === 423 && err.detail) {
          setLocked(err.detail)
        } else if (err.status === 403 || (err.message && err.message.includes('not available'))) {
          setInactive(true)
        } else if (err.status === 404 || (err.message && err.message.includes('not found'))) {
          setNotFound(true)
        }
        setLoading(false)
      })
  }, [slug])

  useEffect(() => { load() }, [load])

  const unlock = useCallback(async (pin) => {
    await api.unlockClub(slug, pin)
    load()
  }, [slug, load])

  const requestAccess = useCallback((email, message) => api.requestClubUnpause(slug, email, message), [slug])

  return { club, orgId: club?.id || null, loading, inactive, notFound, locked, unlock, requestAccess }
}
