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
  }, [playerId, filters.seasonId, filters.gradeId])

  return { data, loading, error }
}
