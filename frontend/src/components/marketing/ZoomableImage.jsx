import { useState } from 'react'
import Lightbox from './Lightbox'

/**
 * An <img> that opens full-size in a Lightbox when clicked. Use it anywhere a
 * screenshot is shown small and the detail matters. `className` styles the
 * image itself; `wrapperClassName` styles the clickable frame (handy when the
 * image needs to fill a fixed-height container). `zoomSrc` lets the enlarged
 * view load a higher-res source than the thumbnail.
 */
export default function ZoomableImage({
  src,
  alt = '',
  caption,
  zoomSrc,
  className = '',
  wrapperClassName = '',
  onError,
  loading = 'lazy',
}) {
  const [open, setOpen] = useState(false)
  if (!src) return null
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={alt ? `Enlarge: ${alt}` : 'Enlarge image'}
        className={`group/zoom relative block w-full cursor-zoom-in ${wrapperClassName}`}
      >
        <img src={src} alt={alt} onError={onError} loading={loading} className={className} />
        <span
          className="pointer-events-none absolute bottom-2 right-2 grid h-8 w-8 place-items-center rounded-full bg-black/55 text-white opacity-0 backdrop-blur-sm transition-opacity duration-200 group-hover/zoom:opacity-100"
          aria-hidden="true"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="7" />
            <line x1="16.5" y1="16.5" x2="21" y2="21" />
            <line x1="11" y1="8" x2="11" y2="14" />
            <line x1="8" y1="11" x2="14" y2="11" />
          </svg>
        </span>
      </button>
      {open && <Lightbox src={zoomSrc || src} alt={alt} caption={caption} onClose={() => setOpen(false)} />}
    </>
  )
}
