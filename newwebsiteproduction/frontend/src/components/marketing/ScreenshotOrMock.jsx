import { useState } from 'react'

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
 */
export default function ScreenshotOrMock({ src, alt, fallback, className = '' }) {
  const [failed, setFailed] = useState(false)
  if (!src || failed) return fallback
  return (
    <img
      src={src}
      alt={alt || ''}
      className={`block w-full h-auto rounded-2xl border pb-hairline shadow-[0_30px_60px_-20px_rgba(0,0,0,0.6)] ${className}`}
      onError={() => setFailed(true)}
      loading="lazy"
    />
  )
}
