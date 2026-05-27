import { useEffect, useRef, useState } from 'react'

/**
 * Wraps children in a transform/opacity reveal triggered when the element
 * enters the viewport. Uses .reveal / .reveal.in classes defined in index.css.
 */
export default function Reveal({ children, delay = 0, className = '' }) {
  const ref = useRef(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            setTimeout(() => e.target.classList.add('in'), delay)
            io.unobserve(e.target)
          }
        })
      },
      { threshold: 0.12 }
    )
    io.observe(el)
    return () => io.disconnect()
  }, [delay])
  return (
    <div ref={ref} className={`reveal ${className}`}>
      {children}
    </div>
  )
}

/** useInView — returns true once the element has scrolled into view. */
export function useInView(ref, options = { threshold: 0.4 }) {
  const [inView, setInView] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) {
        setInView(true)
        io.disconnect()
      }
    }, options)
    io.observe(el)
    return () => io.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return inView
}
