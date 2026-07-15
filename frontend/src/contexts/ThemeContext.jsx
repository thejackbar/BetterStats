import { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react'
import { useLocation } from 'react-router-dom'
import { isMarketingPath } from '../lib/marketingPaths'

/**
 * Light/dark theme state.
 *
 * Resolution order:
 *   1. The BetterCricket marketing site is always dark, regardless of any
 *      visitor override or leftover club default from a prior page — see
 *      `onMarketingPath` below.
 *   2. Visitor override (localStorage 'bs_theme') — set via the navbar toggle.
 *   3. The club's admin default (theme_mode: 'light' | 'dark' | 'auto').
 *   4. 'auto' falls back to the OS colour-scheme preference.
 *
 * useClubTheme() feeds the club default in via setClubDefault().
 */

const ThemeContext = createContext(null)
const STORAGE_KEY = 'bs_theme'

const systemTheme = () =>
  window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'

export function ThemeProvider({ children }) {
  const { pathname } = useLocation()
  const onMarketingPath = isMarketingPath(pathname)
  const [override, setOverride] = useState(() => {
    const v = localStorage.getItem(STORAGE_KEY)
    return v === 'light' || v === 'dark' ? v : null
  })
  const [clubDefault, setClubDefault] = useState('dark')

  const resolved = useMemo(() => {
    if (onMarketingPath) return 'dark'
    if (override) return override
    if (clubDefault === 'auto') return systemTheme()
    return clubDefault === 'light' ? 'light' : 'dark'
  }, [onMarketingPath, override, clubDefault])

  useEffect(() => {
    document.documentElement.dataset.theme = resolved
  }, [resolved])

  // Track the OS preference while following 'auto' with no visitor override
  // and off the (always-dark) marketing site.
  useEffect(() => {
    if (onMarketingPath || override || clubDefault !== 'auto') return
    const mq = window.matchMedia('(prefers-color-scheme: light)')
    const onChange = () => {
      document.documentElement.dataset.theme = systemTheme()
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [onMarketingPath, override, clubDefault])

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
