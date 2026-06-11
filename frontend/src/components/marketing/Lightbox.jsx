import { useEffect } from 'react'
import { createPortal } from 'react-dom'

/**
 * Full-screen overlay that shows one image at the largest size that fits the
 * viewport. Closes on backdrop click, the close button, or Escape, and locks
 * page scroll while it's open. Matches the gallery lightbox on the club sites.
 *
 * Controlled — render it only while open and pass onClose:
 *   {open && <Lightbox src={src} alt={alt} caption={cap} onClose={() => setOpen(false)} />}
 */
export default function Lightbox({ src, alt = '', caption, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [onClose])

  return createPortal(
    <div
      className="bs-lightbox-backdrop fixed inset-0 z-[200] flex items-center justify-center bg-black/90 p-4 sm:p-8"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={alt || 'Enlarged screenshot'}
    >
      <button
        onClick={onClose}
        aria-label="Close"
        className="absolute top-4 right-4 grid h-10 w-10 place-items-center rounded-full text-2xl leading-none text-white/70 transition-colors hover:bg-white/10 hover:text-white"
      >
        ✕
      </button>
      <figure
        className="bs-lightbox-figure flex max-h-[92vh] w-full max-w-6xl flex-col items-center"
        onClick={(e) => e.stopPropagation()}
      >
        <img
          src={src}
          alt={alt}
          className="mx-auto max-h-[85vh] w-auto max-w-full rounded-lg object-contain shadow-2xl"
        />
        {caption && (
          <figcaption className="mt-4 max-w-2xl text-center text-sm text-white/80">{caption}</figcaption>
        )}
      </figure>
    </div>,
    document.body,
  )
}
