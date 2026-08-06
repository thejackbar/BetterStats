import { useState, useEffect } from 'react'
import { api } from '../lib/api'

export function usePlayerStats(playerId, filters = {}) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!playerId) return
    setLoading(true)
    api.getPlayerStats(playerId, filters)
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
    // `categories` belongs in the dependency list, not just the request: without
    // it, switching the Juniors toggle would send a new query and never re-run
    // the effect, leaving the old figures on screen.
  }, [playerId, filters.seasonId, filters.gradeId, filters.categories])

  return { data, loading, error }
}
