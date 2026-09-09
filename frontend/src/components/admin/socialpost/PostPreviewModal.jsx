// Preview — every page of the post at once, at the size it will actually be
// posted at, with no editing chrome over the top.
//
// The canvas behind the editor is a live preview of ONE page and carries
// selection outlines, resize handles and the inspector; there was no way to see
// a carousel end to end, or to look at a design without the tools on it.
//
// The pages come from the caller's own postPages list — the same array the
// off-screen export nodes render — so what is previewed is what downloads.
//
// Props:
//   open, onClose
//   pages      [{ key, label, content }]  from AdminSocialPost's postPages
//   width/height                          the post's canvas size
//   fontStyle                             the club's display/body font vars
//   fill                                  colour behind a letterboxed layout
//   title, sizeLabel                      shown in the header
import { useEffect, useRef, useState } from 'react'

export default function PostPreviewModal({
  open, onClose, pages = [], width = 1080, height = 1080, fontStyle = {}, title = 'Post', sizeLabel = '', fill,
}) {
  // Fit the tallest page into the space we have. Measured rather than assumed,
  // so a 9:16 story doesn't run off the bottom of a laptop screen.
  const bodyRef = useRef(null)
  const [box, setBox] = useState({ w: 0, h: 0 })
  useEffect(() => {
    if (!open) return
    const el = bodyRef.current
    if (!el) return
    const measure = () => setBox({ w: el.clientWidth, h: el.clientHeight })
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') onClose?.() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  const many = pages.length > 1
  // Side by side while they fit, then wrapped — a 3-page carousel of squares
  // reads as a carousel, where three stories do not.
  const perRow = many ? Math.min(pages.length, Math.max(1, Math.floor((box.w || 1200) / 320))) : 1
  const cellW = Math.max(120, ((box.w || 1200) - 24 * (perRow + 1)) / perRow)
  const rows = Math.ceil(pages.length / perRow)
  const cellH = Math.max(120, ((box.h || 700) - 24 * (rows + 1) - (many ? 22 * rows : 0)) / rows)
  const scale = Math.min(cellW / width, cellH / height, 1)

  return (
    <div className="fixed inset-0 z-50 flex flex-col" style={{ background: 'rgba(7,9,15,.94)', backdropFilter: 'blur(6px)' }}
      onClick={onClose} data-testid="post-preview">
      <header className="shrink-0 h-13 flex items-center gap-3 px-4 py-3 border-b pb-hairline" onClick={(e) => e.stopPropagation()}>
        <span className="font-mono text-[10px] tracking-wide2 uppercase text-pb-accent">Preview</span>
        <span className="text-pb-text text-[13px] truncate">{title}</span>
        <span className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faintest" data-testid="preview-meta">
          {width} × {height}{sizeLabel ? ` · ${sizeLabel}` : ''} · {pages.length} page{pages.length === 1 ? '' : 's'}
        </span>
        <span className="flex-1" />
        <span className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faintest hidden sm:block">Esc to close</span>
        <button onClick={onClose} data-testid="preview-close"
          className="px-3 h-8 rounded-md border pb-hairline2 font-mono text-[10px] tracking-wide2 text-pb-dim hover:text-pb-text transition-colors">Close</button>
      </header>

      <div ref={bodyRef} className="flex-1 min-h-0 overflow-auto p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex flex-wrap items-start justify-center gap-6">
          {pages.map((p) => (
            <figure key={p.key} className="m-0 flex flex-col items-center gap-1.5" data-testid="preview-page">
              <div style={{
                width: Math.round(width * scale), height: Math.round(height * scale),
                overflow: 'hidden', borderRadius: 6, background: fill || '#080808',
                boxShadow: '0 24px 60px rgba(0,0,0,.55)',
              }}>
                <div style={{ ...fontStyle, width, height, transform: `scale(${scale})`, transformOrigin: 'top left', position: 'relative' }}>
                  {p.content}
                </div>
              </div>
              {many && (
                <figcaption className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faintest">{p.label}</figcaption>
              )}
            </figure>
          ))}
        </div>
      </div>
    </div>
  )
}
