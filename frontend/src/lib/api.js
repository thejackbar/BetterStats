const BASE = import.meta.env.VITE_API_URL || '/api'

async function request(path, options = {}) {
  const token = localStorage.getItem('bs_token')
  const headers = { 'Content-Type': 'application/json', ...options.headers }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${BASE}${path}`, { ...options, headers })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = Array.isArray(err.detail)
      ? err.detail.map(e => e.msg || JSON.stringify(e)).join(', ')
      : (typeof err.detail === 'string' ? err.detail : `HTTP ${res.status}`)
    throw new Error(detail)
  }
  return res.json()
}

export const api = {
  // Auth
  register: (email, password) =>
    request('/auth/register', { method: 'POST', body: JSON.stringify({ email, password }) }),
  login: (email, password) => {
    const form = new URLSearchParams({ username: email, password })
    return fetch(`${BASE}/auth/token`, { method: 'POST', body: form, headers: {} })
      .then(r => r.json())
  },
  me: () => request('/auth/me'),

  // Organisations
  searchOrgs: (q) => request(`/organisations/search?q=${encodeURIComponent(q)}`),
  onboard: (orgId, orgName = '') =>
    request('/organisations/onboard', { method: 'POST', body: JSON.stringify({ org_id: orgId, org_name: orgName }) }),
  listOrgs: () => request('/organisations'),
  getOrg: (orgId) => request(`/organisations/${orgId}`),
  getOrgSeasons: (orgId) => request(`/organisations/${orgId}/seasons`),
  getSeasonGrades: (orgId, seasonId) => request(`/organisations/${orgId}/seasons/${seasonId}/grades`),
  triggerSync: (orgId) => request(`/organisations/${orgId}/sync`, { method: 'POST' }),
  getOrgSummary: (orgId, { seasonId, gradeId } = {}) => {
    const params = new URLSearchParams()
    if (seasonId) params.set('season_id', seasonId)
    if (gradeId) params.set('grade_id', gradeId)
    return request(`/organisations/${orgId}/summary?${params}`)
  },
  getUpcomingMilestones: (orgId, limit = 20) =>
    request(`/organisations/${orgId}/upcoming-milestones?limit=${limit}`),
  getRecentlyAchievedMilestones: (orgId) =>
    request(`/organisations/${orgId}/recently-achieved-milestones`),
  getOrgFixtures: (orgId) => request(`/organisations/${orgId}/fixtures`),

  // Players
  listPlayers: (orgId) => request(`/players?org_id=${orgId}`),
  getPlayer: (playerId) => request(`/players/${playerId}`),
  getPlayerStats: (playerId, { seasonId, gradeId } = {}) => {
    const params = new URLSearchParams()
    if (seasonId) params.set('season_id', seasonId)
    if (gradeId) params.set('grade_id', gradeId)
    return request(`/players/${playerId}/stats?${params}`)
  },
  getPlayerDismissals: (playerId) => request(`/players/${playerId}/dismissals`),
  getPlayerByPosition: (playerId) => request(`/players/${playerId}/by-position`),
  getPlayerByGrade: (playerId) => request(`/players/${playerId}/by-grade`),
  getPlayerSeasons: (playerId) => request(`/players/${playerId}/seasons`),
  getPlayerMilestones: (playerId) => request(`/players/${playerId}/milestones`),
  getPlayerPartnerships: (playerId) => request(`/players/${playerId}/partnerships`),
  getPlayerActivity: (playerId) => request(`/players/${playerId}/activity`),
  getPlayerUpcomingMilestones: (playerId) => request(`/players/${playerId}/upcoming-milestones`),
  claimPlayer: (playerId) =>
    request(`/players/${playerId}/claim`, { method: 'POST' }),

  // Games
  listGames: (orgId, { seasonId, gradeId, limit } = {}) => {
    const params = new URLSearchParams({ org_id: orgId })
    if (seasonId) params.set('season_id', seasonId)
    if (gradeId) params.set('grade_id', gradeId)
    if (limit) params.set('limit', limit)
    return request(`/games?${params}`)
  },
  getScorecard: (gameId) => request(`/games/${gameId}/scorecard`),
  getPlayHQGame: (orgId, gameId) => request(`/games/playhq/${gameId}?org_id=${encodeURIComponent(orgId)}`),
  getPlayHQScorecard: (orgId, gameId) => request(`/games/playhq/${gameId}/scorecard?org_id=${encodeURIComponent(orgId)}`),

  // Leaderboard
  battingLeaderboard: (orgId, { seasonId, gradeId, sortBy, limit } = {}) => {
    const params = new URLSearchParams({ org_id: orgId })
    if (seasonId) params.set('season_id', seasonId)
    if (gradeId) params.set('grade_id', gradeId)
    if (sortBy) params.set('sort_by', sortBy)
    if (limit) params.set('limit', limit)
    return request(`/leaderboard/batting?${params}`)
  },
  bowlingLeaderboard: (orgId, { seasonId, gradeId, sortBy, limit } = {}) => {
    const params = new URLSearchParams({ org_id: orgId })
    if (seasonId) params.set('season_id', seasonId)
    if (gradeId) params.set('grade_id', gradeId)
    if (sortBy) params.set('sort_by', sortBy)
    if (limit) params.set('limit', limit)
    return request(`/leaderboard/bowling?${params}`)
  },
  fieldingLeaderboard: (orgId, { seasonId, gradeId, limit } = {}) => {
    const params = new URLSearchParams({ org_id: orgId })
    if (seasonId) params.set('season_id', seasonId)
    if (gradeId) params.set('grade_id', gradeId)
    if (limit) params.set('limit', limit)
    return request(`/leaderboard/fielding?${params}`)
  },
}
