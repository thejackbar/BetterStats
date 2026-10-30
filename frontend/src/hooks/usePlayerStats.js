import { useState, useEffect } from 'react'
import { api } from '../lib/api'

export function usePlayerStats(playerId, filters = {}) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!playerId) return
    // /players/:playerId is one mounted page, so moving to another player (the search box, a
    // teammate link) re-runs this effect on the SAME instance. An error from one load stayed
    // in state and drew "Error: Player not found" over every player after it until a full
    // reload; each load now starts clean, and a reply from a load we have left is ignored.
    let cancelled = false
    setLoading(true)
    setError(null)
    api.getPlayerStats(playerId, filters)
      .then(d => { if (!cancelled) setData(d) })
      .catch(e => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // `categories`, `formats`, `competitions` and `grades` belong in the dependency
    // list, not just the request: without them, switching Grade Type, Match
    // Type or Competition would build a new query and never re-run the effect,
    // leaving the old figures on screen.
  }, [playerId, filters.seasonId, filters.gradeId, filters.categories,
      filters.formats, filters.competitions, filters.grades])

  return { data, loading, error }
}
