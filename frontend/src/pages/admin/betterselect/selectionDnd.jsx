// Pointer-based drag engine for the Selection board — works with mouse AND
// touch from one code path (Pointer Events), with a floating ghost. Replaces
// the old HTML5 `draggable` board, whose right→left drag was broken and which
// didn't work on touch at all.
//
// Drop zones tag themselves with `data-drop-kind` ("slot" | "pool") and, for
// slots, `data-drop-idx`. Draggables spread `useDrag().bind(item)` where item is
// `{ kind:'pool', player }` or `{ kind:'slot', idx, player }`. A 6px threshold
// distinguishes a drag from a tap so tap-to-place (the primary mobile gesture)
// still fires. Only grip handles set `touch-action:none`, so the pool lists
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
      return { kind, idx: idx == null ? null : Number(idx), key: kind + (idx == null ? '' : ':' + idx) }
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
      const t = hit(e.clientX, e.clientY)
      setHover(t ? t.key : null)
      setDrag({ item: r.item, x: e.clientX, y: e.clientY })
    }
    const up = (e) => {
      const r = ref.current
      if (!r.item) return
      if (r.active) { const t = hit(e.clientX, e.clientY); if (t) onDropRef.current(t, r.item) }
      r.item = null; r.active = false
      document.body.style.userSelect = ''
      setDrag(null); setHover(null)
    }
    window.addEventListener('pointermove', move, { passive: false })
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', up)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', up)
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
