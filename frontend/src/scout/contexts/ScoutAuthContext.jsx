import { createContext, useContext, useState, useEffect, useCallback } from 'react'

// Same API root as the rest of the (single) app — contexts/AuthContext.jsx
// uses this exact computation. BetterScout's routes are mounted at
// /scout/auth/* on the backend (see routers/scout/auth.py), distinct from
// the club-admin /auth/* routes so the two logins can never collide.
const API_BASE = import.meta.env.VITE_API_URL || (import.meta.env.BASE_URL + 'api')

const ScoutAuthContext = createContext(null)

/**
 * BetterScout's own auth context — deliberately NOT the shared AuthContext.
 * That one is wired to club-shaped concepts (club_id, capabilities,
 * entitlements/hasModule, coreLive) that don't exist for a Scout Org login.
 * This is the pared-down equivalent: just "who am I" against BetterScout's
 * own /scout/auth/me, backed by services/scout_auth.py's separate session
 * cookie.
 */
export function ScoutAuthProvider({ children }) {
  const [user, setUser] = useState(undefined) // undefined = loading, null = not authed

  const fetchMe = useCallback(async () => {
    try {
      const res = await fetch(API_BASE + '/scout/auth/me', { credentials: 'include' })
      setUser(res.ok ? await res.json() : null)
    } catch {
      setUser(null)
    }
  }, [])

  useEffect(() => { fetchMe() }, [fetchMe])

  const login = async (username, password) => {
    const res = await fetch(API_BASE + '/scout/auth/login', {
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
    return data
  }

  const logout = async () => {
    await fetch(API_BASE + '/scout/auth/logout', { method: 'POST', credentials: 'include' })
    setUser(null)
  }

  return (
    <ScoutAuthContext.Provider value={{ user, login, logout, refetch: fetchMe }}>
      {children}
    </ScoutAuthContext.Provider>
  )
}

export function useScoutAuth() {
  const ctx = useContext(ScoutAuthContext)
  if (!ctx) throw new Error('useScoutAuth must be used within a ScoutAuthProvider')
  return ctx
}
