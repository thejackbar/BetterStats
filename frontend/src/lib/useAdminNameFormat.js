import { useEffect, useState } from 'react'
import { api } from './api'
import { formatPlayerName } from './nameFormat'

// One settings fetch per page load, shared by every admin screen that prints
// player names. Falls back to "Last, First" if the settings call fails.
let cached = null
let pending = null

function loadFormat() {
  if (cached) return Promise.resolve(cached)
  if (!pending) {
    pending = api.adminGetSettings()
      .then((s) => { cached = s?.player_name_format || 'last_first'; return cached })
      .catch(() => 'last_first')
      .finally(() => { pending = null })
  }
  return pending
}

/** Call after the club saves a new name format so open screens pick it up. */
export function setAdminNameFormat(format) {
  cached = format || 'last_first'
}

/**
 * Returns fmt(name) bound to the club's player_name_format (Settings).
 * Use for display only: sorting and searching keep working on the stored name.
 */
export function useAdminNameFormat() {
  const [format, setFormat] = useState(cached || 'last_first')
  useEffect(() => {
    let live = true
    loadFormat().then((f) => { if (live) setFormat(f) })
    return () => { live = false }
  }, [])
  return (name) => formatPlayerName(name, format)
}
