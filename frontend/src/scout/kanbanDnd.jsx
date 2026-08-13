// Pointer-based drag engine for BetterScout's watchlist boards — a
// generalisation of frontend/src/pages/admin/betterselect/selectionDnd.jsx's
// engine (same Pointer Events approach: works with mouse AND touch from one
// code path, ref-tracked drag state, data-drop-* hit-testing, floating
// ghost via a portal). Chosen over the roster board's native HTML5
// drag-and-drop specifically because Pointer Events give free touch support
// and can be driven by a real mouse in automated testing, unlike native
// HTML5 drag (which needs raw DragEvents dispatched in two separate steps
// to work under Playwright).
//
// Generalised two ways from the original: drop zones are tagged
// `data-drop-kind="column"` with `data-drop-idx` as a COLUMN ID (a string,
// not a numeric slot index — Kanban columns aren't positional slots), and
// the drag ghost's content is a render prop instead of a hardcoded player
// Avatar, so this module has no BetterScout-specific rendering baked in.
import { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react'
import { createPortal } from 'react-dom'

const DnDCtx = createContext(null)

export function KanbanDnD({ onDrop, renderGhost, children }) {
  const [drag, setDrag] = useState(null)    // { item, x, y } while dragging
  const [hover, setHover] = useState(null)  // 'column:<id>' | null
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
      return { kind, idx, key: kind + (idx == null ? '' : ':' + idx) }
    }
    const move = (e) => {
      const r = ref.current
      if (!r.item) return
      const dx = e.clientX - r.startX, dy = e.clientY - r.startY
      if (!r.active && Math.hypot(dx, dy) < 6) return
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
    if (e.button != null && e.button !== 0) return
    ref.current = { item, startX: e.clientX, startY: e.clientY, active: false, didDrag: false }
    setDrag(null)
  }, [])
  const consumedClick = useCallback(() => { const d = ref.current.didDrag; ref.current.didDrag = false; return d }, [])

  return (
    <DnDCtx.Provider value={{ begin, consumedClick, hover, dragItem: drag?.item || null }}>
      {children}
      {drag && renderGhost && (
        createPortal(
          <div style={{
            position: 'fixed', left: drag.x, top: drag.y, transform: 'translate(-50%,-130%) rotate(-2deg)',
            zIndex: 9999, pointerEvents: 'none', opacity: 0.96,
          }}>
            {renderGhost(drag.item)}
          </div>,
          document.body,
        )
      )}
    </DnDCtx.Provider>
  )
}

export function useKanbanDrag() {
  const ctx = useContext(DnDCtx)
  return {
    bind: (item) => ({ onPointerDown: (e) => ctx.begin(item, e) }),
    clickGuard: (fn) => (e) => { if (ctx.consumedClick()) return; if (fn) fn(e) },
    hover: ctx.hover,
    dragItem: ctx.dragItem,
  }
}
