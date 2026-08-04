import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { clearAttribution } from '../lib/visitor'
import { coreLiveFromPlan } from '../lib/modules'

// Base-path aware API root ('/api' for cricket; '/afl/api' under a silo's
// path prefix). Mirrors lib/api.js's BASE.
const API_BASE = import.meta.env.VITE_API_URL || (import.meta.env.BASE_URL + 'api')

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined) // undefined = loading, null = not authed
  const [justLoggedIn, setJustLoggedIn] = useState(false)
  // Per-module account plan, fetched once per club — the reliable source for
  // coreLive below. account_plan_status reflects a lapsed BetterStats (Core) as
  // 'trial_expired' on ANY backend version, so this doesn't depend on the
  // /auth/me `core_live` flag (which a pre-upgrade backend or a stale /auth/me
  // may omit). ProtectedRoute, the admin sidebar and the dashboard all gate on
  // the resulting coreLive, so all three agree and self-heal.
  const [accountPlan, setAccountPlan] = useState(null)

  const fetchMe = useCallback(async () => {
    try {
      const res = await fetch(API_BASE + '/auth/me', { credentials: 'include' })
      if (res.ok) {
        setUser(await res.json())
        // A flow that mints a session server-side and then hard-reloads
        // (rather than calling login() itself — e.g. the self-serve trial
        // modal's "Log in as new admin") leaves a marker here so this first
        // post-reload fetch still counts as a fresh login for the bell /
        // onboarding wizard auto-open checks, which only run on justLoggedIn.
        try {
          if (sessionStorage.getItem('bs_pending_fresh_login')) {
            sessionStorage.removeItem('bs_pending_fresh_login')
            setJustLoggedIn(true)
          }
        } catch { /* sessionStorage unavailable — skip */ }
      } else {
        setUser(null)
      }
    } catch {
      setUser(null)
    }
  }, [])

  useEffect(() => { fetchMe() }, [fetchMe])

  useEffect(() => {
    if (!user || user.role === 'super_admin' || !user.club_id) { setAccountPlan(null); return }
    let alive = true
    fetch(API_BASE + '/club-admin/account/plan', { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (alive) setAccountPlan(Array.isArray(d?.modules) ? d.modules : null) })
      .catch(() => {})
    return () => { alive = false }
  }, [user?.club_id, user?.role])

  const login = async (username, password) => {
    const res = await fetch(API_BASE + '/auth/login', {
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
    const res = await fetch(`${API_BASE}/auth/invite/${token}/accept`, {
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

  // Admin-triggered password reset accept (routers/auth.py::accept_password_reset)
  // — same shape as acceptInvite, but for an EXISTING account (a club admin
  // clicked "Send password reset email" on this user from Club Users).
  const resetPassword = async (token, password, confirmPassword) => {
    const res = await fetch(`${API_BASE}/auth/reset-password/${token}/accept`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password, confirm_password: confirmPassword }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Could not reset your password' }))
      const detail = err.detail
      const message = Array.isArray(detail?.errors) ? detail.errors.join(' ') : (detail || 'Could not reset your password')
      throw new Error(message)
    }
    const data = await res.json()
    setUser(data)
    setJustLoggedIn(true)
    clearAttribution()
    return data
  }

  const logout = async () => {
    await fetch(API_BASE + '/auth/logout', { method: 'POST', credentials: 'include' })
    setUser(null)
  }

  // Super-admin club switching. Persists the acted-as club server-side, then
  // hard-reloads into the admin dashboard so every page refetches under the new
  // club scope (a soft context update would leave already-mounted pages showing
  // the previous club's data). Pass null to return to the home club.
  const switchClub = useCallback(async (clubId) => {
    const res = await fetch(API_BASE + '/auth/switch-club', {
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
    // Core is a hard prerequisite: if BetterStats isn't live, no add-on is
    // usable either, whatever its own state. The backend already drops modules
    // to an empty list in this case (org_entitled_modules), so this is belt-and-
    // braces — but it also gates instantly, before entitlements are re-fetched.
    if (user.entitlements?.core_live === false) return false
    // Backward-compat / fail-open: an older backend (or a not-yet-migrated one)
    // doesn't send `entitlements` at all. Don't hide the modules in that case —
    // only gate when the backend explicitly provides the modules list. A club
    // with no modules still gets an (empty) modules array, so real gating is
    // unaffected.
    const mods = user.entitlements?.modules
    if (!Array.isArray(mods)) return true
    return mods.includes(moduleKey)
  }, [user])

  // Whether BetterStats (Core) is live — gates the club's BetterStats admin
  // surfaces (routes + dashboard tile). A lapsed Core trial / cancelled Core
  // subscription reads false. Super admins act cross-club and are never gated.
  // Fail-open when the backend doesn't send the flag (older/not-migrated) or
  // before entitlements arrive, so we never wrongly lock a live club.
  const coreLive = (() => {
    if (!user) return false
    if (user.role === 'super_admin') return true
    // Prefer the account-plan-derived signal (reliable across backend versions
    // / a stale /auth/me); fall back to the /auth/me flag, then fail open so a
    // legacy club or an unloaded plan is never wrongly locked.
    const fromPlan = coreLiveFromPlan(accountPlan)
    if (fromPlan !== null) return fromPlan
    return user.entitlements?.core_live ?? true
  })()

  return (
    <AuthContext.Provider value={{ user, login, logout, switchClub, acceptInvite, resetPassword, refetch: fetchMe, justLoggedIn, clearJustLoggedIn, hasCapability, hasModule, coreLive }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
