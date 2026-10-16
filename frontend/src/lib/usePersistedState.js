import { useCallback, useState } from 'react'

/* useState that remembers its value on this device (localStorage), for the quiet
 * view controls that are not URL filters: a roster toggle, a recency window, a
 * "show juniors" switch. Storage can be missing or throw (private window,
 * blocked site data), so every read and write is guarded and the screen works
 * the same without it. `valid` rejects a stale stored value. */
export default function usePersistedState(key, initial, valid) {
  const [value, setValue] = useState(() => {
    try {
      const raw = localStorage.getItem('bs_pref:' + key)
      if (raw != null) {
        const v = JSON.parse(raw)
        if (!valid || valid(v)) return v
      }
    } catch { /* fall through to the default */ }
    return initial
  })
  const set = useCallback((next) => {
    setValue((cur) => {
      const v = typeof next === 'function' ? next(cur) : next
      try { localStorage.setItem('bs_pref:' + key, JSON.stringify(v)) } catch { /* not available */ }
      return v
    })
  }, [key])
  return [value, set]
}
