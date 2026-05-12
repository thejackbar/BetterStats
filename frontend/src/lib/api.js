const BASE = import.meta.env.VITE_API_URL || '/api'

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...options.headers }
  const res = await fetch(`${BASE}${path}`, { ...options, headers, credentials: 'include' })
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
  // Clubs (slug-based)
  getClubBySlug: (slug) => request(`/clubs/${slug}`),

  // Organisations (UUID-based, used internally once slug is resolved)
  searchOrgs: (q) => request(`/organisations/search?q=${encodeURIComponent(q)}`),
  onboard: (orgId, orgName = '') =>
    request('/organisations/onboard', { method: 'POST', body: JSON.stringify({ org_id: orgId, org_name: orgName }) }),
  listOrgs: () => request('/organisations'),
  getOrg: (orgId) => request(`/organisations/${orgId}`),
  getOrgSeasons: (orgId) => request(`/organisations/${orgId}/seasons`),
  getSeasonGrades: (orgId, seasonId) => request(`/organisations/${orgId}/seasons/${seasonId}/grades`),
  triggerSync: (orgId) => request(`/organisations/${orgId}/sync`, { method: 'POST' }),
  getSyncLogs: (orgId) => request(`/organisations/${orgId}/sync-logs`),
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
  requestPlayerSync: (playerId, note) =>
    request(`/players/${playerId}/request-sync`, { method: 'POST', body: JSON.stringify({ note }) }),

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

  // Admin / merge tools
  getMergeCandidates: (orgId) => request(`/admin/merge-candidates?org_id=${orgId}`),
  getMergeHistory: (orgId) => request(`/admin/merge-history?org_id=${orgId}`),
  getPlayerMergeInfo: (playerId, orgId) => request(`/admin/player-info?player_id=${playerId}&org_id=${orgId}`),
  mergePlayers: (keepPlayerId, removePlayerId, orgId) =>
    request('/admin/merge-players', {
      method: 'POST',
      body: JSON.stringify({ keep_player_id: keepPlayerId, remove_player_id: removePlayerId, org_id: orgId }),
    }),
  ignorePair: (playerAId, playerBId, orgId) =>
    request('/admin/ignore-pair', {
      method: 'POST',
      body: JSON.stringify({ player_a_id: playerAId, player_b_id: playerBId, org_id: orgId }),
    }),
  undoMerge: (mergeLogId, orgId) =>
    request('/admin/undo-merge', {
      method: 'POST',
      body: JSON.stringify({ merge_log_id: mergeLogId, org_id: orgId }),
    }),

  // Grade merge tools
  listGradesWithStats: (orgId) => request(`/admin/grades-with-stats?org_id=${orgId}`),
  mergeGrades: (orgId, aliasName, canonicalName) =>
    request('/admin/merge-grades', {
      method: 'POST',
      body: JSON.stringify({ org_id: orgId, alias_name: aliasName, canonical_name: canonicalName }),
    }),
  getGradeMergeHistory: (orgId) => request(`/admin/grade-merge-history?org_id=${orgId}`),
  undoGradeMerge: (mergeLogId, orgId) =>
    request('/admin/undo-grade-merge', {
      method: 'POST',
      body: JSON.stringify({ merge_log_id: mergeLogId, org_id: orgId }),
    }),

  // Club admin
  adminListPlayers: () => request('/club-admin/players'),
  adminPatchPlayer: (playerId, data) =>
    request(`/club-admin/players/${playerId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  adminListSeasons: () => request('/club-admin/seasons'),
  adminListGames: (seasonId) => {
    const params = new URLSearchParams()
    if (seasonId) params.set('season_id', seasonId)
    return request(`/club-admin/games?${params}`)
  },
  adminGetSettings: () => request('/club-admin/settings'),
  adminPatchSettings: (data) =>
    request('/club-admin/settings', { method: 'PATCH', body: JSON.stringify(data) }),
  adminListPartnershipRecords: () => request('/club-admin/partnership-records'),
  adminCreatePartnershipRecord: (data) =>
    request('/club-admin/partnership-records', { method: 'POST', body: JSON.stringify(data) }),
  adminDeletePartnershipRecord: (id) =>
    request(`/club-admin/partnership-records/${id}`, { method: 'DELETE' }),
  adminPatchPartnershipRecord: (id, data) =>
    request(`/club-admin/partnership-records/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  adminListGrades: () => request('/club-admin/grades'),
  adminRenamePartnershipGrade: (oldName, newName) =>
    request('/club-admin/partnership-records/rename-grade', {
      method: 'POST',
      body: JSON.stringify({ old_name: oldName, new_name: newName }),
    }),
  adminDownloadPartnershipTemplate: () =>
    fetch(`${BASE}/club-admin/partnership-records/template`, { credentials: 'include' }),
  adminImportPartnershipRecords: (file) => {
    const form = new FormData()
    form.append('file', file)
    return fetch(`${BASE}/club-admin/partnership-records/import`, {
      method: 'POST',
      body: form,
      credentials: 'include',
    }).then(async r => {
      const text = await r.text()
      try {
        return JSON.parse(text)
      } catch {
        throw new Error(`Server error (${r.status}): ${text.slice(0, 120)}`)
      }
    })
  },
  adminListSyncRequests: () => request('/club-admin/sync-requests'),
  adminActionSyncRequest: (id, action, adminNote) =>
    request(`/club-admin/sync-requests/${id}`, {
      method: 'POST',
      body: JSON.stringify({ action, admin_note: adminNote }),
    }),
  adminHardRefreshOrg: () =>
    request('/club-admin/hard-refresh', { method: 'POST' }),
  adminListSyncRuns: (limit = 30) =>
    request(`/club-admin/sync-runs?limit=${limit}`),
  adminGetSyncRun: (runId) => request(`/club-admin/sync-runs/${runId}`),
  adminClearSyncRuns: () =>
    request('/club-admin/sync-runs', { method: 'DELETE' }),
  adminClearResolvedSyncRequests: () =>
    request('/club-admin/sync-requests/resolved', { method: 'DELETE' }),
  adminListPhqSuggestions: () => request('/club-admin/phq-suggestions'),
  adminRunPhqSuggestions: () => request('/club-admin/phq-suggestions/run', { method: 'POST' }),
  adminActionPhqSuggestion: (id, action, playerId) =>
    request(`/club-admin/phq-suggestions/${id}`, {
      method: 'POST',
      body: JSON.stringify({ action, player_id: playerId }),
    }),

  // Super admin
  superListClubs: () => request('/club-admin/super/clubs'),
  superCreateClub: (data) =>
    request('/club-admin/super/clubs', { method: 'POST', body: JSON.stringify(data) }),
  superPatchClub: (clubId, data) =>
    request(`/club-admin/super/clubs/${clubId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  superListUsers: () => request('/club-admin/super/users'),
  superCreateUser: (data) =>
    request('/club-admin/super/users', { method: 'POST', body: JSON.stringify(data) }),
  superResetPassword: (userId, newPassword) =>
    request(`/club-admin/super/users/${userId}/reset-password`, {
      method: 'POST',
      body: JSON.stringify({ new_password: newPassword }),
    }),

  // Achievements
  listAchievements: (orgId, { playerId, season } = {}) => {
    const params = new URLSearchParams({ org_id: orgId })
    if (playerId) params.set('player_id', playerId)
    if (season) params.set('season', season)
    return request(`/achievements?${params}`)
  },
  createAchievement: (data) =>
    request('/achievements', { method: 'POST', body: JSON.stringify(data) }),
  updateAchievement: (id, data) =>
    request(`/achievements/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteAchievement: (id, orgId) =>
    request(`/achievements/${id}?org_id=${orgId}`, { method: 'DELETE' }),
  downloadAchievementsTemplate: () =>
    fetch(`${BASE}/achievements/template`, { credentials: 'include' }),
  importAchievements: (orgId, file) => {
    const form = new FormData()
    form.append('file', file)
    return fetch(`${BASE}/achievements/import?org_id=${orgId}`, {
      method: 'POST',
      body: form,
      credentials: 'include',
    }).then(r => r.json())
  },

  // StatLab
  statlabQuery: (orgId, { mode = 'career', seasonId, groupBy = 'player', sortBy = 'runs', sortDir = 'desc', limit = 100, filters = [] } = {}) => {
    const params = new URLSearchParams({ org_id: orgId, mode, group_by: groupBy, sort_by: sortBy, sort_dir: sortDir, limit })
    if (seasonId) params.set('season_id', seasonId)
    filters.forEach(f => params.append('filters', f))
    return request(`/statlab/query?${params}`)
  },

  // Records
  getRecords: (orgId, { seasonId, gradeId } = {}) => {
    const params = new URLSearchParams()
    if (seasonId) params.set('season_id', seasonId)
    if (gradeId) params.set('grade_id', gradeId)
    return request(`/records/${orgId}?${params}`)
  },
  getRecordsGrades: (orgId, seasonId) => {
    const params = new URLSearchParams()
    if (seasonId) params.set('season_id', seasonId)
    return request(`/records/${orgId}/grades?${params}`)
  },

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
