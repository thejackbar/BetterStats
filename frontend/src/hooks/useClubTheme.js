import { useEffect } from 'react'
import { buildThemeCss } from '../lib/theme'
import { useTheme } from '../contexts/ThemeContext'

/**
 * Applies a club's white-label theme:
 *  - injects a <style id="club-theme"> tag with the club's full colour
 *    palette (accent, indicators, chart series, light + dark surfaces)
 *  - feeds the club's admin-default theme mode into ThemeContext
 *
 * Cleans up on unmount so non-club pages fall back to BetterStats defaults.
 */
export function useClubTheme(club) {
  const { setClubDefault } = useTheme()

  useEffect(() => {
    if (!club) return

    const css = buildThemeCss(club.theme_config)
    let style = document.getElementById('club-theme')
    if (!style) {
      style = document.createElement('style')
      style.id = 'club-theme'
      document.head.appendChild(style)
    }
    style.textContent = css

    return () => { document.getElementById('club-theme')?.remove() }
  }, [club?.theme_config, club?.accent_color])

  useEffect(() => {
    if (!club) return
    const mode = club.theme_mode
    setClubDefault(mode === 'light' || mode === 'dark' ? mode : 'auto')
    // Reset to the BetterStats default on unmount — otherwise a club's
    // light/auto theme_mode keeps applying to whatever the visitor navigates
    // to next (including the always-dark marketing site).
    return () => setClubDefault('dark')
  }, [club?.theme_mode, setClubDefault])
}
