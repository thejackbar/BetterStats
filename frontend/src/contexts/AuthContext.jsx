import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { clearAttribution } from '../lib/visitor'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined) // undefined = loading, null = not authed
  const [justLoggedIn, setJustLoggedIn] = useState(false)

  const fetchMe = useCallback(async () => {
    try {
      const res = await fetch('/api/auth/me', { credentials: 'include' })
      if (res.ok) {
        setUser(await res.json())
      } else {
        setUser(null)
      }
    } catch {
      setUser(null)
    }
  }, [])

  useEffect(() => { fetchMe() }, [fetchMe])

  const login = async (username, password) => {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Login failed' }))
      throw new Error(err.detail || 'Login failed')
    }
    const data = await res.json()
    setUser(data)
    setJustLoggedIn(true)
    // A stale marketing UTM sitting in this tab (e.g. from testing/copying a
    // club's own outreach link) shouldn't keep riding along on this staff
    // member's admin browsing from here on.
    clearAttribution()
    return data
  }

  // Club-user invite accept (routers/auth.py::accept_invite) — sets the
  // invited admin's own password and logs them in, the same shape login()
  // itself uses (the backend response is a _build_me payload either way).
  const acceptInvite = async (token, password, confirmPassword) => {
    const res = await fetch(`/api/auth/invite/${token}/accept`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password, confirm_password: confirmPassword }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Could not set your password' }))
      const detail = err.detail
      const message = Array.isArray(detail?.errors) ? detail.errors.join(' ') : (detail || 'Could not set your password')
      throw new Error(message)
    }
    const data = await res.json()
    setUser(data)
    setJustLoggedIn(true)
    clearAttribution()
    return data
  }

  const logout = async () => {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
    setUser(null)
  }

  // Super-admin club switching. Persists the acted-as club server-side, then
  // hard-reloads into the admin dashboard so every page refetches under the new
  // club scope (a soft context update would leave already-mounted pages showing
  // the previous club's data). Pass null to return to the home club.
  const switchClub = useCallback(async (clubId) => {
    const res = await fetch('/api/auth/switch-club', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ club_id: clubId ?? null }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Could not switch club' }))
      throw new Error(err.detail || 'Could not switch club')
    }
    // Keep slug-derived UI (the public navbar's club fallback) in step with the
    // club we just switched into.
    const data = await res.json().catch(() => null)
    if (data?.club_slug) {
      try { sessionStorage.setItem('bs_last_slug', data.club_slug) } catch {}
    }
    window.location.assign('/admin')
  }, [])

  const clearJustLoggedIn = useCallback(() => setJustLoggedIn(false), [])

  // super_admin / club_admin implicitly have everything (backend sends the
  // expanded list anyway, but checking role short-circuits race conditions
  // where the role is set but capabilities haven't arrived yet).
  const hasCapability = useCallback((cap) => {
    if (!user) return false
    if (user.role === 'super_admin' || user.role === 'club_admin') return true
    return Array.isArray(user.capabilities) && user.capabilities.includes(cap)
  }, [user])

  // Module entitlement — the club's explicit module list, sent by the backend
  // on /auth/me + /auth/login as `entitlements.modules`. Super admins act
  // cross-club and are entitled to everything.
  const hasModule = useCallback((moduleKey) => {
    if (!user) return false
    if (user.role === 'super_admin') return true
    // Backward-compat / fail-open: an older backend (or a not-yet-migrated one)
    // doesn't send `entitlements` at all. Don't hide the modules in that case —
    // only gate when the backend explicitly provides the modules list. A club
    // with no modules still gets an (empty) modules array, so real gating is
    // unaffected.
    const mods = user.entitlements?.modules
    if (!Array.isArray(mods)) return true
    return mods.includes(moduleKey)
  }, [user])

  return (
    <AuthContext.Provider value={{ user, login, logout, switchClub, acceptInvite, refetch: fetchMe, justLoggedIn, clearJustLoggedIn, hasCapability, hasModule }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
