import { useEffect, useState } from 'react'
import { initialsOf } from './votesTokens'

// A player's photo, or their initials when they have none or it will not load.
// Not the BetterSelect Avatar: that one links to the BetterSelect profile page
// and has no load-failure fallback, and these screens (including the football
// twin's) must not navigate away from a count.
// `accent` colours the ring and the initials (podium places, awards-night leader).
export default function VoteFace({ player, size = 26, accent, className = '' }) {
  const url = player?.photo_url
  const [failed, setFailed] = useState(false)
  useEffect(() => { setFailed(false) }, [url])

  const ring = accent
    ? `1.5px solid color-mix(in srgb, ${accent} 40%, transparent)`
    : '1px solid var(--pb-hairline2)'
  const box = { width: size, height: size, minWidth: size, border: ring }

  if (url && !failed) {
    return (
      <img src={url} alt="" loading="lazy" onError={() => setFailed(true)} data-face="photo"
        className={`rounded-full object-cover bg-pb-surface2 shrink-0 ${className}`} style={box} />
    )
  }
  return (
    <span data-face="initials" aria-hidden="true"
      className={`rounded-full bg-pb-surface2 font-mono font-semibold flex items-center justify-center shrink-0 ${className}`}
      style={{ ...box, fontSize: Math.max(8, Math.round(size * 0.34)), color: accent || 'var(--pb-dim)' }}>
      {initialsOf(player?.name)}
    </span>
  )
}
