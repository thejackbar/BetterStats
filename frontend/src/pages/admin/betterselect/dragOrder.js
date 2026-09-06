// Dragging a list into order with a finger, a pencil or a mouse.
//
// POINTER EVENTS, NOT THE HTML5 DRAG API, and that is the whole reason this
// exists rather than a `draggable` attribute. iOS Safari fires no dragstart,
// dragover or drop at all — so on an iPad, which is the device the net manager
// actually runs a session from, `draggable` gives you nothing and the list
// simply can't be reordered. Pointer events are the one API that covers a
// finger, an Apple Pencil and a mouse with the same code.
//
// `touch-action: none` on the HANDLE is the other half. Without it the browser
// claims the gesture as a page scroll before the first pointermove ever
// reaches us, and the drag never starts. Putting it on the handle rather than
// the row is deliberate: the rest of the row keeps its ordinary scrolling, so
// a coach can still flick past a twenty-name queue with a thumb.
//
// The rows reorder live under the finger rather than a lifted copy following
// it. One thing moves instead of two, there is no ghost element to keep in
// step with a re-render, and the row that has just landed is the row that is
// under the finger.
import { useCallback, useRef, useState } from 'react'

// How close to the edge of the window auto-scroll starts, and how fast it runs
// at the very edge. A long queue is taller than an iPad, so a drag from the
// bottom of it to the top has to be able to reach.
const EDGE_PX = 96
const EDGE_SPEED = 16

/**
 * @param ids       the current order, as stable ids
 * @param onCommit  called with the new order once the finger lifts; awaited, so
 *                  the preview can be held until the write lands
 * @param enabled   false leaves every handle inert (a read-only viewer)
 * @param onActive  told when a drag starts and stops — the caller uses it to
 *                  hold off the poll, which would otherwise adopt the server's
 *                  older order mid-drag and yank the row out from under the
 *                  finger
 */
export function useDragOrder({ ids, onCommit, enabled = true, onActive }) {
  const [dragId, setDragId] = useState(null)
  const [order, setOrder] = useState(null)   // the preview, or null when idle

  const els = useRef(new Map())
  const st = useRef(null)
  // Read through refs so a handle bound on one render can't act on a stale
  // list or call a stale writer three renders later.
  const idsRef = useRef(ids); idsRef.current = ids
  const commitRef = useRef(onCommit); commitRef.current = onCommit
  const activeRef = useRef(onActive); activeRef.current = onActive

  const register = useCallback((id) => (el) => {
    if (el) els.current.set(id, el)
    else els.current.delete(id)
  }, [])

  const start = useCallback((e, id) => {
    if (st.current) return
    if (e.pointerType === 'mouse' && e.button !== 0) return
    const list = idsRef.current
    const from = list.indexOf(id)
    if (from < 0) return
    e.preventDefault()
    e.stopPropagation()

    // PAGE coordinates, not client ones. The list auto-scrolls under the finger
    // on a long queue, and a snapshot taken in client space would have every
    // threshold quietly shift the moment it did.
    const scrollY = window.scrollY || 0
    const s = {
      id,
      from,
      to: from,
      list,
      order: list,
      // The rows' midpoints as they sat when the drag began. Measuring once and
      // comparing against those is what keeps the row from oscillating between
      // two slots: re-measuring after each swap moves the very threshold that
      // caused it.
      mids: list.map((x) => {
        const el = els.current.get(x)
        if (!el) return Infinity
        const r = el.getBoundingClientRect()
        return (r.top + r.bottom) / 2 + scrollY
      }),
      pageY: e.clientY + scrollY,
      raf: 0,
    }
    st.current = s
    setDragId(id)
    setOrder(list)
    activeRef.current?.(true)
    const priorSelect = document.body.style.userSelect
    document.body.style.userSelect = 'none'

    const apply = () => {
      const cur = st.current
      if (!cur) return
      let to = cur.from
      const y = cur.pageY
      if (y > cur.mids[cur.from]) {
        for (let i = cur.from + 1; i < cur.mids.length; i++) if (y > cur.mids[i]) to = i
      } else {
        for (let i = cur.from - 1; i >= 0; i--) if (y < cur.mids[i]) to = i
      }
      if (to === cur.to) return
      cur.to = to
      const next = cur.list.slice()
      next.splice(cur.from, 1)
      next.splice(to, 0, cur.id)
      cur.order = next
      setOrder(next)
    }

    const tick = () => {
      const cur = st.current
      if (!cur) return
      const clientY = cur.pageY - (window.scrollY || 0)
      let dy = 0
      if (clientY < EDGE_PX) dy = -Math.ceil(EDGE_SPEED * (1 - clientY / EDGE_PX))
      else if (clientY > window.innerHeight - EDGE_PX) {
        dy = Math.ceil(EDGE_SPEED * (1 - (window.innerHeight - clientY) / EDGE_PX))
      }
      if (dy) {
        const before = window.scrollY || 0
        window.scrollBy(0, dy)
        // The finger hasn't moved, so its position on the PAGE moves with the
        // scroll. Without this the row stops advancing the instant auto-scroll
        // takes over.
        cur.pageY += (window.scrollY || 0) - before
        apply()
      }
      cur.raf = requestAnimationFrame(tick)
    }

    const move = (ev) => {
      const cur = st.current
      if (!cur) return
      ev.preventDefault()
      cur.pageY = ev.clientY + (window.scrollY || 0)
      apply()
    }

    const end = (commit) => {
      const cur = st.current
      if (!cur) return
      st.current = null
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', cancel)
      cancelAnimationFrame(cur.raf)
      document.body.style.userSelect = priorSelect
      setDragId(null)
      activeRef.current?.(false)
      const moved = commit && cur.order.join('|') !== cur.list.join('|')
      if (!moved) { setOrder(null); return }
      // Hold the preview until the write comes back. Clearing it here would
      // snap the row to where it started and then forward again a moment
      // later, which reads as the drag having failed.
      Promise.resolve(commitRef.current(cur.order)).finally(() => setOrder(null))
    }
    const up = () => end(true)
    const cancel = () => end(false)

    window.addEventListener('pointermove', move, { passive: false })
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', cancel)
    s.raf = requestAnimationFrame(tick)
  }, [])

  const handleProps = useCallback((id) => (
    enabled
      ? { style: { touchAction: 'none' }, onPointerDown: (e) => start(e, id) }
      : {}
  ), [enabled, start])

  return { dragId, order, register, handleProps, dragging: dragId != null }
}
