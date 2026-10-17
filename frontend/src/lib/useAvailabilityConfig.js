// The club settings every BetterSelect screen reads: whether the club offers
// "Maybe", the half-available colours, how far back the player pools reach, the
// per-team starting filters and the squads in XI order. Fetched once per page
// load and shared, so every screen and panel agrees without each asking.
import { useEffect, useState } from 'react'
import { api } from './api'

let current = {
  allow_maybe: true, half_colours: null, played_years: { selection: 3, availability: 0 },
  team_defaults: [], squads: [], loaded: false,
}
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

// One read for the whole page. Football has no such settings: a failed read
// leaves everything as it always was, and says so (loaded) so nobody waits on it.
function ensureLoaded() {
  if (loading) return
  loading = api.bsAvailabilityConfig().then((c) => publish({
    allow_maybe: c?.allow_maybe !== false,
    half_colours: c?.half_colours || null,
    ...(c?.played_years ? { played_years: c.played_years } : {}),
    team_defaults: c?.team_defaults || [],
    squads: c?.squads || [],
    loaded: true,
  })).catch(() => publish({ loaded: true }))
}

function useConfig() {
  const [cfg, setCfg] = useState(current)
  useEffect(() => {
    listeners.add(setCfg)
    ensureLoaded()
    setCfg(current)
    return () => { listeners.delete(setCfg) }
  }, [])
  return cfg
}

/* The Settings screen calls these so every open screen follows a change. */
export function setHalfColours(c) { publish({ half_colours: c }) }
export function setAllowMaybe(v) { publish({ allow_maybe: v !== false }) }
export function setSelectConfig(next) { publish(next) }

export function useAllowMaybe() { return useConfig().allow_maybe !== false }

/* Every BetterSelect screen mounts this once (the layout does), so the club's
   half-available colours are on the page before the first card is drawn. */
export function useHalfColours() { return useConfig().half_colours }

/* How far back a player may have last played to be listed (0 = any time), the
   per-team starting filters, and the squads in XI order. `ready` is false until
   the first read comes back, so a screen can wait instead of flashing defaults. */
export function useSelectConfig() {
  const cfg = useConfig()
  return { playedYears: cfg.played_years, teamDefaults: cfg.team_defaults || [], squads: cfg.squads || [], ready: !!cfg.loaded }
}
