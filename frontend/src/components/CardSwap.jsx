// A stack of cards where the front one drops away and returns to the back (the React Bits "Card Swap"
// idea), built on gsap, which the app already ships. Differences from the original, made for browsing a
// long list by hand: it is driven by next / prev / goTo (no timer), a swipe or the arrow keys work,
// and only the first few cards behind the front one are drawn, so fifty cards do not run off the screen.
//
//   <CardSwap ref={ref} width={300} height={500} onFront={(i) => ...}>{cards}</CardSwap>
//   ref.current.next() | prev() | goTo(index)
import { Children, forwardRef, useCallback, useImperativeHandle, useLayoutEffect, useRef } from 'react'
import gsap from 'gsap'

const MAX_DEPTH = 3          // cards drawn behind the front one
const SWIPE_PX = 40

const reducedMotion = () => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

const CardSwap = forwardRef(function CardSwap(
  { width, height, cardDistance = 12, verticalDistance = 16, skewAmount = 3, initialFront = 0, onFront, onCardClick, label, children },
  ref,
) {
  const items = Children.toArray(children)
  const n = items.length
  const depth = Math.min(MAX_DEPTH, Math.max(0, n - 1))
  const els = useRef([])
  const order = useRef([])               // child indexes, front first
  const busy = useRef(false)
  const line = useRef(null)
  const swipe = useRef(null)
  const dragged = useRef(false)          // the last pointer gesture was a swipe, so its click is not a tap
  const live = useRef({})
  live.current = { onFront, onCardClick }

  const skew = reducedMotion() ? 0 : skewAmount
  const slot = useCallback((i) => {
    const j = Math.min(i, depth)
    return { x: j * cardDistance, y: (depth - j) * verticalDistance, z: -j * cardDistance * 1.5, zIndex: n - i, opacity: i > depth ? 0 : 1 }
  }, [depth, n, cardDistance, verticalDistance])

  // Place every card. Runs again when the cards change, so a reload never leaves a stale stack.
  useLayoutEffect(() => {
    const start = n ? ((initialFront % n) + n) % n : 0
    order.current = Array.from({ length: n }, (_, i) => (start + i) % n)
    busy.current = false
    order.current.forEach((idx, pos) => {
      const s = slot(pos)
      gsap.set(els.current[idx], { x: s.x, y: s.y, z: s.z, skewY: skew, opacity: s.opacity, zIndex: s.zIndex, transformOrigin: 'center center', force3D: true })
    })
    return () => { line.current?.kill(); line.current = null }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [n, initialFront, slot])

  const finish = (newOrder) => {
    order.current = newOrder
    busy.current = false
    live.current.onFront?.(newOrder[0])
  }

  const next = useCallback(() => {
    if (n < 2 || busy.current) return
    busy.current = true
    const [front, ...rest] = order.current
    const d = reducedMotion() ? 0 : 0.55
    const back = slot(n - 1)
    const tl = gsap.timeline({ onComplete: () => finish([...rest, front]) })
    line.current = tl
    tl.to(els.current[front], { y: slot(0).y + height * 0.32, opacity: 0, duration: d * 0.8, ease: 'power2.in' })
    tl.addLabel('promote', `-=${d * 0.3}`)
    rest.forEach((idx, i) => {
      const s = slot(i)
      tl.set(els.current[idx], { zIndex: s.zIndex }, 'promote')
      tl.to(els.current[idx], { x: s.x, y: s.y, z: s.z, opacity: s.opacity, duration: d, ease: 'power2.out' }, `promote+=${Math.min(i, depth + 1) * 0.04}`)
    })
    tl.addLabel('return', `promote+=${d * 0.35}`)
    tl.set(els.current[front], { zIndex: back.zIndex }, 'return')
    tl.to(els.current[front], { x: back.x, y: back.y, z: back.z, opacity: back.opacity, duration: d, ease: 'power2.inOut' }, 'return')
  }, [n, height, depth, slot])

  // Bring `newOrder[0]` to the front from above while the others settle into the slots behind it.
  const relayout = useCallback((newOrder) => {
    if (busy.current) return
    busy.current = true
    const d = reducedMotion() ? 0 : 0.5
    const incoming = els.current[newOrder[0]]
    const s0 = slot(0)
    gsap.set(incoming, { x: s0.x, y: s0.y + height * 0.32, z: s0.z, opacity: 0, zIndex: n + 1 })
    const tl = gsap.timeline({ onComplete: () => finish(newOrder) })
    line.current = tl
    newOrder.forEach((idx, pos) => {
      const s = slot(pos)
      if (pos > 0) tl.set(els.current[idx], { zIndex: s.zIndex }, 0)
      tl.to(els.current[idx], { x: s.x, y: s.y, z: s.z, opacity: s.opacity, duration: d, ease: 'power2.out' }, 0)
    })
    tl.set(incoming, { zIndex: s0.zIndex }, d)
  }, [n, height, slot])

  const prev = useCallback(() => {
    if (n < 2 || busy.current) return
    const o = order.current
    relayout([o[n - 1], ...o.slice(0, n - 1)])
  }, [n, relayout])

  const goTo = useCallback((idx) => {
    const o = order.current
    const pos = o.indexOf(idx)
    if (pos <= 0 || busy.current) return
    relayout([...o.slice(pos), ...o.slice(0, pos)])
  }, [relayout])

  useImperativeHandle(ref, () => ({ next, prev, goTo }), [next, prev, goTo])

  const onPointerDown = (e) => { swipe.current = { x: e.clientX }; dragged.current = false }
  const onPointerUp = (e) => {
    const s = swipe.current
    swipe.current = null
    if (!s) return
    const dx = e.clientX - s.x
    if (Math.abs(dx) >= 8) dragged.current = true
    if (Math.abs(dx) >= SWIPE_PX) { if (dx < 0) next(); else prev() }
  }
  const onKeyDown = (e) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); next() }
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); prev() }
  }

  return (
    <div
      role="group" aria-roledescription="carousel" aria-label={label} tabIndex={0}
      onKeyDown={onKeyDown} onPointerDown={onPointerDown} onPointerUp={onPointerUp} onDragStart={(e) => e.preventDefault()}
      onPointerCancel={() => { swipe.current = null }}
      style={{
        position: 'relative', margin: '0 auto', maxWidth: '100%', perspective: 900, touchAction: 'pan-y', outline: 'none',
        // A swipe must not select text or start dragging an image, either of which cancels the gesture.
        userSelect: 'none', WebkitUserSelect: 'none',
        width: width + depth * cardDistance, height: height + depth * verticalDistance,
      }}
    >
      {items.map((child, i) => (
        <div
          key={child.key ?? i}
          ref={(el) => { els.current[i] = el }}
          onClick={() => { if (!dragged.current) live.current.onCardClick?.(i) }}
          style={{ position: 'absolute', left: 0, top: 0, width, height, transformStyle: 'preserve-3d', willChange: 'transform' }}
        >
          {child}
        </div>
      ))}
    </div>
  )
})

export default CardSwap
