import { useEffect, useLayoutEffect, useRef, useState, useCallback } from 'react'
import { createPortal } from 'react-dom'

// Floating panel that is rendered into <body> via a portal and positioned with
// `position: fixed` against its anchor. Because it lives at the top of the DOM
// (not inside the anchor's subtree) it can NEVER be clipped by an ancestor's
// `overflow: hidden` / `overflow: auto` — the bug that was cutting off search
// dropdowns and menus all across the app (a `position: absolute` panel is always
// clipped by the nearest scroll/overflow ancestor; a portalled fixed panel is not).
//
// It mirrors the pattern already proven in components/Navbar.jsx (portal + fixed +
// getBoundingClientRect), generalised so every autocomplete/menu can share it.
//
// Props:
//   anchorRef  ref to the trigger element (input wrapper / button). Width + screen
//              position are read from it.
//   open       whether the panel is shown.
//   onClose    called on outside-click or Escape (the host keeps its own `open`).
//   align      'stretch' (default, match anchor width) | 'start' (left edge) | 'end' (right edge)
//   width      explicit CSS width (px number or string). Defaults to the anchor
//              width for 'stretch', otherwise auto.
//   gap        px between anchor and panel (default 4 ≈ Tailwind mt-1).
//   maxHeight  px cap on the panel height (preserves a site's old max-h-*). Always
//              further capped to the space actually available on screen so it can
//              never run off the viewport.
//   className  styling for the panel (colours / border / rounded / shadow). Do NOT
//              pass positioning (absolute/z/top/left) or max-height/overflow — those
//              are handled here.
//   zIndex     stacking (default 200, same as the Navbar portal menus).
export default function Dropdown({
  anchorRef,
  open,
  onClose,
  align = 'stretch',
  width,
  gap = 4,
  maxHeight,
  className = '',
  style: styleProp,
  children,
  zIndex = 200,
}) {
  const panelRef = useRef(null)
  const [pos, setPos] = useState(null)

  const compute = useCallback(() => {
    const el = anchorRef?.current
    if (!el) return
    const r = el.getBoundingClientRect()
    const vw = window.innerWidth
    const vh = window.innerHeight
    const spaceBelow = vh - r.bottom
    const spaceAbove = r.top
    // Flip above only when there genuinely isn't room below but there is above.
    const flipUp = spaceBelow < 220 && spaceAbove > spaceBelow
    const available = Math.max(140, Math.round((flipUp ? spaceAbove : spaceBelow) - gap - 8))
    const next = {
      top: flipUp ? undefined : Math.round(r.bottom + gap),
      bottom: flipUp ? Math.round(vh - r.top + gap) : undefined,
      maxHeight: maxHeight != null ? Math.min(maxHeight, available) : available,
    }
    if (align === 'end') {
      next.right = Math.round(vw - r.right)
      if (width != null) next.width = width
    } else {
      next.left = Math.round(r.left)
      next.width = width != null ? width : (align === 'stretch' ? Math.round(r.width) : undefined)
    }
    setPos(next)
  }, [anchorRef, align, width, gap, maxHeight])

  // Position before paint to avoid a flash at (0,0), then keep it glued to the
  // anchor as the page scrolls/resizes. Scroll is captured so it also fires for
  // scrollable ancestors, not just the window.
  useLayoutEffect(() => {
    if (!open) { setPos(null); return }
    compute()
    const onScroll = () => compute()
    window.addEventListener('scroll', onScroll, true)
    window.addEventListener('resize', compute)
    return () => {
      window.removeEventListener('scroll', onScroll, true)
      window.removeEventListener('resize', compute)
    }
  }, [open, compute])

  // Outside-click + Escape close. We check the real panel node (which includes
  // the portalled children) so clicking an option never counts as "outside".
  useEffect(() => {
    if (!open) return
    const onDown = (e) => {
      const a = anchorRef?.current
      const p = panelRef.current
      if (a && a.contains(e.target)) return
      if (p && p.contains(e.target)) return
      onClose?.()
    }
    const onKey = (e) => { if (e.key === 'Escape') onClose?.() }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, anchorRef, onClose])

  if (!open || !pos) return null

  return createPortal(
    <div
      ref={panelRef}
      className={className}
      style={{
        position: 'fixed',
        zIndex,
        top: pos.top,
        bottom: pos.bottom,
        left: pos.left,
        right: pos.right,
        width: pos.width,
        maxHeight: pos.maxHeight,
        overflowY: 'auto',
        ...styleProp,
      }}
    >
      {children}
    </div>,
    document.body,
  )
}
