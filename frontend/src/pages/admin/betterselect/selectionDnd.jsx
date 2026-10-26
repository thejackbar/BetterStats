// Pointer-based drag engine for the Selection board — works with mouse AND
// touch from one code path (Pointer Events), with a floating ghost. Replaces
// the old HTML5 `draggable` board, whose right→left drag was broken and which
// didn't work on touch at all.
//
// Drop zones tag themselves with `data-drop-kind` ("slot" | "pool" | "col") and,
// for slots, `data-drop-idx`. A board with several sides (the draft table) also
// sets `data-drop-col` to say which one; without it the hit is exactly what it
// always was. Draggables spread `useDrag().bind(item)` where item is
// `{ kind:'pool', player }` or `{ kind:'slot', idx, player }`. A 6px threshold
// distinguishes a drag from a tap so tap-to-place (the primary mobile gesture)
// still fires. A horizontally scrolling board tags its scroller `data-autoscroll-x`
// and the engine scrolls it sideways while a drag is held near its left or right
// edge; a child tagged `data-autoscroll-skip` (a pinned pool) is not part of the
// left edge. Only grip handles set `touch-action:none`, so the pool lists
// keep scrolling on touch — whole-card drag is a desktop nicety.
import { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { Avatar } from './ui'

const DnDCtx = createContext(null)

export function DnD({ onDrop, children }) {
  const [drag, setDrag] = useState(null)    // { item, x, y } while dragging
  const [hover, setHover] = useState(null)  // 'slot:3' | 'pool' | null
  const ref = useRef({ item: null, startX: 0, startY: 0, active: false, didDrag: false })
  const onDropRef = useRef(onDrop)
  useEffect(() => { onDropRef.current = onDrop }, [onDrop])

  useEffect(() => {
    const hit = (x, y) => {
      const el = document.elementFromPoint(x, y)
      const z = el && el.closest('[data-drop-kind]')
      if (!z) return null
      const kind = z.getAttribute('data-drop-kind')
      const idx = z.getAttribute('data-drop-idx')
      const col = z.getAttribute('data-drop-col')
      return { kind, idx: idx == null ? null : Number(idx), col, key: kind + (col ? ':' + col : '') + (idx == null ? '' : ':' + idx) }
    }
    // Hold a drag near the edge of a sideways scroller and it scrolls, so a
    // column that is off screen can still be dropped on.
    const EDGE = 80, MAX_STEP = 24
    let raf = 0
    const tick = () => {
      raf = 0
      const r = ref.current
      if (!r.active || !r.item) return
      let scrolled = false
      document.querySelectorAll('[data-autoscroll-x]').forEach((el) => {
        const b = el.getBoundingClientRect()
        if (r.lastY < b.top || r.lastY > b.bottom) return
        const skip = el.querySelector('[data-autoscroll-skip]')
        const leftEdge = b.left + (skip ? skip.getBoundingClientRect().width : 0)
        let dx = 0
        if (r.lastX > b.right - EDGE) dx = Math.ceil(MAX_STEP * Math.min(1, (r.lastX - (b.right - EDGE)) / EDGE))
        else if (r.lastX >= leftEdge && r.lastX < leftEdge + EDGE) dx = -Math.ceil(MAX_STEP * Math.min(1, (leftEdge + EDGE - r.lastX) / EDGE))
        if (!dx) return
        const before = el.scrollLeft
        el.scrollLeft = before + dx
        if (el.scrollLeft !== before) scrolled = true
      })
      if (scrolled) { const t = hit(r.lastX, r.lastY); setHover(t ? t.key : null) }
      raf = requestAnimationFrame(tick)
    }
    const move = (e) => {
      const r = ref.current
      if (!r.item) return
      const dx = e.clientX - r.startX, dy = e.clientY - r.startY
      if (!r.active && Math.hypot(dx, dy) < 6) return
      // Once a real drag starts, suppress text selection so sweeping the cursor
      // across the board doesn't highlight every row's text under the pointer.
      if (!r.active) { r.active = true; r.didDrag = true; document.body.style.userSelect = 'none' }
      if (e.cancelable) e.preventDefault()
      r.lastX = e.clientX; r.lastY = e.clientY
      if (!raf) raf = requestAnimationFrame(tick)
      const t = hit(e.clientX, e.clientY)
      setHover(t ? t.key : null)
      setDrag({ item: r.item, x: e.clientX, y: e.clientY })
    }
    const finish = (e, drop) => {
      const r = ref.current
      if (!r.item) return
      if (drop && r.active) { const t = hit(e.clientX, e.clientY); if (t) onDropRef.current(t, r.item) }
      r.item = null; r.active = false
      cancelAnimationFrame(raf); raf = 0
      document.body.style.userSelect = ''
      setDrag(null); setHover(null)
    }
    const up = (e) => finish(e, true)
    // The browser took the gesture (a finger that turned into a scroll): that is
    // not a drop, whatever is under the finger when it lets go.
    const cancel = (e) => finish(e, false)
    window.addEventListener('pointermove', move, { passive: false })
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', cancel)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', cancel)
      document.body.style.userSelect = ''
    }
  }, [])

  const begin = useCallback((item, e) => {
    // Only the primary button / a touch contact starts a drag.
    if (e.button != null && e.button !== 0) return
    ref.current = { item, startX: e.clientX, startY: e.clientY, active: false, didDrag: false }
    setDrag(null)
  }, [])
  // A drag that moved past threshold suppresses the trailing click (tap-to-place).
  const consumedClick = useCallback(() => { const d = ref.current.didDrag; ref.current.didDrag = false; return d }, [])

  return (
    <DnDCtx.Provider value={{ begin, consumedClick, hover, dragItem: drag?.item || null }}>
      {children}
      {drag && <DragGhost drag={drag} />}
    </DnDCtx.Provider>
  )
}

function DragGhost({ drag }) {
  const p = drag.item.player
  return createPortal(
    <div style={{
      position: 'fixed', left: drag.x, top: drag.y, transform: 'translate(-50%,-130%) rotate(-2deg)',
      zIndex: 9999, pointerEvents: 'none', display: 'flex', alignItems: 'center', gap: 8,
      padding: '7px 12px 7px 8px', borderRadius: 10, background: 'var(--pb-surface)',
      border: '1px solid var(--pb-accent)', boxShadow: '0 16px 40px -8px rgba(0,0,0,.45)', opacity: 0.96,
    }}>
      <Avatar player={p} size={26} noLink />
      <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--pb-text)' }}>{p?.display_name}</span>
    </div>,
    document.body,
  )
}

export function useDrag() {
  const ctx = useContext(DnDCtx)
  return {
    bind: (item) => ({ onPointerDown: (e) => ctx.begin(item, e) }),
    clickGuard: (fn) => (e) => { if (ctx.consumedClick()) return; if (fn) fn(e) },
    hover: ctx.hover,
    dragItem: ctx.dragItem,
  }
}
