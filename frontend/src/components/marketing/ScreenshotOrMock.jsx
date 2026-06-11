import { useState } from 'react'
import ZoomableImage from './ZoomableImage'

/**
 * Try to load a screenshot from /public/marketing/. If the file doesn't exist
 * (404) the onError fires and we fall back to the polished mock component.
 *
 * Usage:
 *   <ScreenshotOrMock
 *     src="/marketing/leaderboard.png"
 *     alt="Leaderboard"
 *     fallback={<MockLeaderboard />}
 *   />
 *
 * This means the marketing site looks great from day one (mocks) and
 * auto-upgrades to real screenshots the moment you drop a PNG in /public/marketing/.
 *
 * Real screenshots are click-to-enlarge by default (they're shown small on the
 * page). Pass `zoomable={false}` to opt out, or `caption` to label the enlarged
 * view. Mock fallbacks are never zoomable (there's no detail to reveal).
 */
export default function ScreenshotOrMock({ src, alt, fallback, className = '', zoomable = true, caption }) {
  const [failed, setFailed] = useState(false)
  if (!src || failed) return fallback
  const imgClass = `block w-full h-auto rounded-2xl border pb-hairline shadow-[0_30px_60px_-20px_rgba(0,0,0,0.6)] ${className}`
  if (!zoomable) {
    return <img src={src} alt={alt || ''} className={imgClass} onError={() => setFailed(true)} loading="lazy" />
  }
  return (
    <ZoomableImage
      src={src}
      alt={alt || ''}
      caption={caption}
      className={imgClass}
      onError={() => setFailed(true)}
    />
  )
}
