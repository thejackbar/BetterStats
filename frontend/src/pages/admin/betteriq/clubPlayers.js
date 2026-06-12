/* BetterIQ — the club's full five-year player list, shared by the scout pages.
 *
 * The dossier squad only contains players seen in the CURRENT-season scan, so
 * anyone who hasn't played this season was unsearchable and unselectable on the
 * club page even when the vs-us player search had just surfaced them (the
 * "S Morgan: top of the search, gone on the club page" bug). This hook pulls
 * the club's whole career-window roster (every player CA's aggregates know
 * about, with their participant GUIDs) and the helpers merge it into a page's
 * squad index so a five-year veteran is always reachable.
 */
import { useState, useEffect, useRef } from 'react'
import { api } from '../../../lib/api'

const POLL_MS = 3000

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
export const isOrgGuid = (s) => UUID_RE.test(s || '')

/* Poll the club-players list ({status, players}) for a club's CA org GUID. */
export function useClubPlayers(orgGuid, clubName) {
  const [data, setData] = useState(null)
  const timerRef = useRef(null)
  useEffect(() => {
    setData(null)
    if (!orgGuid) return
    let alive = true
    const poll = () => {
      api.iqClubPlayers({ org: orgGuid, clubName }).then(d => {
        if (!alive) return
        setData(d)
        if (d?.status === 'building') timerRef.current = setTimeout(poll, POLL_MS)
      }).catch(() => { if (alive) setData({ status: 'error' }) })
    }
    poll()
    return () => { alive = false; if (timerRef.current) clearTimeout(timerRef.current) }
  }, [orgGuid])  // eslint-disable-line react-hooks/exhaustive-deps
  return data
}

/* Career-window players NOT in the dossier squad index, as selectable entries.
   Shape mirrors buildOppPlayerIndex values plus `careerOnly` + `career`. */
export function careerOnlyEntries(index, clubPlayers) {
  const list = clubPlayers?.status === 'ready' ? clubPlayers.players || [] : []
  return list
    .filter(p => p.player_id && !index.has(p.player_id))
    .map(p => ({ id: p.player_id, name: p.name, bat: null, bowl: null, careerOnly: true, career: p }))
}

/* A career-only player's vs-us record, recovered from the dossier's
   historical-threats shelf (players who hurt us but aren't in the current
   squad) so the profile's "vs us" card still renders for them. */
export function entryWithThreat(entry, dossier) {
  if (!entry?.careerOnly) return entry
  const t = (dossier?.historical_threats || []).find(x => x.player_id === entry.id)
  if (!t) return entry
  return {
    ...entry,
    bat: {
      innings: 0,
      vs_us: {
        innings: t.innings, runs: t.runs, average: t.average,
        high_score: t.high_score, fifties: t.fifties, hundreds: t.hundreds,
      },
    },
  }
}

/* Score how well a candidate roster/career name matches a wanted name across
   the formats in play: our vs-us index holds "S Morgan", CA aggregates hold
   "Morgan, Simon", team sheets hold "Simon Morgan". Full-token hits score 2,
   initial-vs-full hits score 1 — so "S Morgan" → "Morgan, Simon" scores 3 and
   beats "Morgan, David" (2). The old substring check matched none of these. */
export function nameScore(want, candidate) {
  const tok = (s) => (s || '').toLowerCase().replace(/[.]/g, ' ').split(/[\s,]+/).filter(Boolean)
  const w = tok(want)
  const c = tok(candidate)
  if (!w.length || !c.length) return 0
  let score = 0
  for (const t of w) {
    if (t.length > 1 && c.includes(t)) score += 2
    else if (t.length === 1 && c.some(x => x[0] === t)) score += 1
    else if (t.length > 1 && c.some(x => x.length === 1 && x === t[0])) score += 1
  }
  return score
}

/* Best match for a wanted name in a list of entries (≥2 = at least a full-token
   hit, e.g. the surname). Ties break towards the bigger career/season. */
export function bestNameMatch(want, entries) {
  const scored = entries
    .map(p => ({ p, s: nameScore(want, p.name) }))
    .filter(x => x.s >= 2)
    .sort((a, b) =>
      b.s - a.s
      || ((b.p.career?.runs || b.p.bat?.runs || 0) - (a.p.career?.runs || a.p.bat?.runs || 0)))
  return scored[0]?.p || null
}
