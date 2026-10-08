import { useState, useEffect } from 'react'

// Live result of a CSS media query. For the few places that must change what
// they DO on a phone (open a sheet instead of focusing a slot), not just how
// they look: a width the layout switches on in CSS should use the matching
// Tailwind variant instead.
export function useMediaQuery(query) {
  const read = () => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(query).matches : false)
  const [matches, setMatches] = useState(read)
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined
    const mq = window.matchMedia(query)
    const on = () => setMatches(mq.matches)
    on()
    mq.addEventListener ? mq.addEventListener('change', on) : mq.addListener(on)
    return () => { mq.removeEventListener ? mq.removeEventListener('change', on) : mq.removeListener(on) }
  }, [query])
  return matches
}
