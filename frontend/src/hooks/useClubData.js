import { useState, useEffect } from 'react'
import { api } from '../lib/api'

export function useClubData(orgId) {
  const [org, setOrg] = useState(null)
  const [seasons, setSeasons] = useState([])
  const [grades, setGrades] = useState([])
  const [selectedSeason, setSelectedSeason] = useState(null)
  const [selectedGrade, setSelectedGrade] = useState(null)
  const [finalsOnly, setFinalsOnly] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!orgId) return
    setLoading(true)
    Promise.all([api.getOrg(orgId), api.getOrgSeasons(orgId)])
      .then(([orgData, seasonsData]) => {
        setOrg(orgData)
        setSeasons(seasonsData)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [orgId])

  useEffect(() => {
    if (!orgId || !selectedSeason) return
    api.getSeasonGrades(orgId, selectedSeason)
      .then(data => {
        setGrades(data)
        setSelectedGrade(null)
      })
      .catch(() => setGrades([]))
  }, [orgId, selectedSeason])

  return {
    org, seasons, grades,
    selectedSeason, setSelectedSeason,
    selectedGrade, setSelectedGrade,
    finalsOnly, setFinalsOnly,
    loading, error,
  }
}

export function useRecentGames(orgId, { seasonId, gradeId, categories, formats } = {}) {
  const [games, setGames] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!orgId) return
    setLoading(true)
    api.listGames(orgId, { seasonId, gradeId, limit: 10, categories, formats })
      .then(setGames)
      .catch(() => setGames([]))
      .finally(() => setLoading(false))
  }, [orgId, seasonId, gradeId, categories, formats])

  return { games, loading }
}
