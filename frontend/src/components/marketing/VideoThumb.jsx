import { useState } from 'react'

/**
 * A 16:9 poster frame with a play badge over it, shared by the /videos index
 * and the related-video rail on a video's own page.
 *
 * A video whose poster has not been uploaded yet falls back to a branded tile
 * rather than a broken image, so an entry can be added to data/videos.js ahead
 * of the recording and still list correctly.
 */
export default function VideoThumb({ poster, title, className = '' }) {
  const [failed, setFailed] = useState(false)
  const showImage = poster && !failed

  return (
    <div className={`relative w-full overflow-hidden rounded-lg border pb-hairline bg-pb-surface2 ${className}`} style={{ aspectRatio: '16 / 9' }}>
      {showImage ? (
        <img
          src={poster}
          alt=""
          className="absolute inset-0 h-full w-full object-cover"
          onError={() => setFailed(true)}
          loading="lazy"
        />
      ) : (
        <div className="absolute inset-0 opacity-20 pb-gradient" aria-hidden="true" />
      )}

      {/* Play badge. Sits over the poster so the tile reads as a video at any size. */}
      <span
        className="absolute inset-0 grid place-items-center transition-transform duration-200 group-hover:scale-105"
        aria-hidden="true"
      >
        <span
          className="grid h-11 w-11 place-items-center rounded-full bg-black/55 text-white backdrop-blur-sm ring-1 ring-white/25"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M8 5.5v13a1 1 0 0 0 1.53.85l10-6.5a1 1 0 0 0 0-1.7l-10-6.5A1 1 0 0 0 8 5.5Z" />
          </svg>
        </span>
      </span>

      {!showImage && (
        <span className="absolute inset-x-0 bottom-0 px-3 py-2 font-mono text-[9px] uppercase tracking-wide3 text-pb-faint">
          {title}
        </span>
      )}
    </div>
  )
}
