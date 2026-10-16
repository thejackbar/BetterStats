// The club settings every screen that RECORDS availability needs. Today that is one
// thing: whether the club offers "Maybe". Fetched once per page load and shared, so
// the quick-answer modal, the bulk bar and the link panel agree without each asking.
import { useEffect, useState } from 'react'
import { api } from './api'

let current = { allow_maybe: true, half_colours: null }
let loading = null
const listeners = new Set()

// The club's half-available colours reach every card through two CSS variables.
function paintHalf(c) {
  if (!c || typeof document === 'undefined') return
  const root = document.documentElement.style
  if (c.w1) root.setProperty('--pb-half-w1', c.w1); else root.removeProperty('--pb-half-w1')
  if (c.w2) root.setProperty('--pb-half-w2', c.w2); else root.removeProperty('--pb-half-w2')
}

function publish(next) {
  current = { ...current, ...next }
  if ('half_colours' in next) paintHalf(next.half_colours)
  listeners.forEach((fn) => fn(current))
}

/* The Settings screen calls this so every open screen follows a colour change. */
export function setHalfColours(c) { publish({ half_colours: c }) }

/* The panel that changes the setting calls this so every open screen follows. */
export function setAllowMaybe(v) { publish({ allow_maybe: v !== false }) }

export function useAllowMaybe() {
  const [cfg, setCfg] = useState(current)
  useEffect(() => {
    listeners.add(setCfg)
    if (!loading) {
      // Football has no such setting: a failed read leaves Maybe on, as it always was.
      loading = api.bsAvailabilityConfig().then((c) => publish({ allow_maybe: c?.allow_maybe !== false, half_colours: c?.half_colours || null })).catch(() => {})
    }
    setCfg(current)
    return () => { listeners.delete(setCfg) }
  }, [])
  return cfg.allow_maybe !== false
}

/* Every BetterSelect screen mounts this once (the layout does), so the club's
   half-available colours are on the page before the first card is drawn. */
export function useHalfColours() {
  useAllowMaybe()
  return current.half_colours
}
