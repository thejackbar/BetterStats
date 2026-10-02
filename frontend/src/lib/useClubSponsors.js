import { useEffect, useState } from 'react'
import { api } from './api'

// One fetch of a club's sponsors, shared by everything on the page that draws
// them (the dashboard slot, the sponsor list, the bottom bar). The public
// endpoint returns every sponsor with the spots each one shows in; callers pick
// their own spot with `forSpot`.
const TTL_MS = 60 * 1000
const cache = new Map() // slug -> { at, data, promise }

function load(slug) {
  const hit = cache.get(slug)
  if (hit && hit.data !== undefined && Date.now() - hit.at < TTL_MS) return Promise.resolve(hit.data)
  if (hit && hit.promise) return hit.promise
  const promise = api.getClubSponsors(slug)
    .then((data) => { cache.set(slug, { at: Date.now(), data }); return data })
    .catch(() => { cache.delete(slug); return null })
  cache.set(slug, { at: 0, data: undefined, promise })
  return promise
}

// Forget a club's cached sponsors, so the next read refetches. The admin screen
// calls this after a save so the public pages in the same tab are not stale.
export function clearClubSponsors(slug) {
  if (slug) cache.delete(slug)
  else cache.clear()
}

function peek(slug) {
  const hit = cache.get(slug)
  return hit && hit.data !== undefined ? hit.data : null
}

export function useClubSponsors(slug) {
  const [data, setData] = useState(() => (slug ? peek(slug) : null))
  useEffect(() => {
    let live = true
    // Never show the previous club's sponsors while the next club's load.
    setData(slug ? peek(slug) : null)
    if (!slug) return undefined
    load(slug).then((d) => { if (live) setData(d) })
    return () => { live = false }
  }, [slug])
  return data
}

// The sponsors showing in one spot: 'dashboard' | 'bar' | 'footer'.
// The dashboard slot and the bar draw logos, so they skip a sponsor without one.
export function forSpot(data, spot) {
  const list = (data && data.sponsors) || []
  return list.filter((s) => (s.placements || []).includes(spot) && (spot === 'footer' || s.logo_url))
}
