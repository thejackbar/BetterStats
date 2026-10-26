// The look a club's cards are drawn in: its accent colour, and its own display font when it has chosen one (an
// uploaded font gets its @font-face added for as long as the cards are on screen).
import { useEffect, useMemo } from 'react'
import { buildFontFaceCss, resolveClubFonts } from '../../lib/theme'
import { DEFAULT_DISPLAY } from './CardFaces'

export function useCardStyle(club) {
  const accent = club?.accent_color || club?.primary_color || '#16c784'
  const fonts = useMemo(() => resolveClubFonts(club), [club])
  const fontCss = useMemo(() => buildFontFaceCss(fonts), [fonts])
  const display = fonts.display?.cssFamily || DEFAULT_DISPLAY
  useEffect(() => {
    if (!fontCss) return undefined
    const el = document.createElement('style')
    el.setAttribute('data-club-card-fonts', '')
    el.textContent = fontCss
    document.head.appendChild(el)
    return () => el.remove()
  }, [fontCss])
  return { accent, display }
}
