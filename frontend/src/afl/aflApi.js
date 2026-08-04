// BetterStats AFL API client — the AFL silo's endpoints only. Auth + club
// resolution reuse the shared client (`api` from lib/api.js): the AFL backend
// serves the same /auth/* and /clubs/{slug} shapes.
const BASE = import.meta.env.VITE_API_URL || (import.meta.env.BASE_URL + 'api')

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...options.headers }
  const res = await fetch(`${BASE}${path}`, { ...options, headers, credentials: 'include' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = typeof err.detail === 'string'
      ? err.detail
      : err.detail?.message || `HTTP ${res.status}`
    const error = new Error(detail)
    error.status = res.status
    if (err.detail && typeof err.detail === 'object') error.detail = err.detail
    throw error
  }
  if (res.status === 204) return null
  const text = await res.text()
  return text ? JSON.parse(text) : null
}

const qs = (params) => {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== '' && v != null && v !== false) p.append(k, v)
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const aflApi = {
  // Public
  getSummary: (orgId, params) => request(`/organisations/${orgId}/summary${qs(params)}`),
  getResults: (orgId, params) => request(`/organisations/${orgId}/results${qs(params)}`),
  getGame: (gameId) => request(`/games/${gameId}`),
  listPlayers: (orgId) => request(`/afl-players/by-org/${orgId}`),
  getPlayer: (playerId) => request(`/afl-players/${playerId}`),
  comparePlayers: (orgId, ids) => request(`/afl-players/compare${qs({ org_id: orgId, ids: ids.join(',') })}`),
  getRecords: (orgId, params) => request(`/afl-records/${orgId}${qs(params)}`),
  getLeaderboard: (orgId, params) => request(`/afl-leaderboard/${orgId}${qs(params)}`),

  // Admin
  syncNow: () => request('/club-admin/sync', { method: 'POST' }),
  fullRebuild: () => request('/club-admin/full-rebuild', { method: 'POST' }),
  getSyncRuns: () => request('/club-admin/sync-runs'),
  getAdminSettings: () => request('/club-admin/settings'),
  patchAdminSettings: (body) => request('/club-admin/settings', { method: 'PATCH', body: JSON.stringify(body) }),
  registerClub: (playhqOrgId) => request('/club-admin/register-club', {
    method: 'POST', body: JSON.stringify({ playhq_org_id: playhqOrgId }),
  }),

  // Admin — Players
  adminListPlayers: () => request('/club-admin/players'),
  adminGetPlayer: (id) => request(`/club-admin/players/${id}`),
  adminCreatePlayer: (body) => request('/club-admin/players', { method: 'POST', body: JSON.stringify(body) }),
  adminPatchPlayer: (id, body) => request(`/club-admin/players/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),

  // Admin — Import Players (CSV contact importer)
  playerImportTemplateUrl: () => `${BASE}/club-admin/player-import/template.csv`,
  playerImportPreview: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch(`${BASE}/club-admin/player-import/preview`, { method: 'POST', body: fd, credentials: 'include' })
      .then(async (res) => {
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Preview failed')
        return res.json()
      })
  },
  playerImportCommit: (rows) => request('/club-admin/player-import/commit', {
    method: 'POST', body: JSON.stringify({ rows }),
  }),

  // Admin — Merge Grades
  gradeNames: () => request('/club-admin/grade-names'),
  mergeGrades: (aliasName, canonicalName) => request('/club-admin/merge-grades', {
    method: 'POST', body: JSON.stringify({ alias_name: aliasName, canonical_name: canonicalName }),
  }),
  gradeMergeHistory: () => request('/club-admin/grade-merge-history'),
  undoGradeMerge: (mergeLogId) => request('/club-admin/undo-grade-merge', {
    method: 'POST', body: JSON.stringify({ merge_log_id: mergeLogId }),
  }),

  // Admin — Award Definitions (catalog)
  listAwardDefinitions: () => request('/award-definitions'),
  createAwardDefinition: (body) => request('/award-definitions', { method: 'POST', body: JSON.stringify(body) }),
  updateAwardDefinition: (id, body) => request(`/award-definitions/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteAwardDefinition: (id) => request(`/award-definitions/${id}`, { method: 'DELETE' }),
  seedAwardDefinitions: (template = 'starter') => request(`/award-definitions/seed?template=${template}`, { method: 'POST' }),

  // Admin — Awards (recorded achievements)
  listAchievements: (params) => request(`/achievements${qs(params)}`),
  createAchievement: (body) => request('/achievements', { method: 'POST', body: JSON.stringify(body) }),
  updateAchievement: (id, body) => request(`/achievements/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteAchievement: (id) => request(`/achievements/${id}`, { method: 'DELETE' }),
  achievementsTemplateUrl: () => `${BASE}/achievements/template`,
  importAchievements: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch(`${BASE}/achievements/import`, { method: 'POST', body: fd, credentials: 'include' })
      .then(async (res) => {
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Import failed')
        return res.json()
      })
  },
  listAchievementImports: () => request('/achievements/imports'),
  undoAchievementImport: (batchId) => request(`/achievements/imports/${batchId}/undo`, { method: 'POST' }),

  // Admin — Sponsors
  listSponsors: () => request('/club-admin/sponsors'),
  createSponsor: (body) => request('/club-admin/sponsors', { method: 'POST', body: JSON.stringify(body) }),
  patchSponsor: (id, body) => request(`/club-admin/sponsors/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteSponsor: (id) => request(`/club-admin/sponsors/${id}`, { method: 'DELETE' }),
  uploadSponsorLogo: (id, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch(`${BASE}/club-admin/sponsors/${id}/logo`, { method: 'POST', body: fd, credentials: 'include' })
      .then(async (res) => {
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Upload failed')
        return res.json()
      })
  },
  deleteSponsorLogo: (id) => request(`/club-admin/sponsors/${id}/logo`, { method: 'DELETE' }),
  reorderSponsors: (items) => request('/club-admin/sponsors/reorder', { method: 'PUT', body: JSON.stringify(items) }),

  // Admin — Users (club-scoped)
  listClubUsers: () => request('/club-admin/users'),
  listCapabilities: () => request('/club-admin/users/capabilities'),
  createClubUser: (body) => request('/club-admin/users', { method: 'POST', body: JSON.stringify(body) }),
  updateClubUser: (id, body) => request(`/club-admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteClubUser: (id) => request(`/club-admin/users/${id}`, { method: 'DELETE' }),
  sendPasswordReset: (id) => request(`/club-admin/users/${id}/send-password-reset`, { method: 'POST' }),

  // Admin — Better HQ: Users (platform-wide)
  superListUsers: () => request('/club-admin/super/users'),
  superCreateUser: (body) => request('/club-admin/super/users', { method: 'POST', body: JSON.stringify(body) }),
  superUpdateUser: (id, body) => request(`/club-admin/super/users/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  superDeleteUser: (id) => request(`/club-admin/super/users/${id}`, { method: 'DELETE' }),
  superResetPassword: (id, newPassword) => request(`/club-admin/super/users/${id}/reset-password`, {
    method: 'POST', body: JSON.stringify({ new_password: newPassword }),
  }),

  // Admin — Merge Players
  mergeCandidates: () => request('/club-admin/merge-candidates'),
  playerMergeInfo: (playerId) => request(`/club-admin/player-info/${playerId}`),
  ignorePair: (playerAId, playerBId) => request('/club-admin/ignore-pair', {
    method: 'POST', body: JSON.stringify({ player_a_id: playerAId, player_b_id: playerBId }),
  }),
  playerMergeHistory: () => request('/club-admin/merge-history'),
  mergePlayers: (keepPlayerId, removePlayerId) => request('/club-admin/merge-players', {
    method: 'POST', body: JSON.stringify({ keep_player_id: keepPlayerId, remove_player_id: removePlayerId }),
  }),
  undoMergePlayers: (mergeLogId) => request('/club-admin/undo-merge-players', {
    method: 'POST', body: JSON.stringify({ merge_log_id: mergeLogId }),
  }),

  // Admin — Better HQ: All Clubs
  superListClubs: (params) => request(`/club-admin/super/clubs${qs(params)}`),
  superCreateClub: (playhqOrgId, syncNow = true) => request('/club-admin/super/clubs', {
    method: 'POST', body: JSON.stringify({ playhq_org_id: playhqOrgId, sync_now: syncNow }),
  }),
  superPatchClub: (id, body) => request(`/club-admin/super/clubs/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  superArchiveClub: (id) => request(`/club-admin/super/clubs/${id}/archive`, { method: 'POST' }),
  superRestoreClub: (id) => request(`/club-admin/super/clubs/${id}/restore`, { method: 'POST' }),
  superSyncClub: (id) => request(`/club-admin/super/clubs/${id}/sync`, { method: 'POST' }),
  superListClubAdmins: (id) => request(`/club-admin/super/clubs/${id}/admins`),
  superSetPrimaryAdmin: (id, userId) => request(`/club-admin/super/clubs/${id}/primary-admin`, {
    method: 'PUT', body: JSON.stringify({ user_id: userId }),
  }),
}

// Score formatting: AFL scores read "14.8 (92)" — goals.behinds (points).
export const scoreLine = (goals, behinds, score) =>
  (goals == null && score == null) ? '—'
    : `${goals ?? 0}.${behinds ?? 0} (${score ?? (goals ?? 0) * 6 + (behinds ?? 0)})`
