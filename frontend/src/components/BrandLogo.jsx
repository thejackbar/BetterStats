import { useTheme } from '../contexts/ThemeContext'
import brandWhite from '../assets/bettercricket-white.svg'
import brandBlack from '../assets/bettercricket-black.svg'

/**
 * Better Cricket logo that flips with the active theme:
 *   dark mode  → white logo (white bars)
 *   light mode → black logo (black bars)
 * The green "B" is constant; only the bar/contrast colour swaps so the mark
 * stays legible on whichever surface it sits on.
 *
 * Used wherever the platform brand mark appears (nav, admin header, "powered
 * by" footers). Pass `alt=""` for decorative placements.
 */
export default function BrandLogo({ className = '', alt = 'Better Cricket', ...rest }) {
  const { theme } = useTheme()
  return (
    <img
      src={theme === 'light' ? brandBlack : brandWhite}
      alt={alt}
      className={className}
      {...rest}
    />
  )
}
