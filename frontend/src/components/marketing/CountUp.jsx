import { useEffect, useRef, useState } from 'react'
import { useInView } from './Reveal'

/**
 * Animated number that counts up from 0 → `to` when the element enters
 * the viewport. Use for stat banners and hero stat strips.
 */
export default function CountUp({ to, duration = 1800, format = (n) => n.toLocaleString() }) {
  const ref = useRef(null)
  const inView = useInView(ref)
  const [val, setVal] = useState(0)
  useEffect(() => {
    if (!inView) return
    let raf
    const start = performance.now()
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      setVal(Math.floor(eased * to))
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [inView, to, duration])
  return <span ref={ref} className="tabular-nums">{format(val)}</span>
}
