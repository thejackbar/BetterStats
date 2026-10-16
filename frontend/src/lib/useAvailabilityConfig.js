// The club settings every screen that RECORDS availability needs. Today that is one
// thing: whether the club offers "Maybe". Fetched once per page load and shared, so
// the quick-answer modal, the bulk bar and the link panel agree without each asking.
import { useEffect, useState } from 'react'
import { api } from './api'

let current = { allow_maybe: true }
let loading = null
const listeners = new Set()

function publish(next) {
  current = { ...current, ...next }
  listeners.forEach((fn) => fn(current))
}

/* The panel that changes the setting calls this so every open screen follows. */
export function setAllowMaybe(v) { publish({ allow_maybe: v !== false }) }

export function useAllowMaybe() {
  const [cfg, setCfg] = useState(current)
  useEffect(() => {
    listeners.add(setCfg)
    if (!loading) {
      // Football has no such setting: a failed read leaves Maybe on, as it always was.
      loading = api.bsAvailabilityConfig().then((c) => publish({ allow_maybe: c?.allow_maybe !== false })).catch(() => {})
    }
    setCfg(current)
    return () => { listeners.delete(setCfg) }
  }, [])
  return cfg.allow_maybe !== false
}
