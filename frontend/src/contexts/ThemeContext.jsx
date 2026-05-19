import { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react'

/**
 * Light/dark theme state.
 *
 * Resolution order:
 *   1. Visitor override (localStorage 'bs_theme') — set via the navbar toggle.
 *   2. The club's admin default (theme_mode: 'light' | 'dark' | 'auto').
 *   3. 'auto' falls back to the OS colour-scheme preference.
 *
 * useClubTheme() feeds the club default in via setClubDefault().
 */

const ThemeContext = createContext(null)
const STORAGE_KEY = 'bs_theme'

const systemTheme = () =>
  window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'

export function ThemeProvider({ children }) {
  const [override, setOverride] = useState(() => {
    const v = localStorage.getItem(STORAGE_KEY)
    return v === 'light' || v === 'dark' ? v : null
  })
  const [clubDefault, setClubDefault] = useState('dark')

  const resolved = useMemo(() => {
    if (override) return override
    if (clubDefault === 'auto') return systemTheme()
    return clubDefault === 'light' ? 'light' : 'dark'
  }, [override, clubDefault])

  useEffect(() => {
    document.documentElement.dataset.theme = resolved
  }, [resolved])

  // Track the OS preference while following 'auto' with no visitor override.
  useEffect(() => {
    if (override || clubDefault !== 'auto') return
    const mq = window.matchMedia('(prefers-color-scheme: light)')
    const onChange = () => {
      document.documentElement.dataset.theme = systemTheme()
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [override, clubDefault])

  const setOverridePersisted = useCallback((value) => {
    if (value === 'light' || value === 'dark') {
      localStorage.setItem(STORAGE_KEY, value)
      setOverride(value)
    } else {
      localStorage.removeItem(STORAGE_KEY)
      setOverride(null)
    }
  }, [])

  const toggle = useCallback(() => {
    setOverridePersisted(resolved === 'dark' ? 'light' : 'dark')
  }, [resolved, setOverridePersisted])

  const value = useMemo(() => ({
    theme: resolved,
    isOverridden: override !== null,
    toggle,
    setTheme: setOverridePersisted,
    clearOverride: () => setOverridePersisted(null),
    setClubDefault,
  }), [resolved, override, toggle, setOverridePersisted])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider')
  return ctx
}
