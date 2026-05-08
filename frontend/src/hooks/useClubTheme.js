import { useEffect } from 'react'

/**
 * Injects a <style> tag overriding the site's accent colour with the club's
 * primary_color setting. Cleans up on unmount so non-club pages stay green.
 */
export function useClubTheme(club) {
  useEffect(() => {
    const colour = club?.accent_color
    if (!colour) return

    const existing = document.getElementById('club-theme')
    if (existing) existing.remove()

    const style = document.createElement('style')
    style.id = 'club-theme'
    style.textContent = `
      .text-accent { color: ${colour} !important; }
      .bg-accent, .btn-primary { background-color: ${colour} !important; }
      .border-accent { border-color: ${colour} !important; }
      .hover\\:text-accent:hover { color: ${colour} !important; }
      .accent-bar { background-color: ${colour} !important; }
    `
    document.head.appendChild(style)

    return () => { document.getElementById('club-theme')?.remove() }
  }, [club?.accent_color])
}
