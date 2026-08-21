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
  getPremierships: (orgId) => request(`/afl-honours/${orgId}/premierships`),
  getOfficeBearers: (orgId) => request(`/afl-honours/${orgId}/office-bearers`),

  // Admin
  syncNow: () => request('/club-admin/sync', { method: 'POST' }),
  fullRebuild: () => request('/club-admin/full-rebuild', { method: 'POST' }),
  getSyncRuns: () => request('/club-admin/sync-runs'),
  // A grade discoverTeams can't see any more (a team re-graded mid-season) —
  // paste a match link from it and pull the whole grade in directly.
  linkGradePreview: (ref) => request('/club-admin/link-grade/preview', {
    method: 'POST', body: JSON.stringify({ ref }),
  }),
  linkGrade: (seasonId, ref) => request('/club-admin/link-grade', {
    method: 'POST', body: JSON.stringify({ season_id: seasonId, ref }),
  }),
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
  // Multipart, so it goes around request() (which sets a JSON content-type —
  // setting it by hand on a FormData body strips the multipart boundary).
  adminUploadPlayerPhoto: (id, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch(`${BASE}/club-admin/players/${id}/photo`, {
      method: 'POST', body: fd, credentials: 'include',
    }).then(async (res) => {
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Upload failed')
      return res.json()
    })
  },
  adminDeletePlayerPhoto: (id) => request(`/club-admin/players/${id}/photo`, { method: 'DELETE' }),

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
  listGradesWithStats: () => request('/club-admin/grades-with-stats'),
  classifyGrade: (gradeName, { category, is_public, display_name, display_order } = {}) => request('/club-admin/grades/classify', {
    method: 'PATCH',
    body: JSON.stringify({ grade_name: gradeName, category, is_public, display_name, display_order }),
  }),
  applyGradeSuggestions: (force = false) => request(
    `/club-admin/grades/apply-suggestions${force ? '?force=true' : ''}`, { method: 'POST' }),
  // The whole reading order in one write — the server numbers 1..N from the
  // submitted order, so the browser never sends the numbers themselves.
  reorderGrades: (gradeNames) => request('/club-admin/grades/reorder', {
    method: 'POST', body: JSON.stringify({ grade_names: gradeNames }),
  }),
  clearGradeOrder: () => request('/club-admin/grades/clear-order', { method: 'POST' }),

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
  bulkIgnoreRedacted: () => request('/club-admin/merge-candidates/bulk-ignore-redacted', { method: 'POST' }),
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

  // Admin — Split Player (the inverse: two people recorded as one)
  splitPreview: (playerId) => request(`/club-admin/split-player/${playerId}`),
  splitPlayer: (playerId, seasonIds, newName) => request('/club-admin/split-player', {
    method: 'POST',
    body: JSON.stringify({ player_id: playerId, season_ids: seasonIds, new_name: newName }),
  }),

  // Admin — Seasons (list / rename / delete)
  adminListSeasons: () => request('/club-admin/seasons'),
  adminRenameSeason: (id, body) => request(`/club-admin/seasons/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  adminDeleteSeason: (id) => request(`/club-admin/seasons/${id}`, { method: 'DELETE' }),

  // Admin — Manual stat entries (adjustments). Seasons come from the Import
  // Stats endpoints below: same club seasons, same create path, deliberately
  // not duplicated.
  adjustmentsList: () => request('/club-admin/manual-entries/adjustments'),
  adjustmentsCreate: (body) => request('/club-admin/manual-entries/adjustments', {
    method: 'POST', body: JSON.stringify(body),
  }),
  adjustmentsUpdate: (id, body) => request(`/club-admin/manual-entries/adjustments/${id}`, {
    method: 'PATCH', body: JSON.stringify(body),
  }),
  adjustmentsDelete: (id) => request(`/club-admin/manual-entries/adjustments/${id}`, { method: 'DELETE' }),
  adjustmentsTemplateUrl: () => `${BASE}/club-admin/manual-entries/adjustments/template.csv`,
  adjustmentsImport: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch(`${BASE}/club-admin/manual-entries/adjustments/import`, {
      method: 'POST', body: fd, credentials: 'include',
    }).then(async (res) => {
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body.detail || 'Upload failed')
      return body
    })
  },
  manualGrades: () => request('/club-admin/manual-entries/grades'),
  manualCreateGrade: (body) => request('/club-admin/manual-entries/grades', {
    method: 'POST', body: JSON.stringify(body),
  }),
  manualAudit: () => request('/club-admin/manual-entries/audit'),
  manualUndo: (logId) => request(`/club-admin/manual-entries/audit/${logId}/undo`, { method: 'POST' }),

  // Admin — Import Stats (historical CSV import)
  importsTemplateUrl: () => `${BASE}/club-admin/imports/template.csv`,
  importsSeasons: () => request('/club-admin/imports/seasons'),
  importsCreateSeason: (body) => request('/club-admin/imports/seasons', { method: 'POST', body: JSON.stringify(body) }),
  importsPreview: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch(`${BASE}/club-admin/imports/preview`, { method: 'POST', body: fd, credentials: 'include' })
      .then(async (res) => {
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Preview failed')
        return res.json()
      })
  },
  importsResolve: (body) => request('/club-admin/imports/resolve', { method: 'POST', body: JSON.stringify(body) }),
  importsCommit: (body) => request('/club-admin/imports/commit', { method: 'POST', body: JSON.stringify(body) }),
  importsList: () => request('/club-admin/imports'),
  importsBatchPlayers: (batchId) => request(`/club-admin/imports/${batchId}/players`),
  importsUndo: (batchId) => request(`/club-admin/imports/${batchId}/undo`, { method: 'POST' }),

  // Admin — Import Results (a club's own results register, one row per
  // match). Seasons come from the Import Stats endpoints above — same club
  // seasons, same create path, deliberately not duplicated.
  resultImportsTemplateUrl: () => `${BASE}/club-admin/result-imports/template.csv`,
  resultImportsPreview: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch(`${BASE}/club-admin/result-imports/preview`, { method: 'POST', body: fd, credentials: 'include' })
      .then(async (res) => {
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Preview failed')
        return res.json()
      })
  },
  resultImportsResolve: (body) => request('/club-admin/result-imports/resolve', { method: 'POST', body: JSON.stringify(body) }),
  resultImportsCommit: (body) => request('/club-admin/result-imports/commit', { method: 'POST', body: JSON.stringify(body) }),
  resultImportsList: () => request('/club-admin/result-imports'),
  resultImportsBatchGames: (batchId) => request(`/club-admin/result-imports/${batchId}/games`),
  resultImportsUndo: (batchId) => request(`/club-admin/result-imports/${batchId}/undo`, { method: 'POST' }),

  // Admin — Import Awards (a club's honour board). Writes the same
  // player_achievements rows the Awards screen reads, and adds any award the
  // club's Award Types catalogue doesn't carry yet.
  awardImportsTemplateUrl: () => `${BASE}/club-admin/award-imports/template.csv`,
  awardImportsPreview: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch(`${BASE}/club-admin/award-imports/preview`, { method: 'POST', body: fd, credentials: 'include' })
      .then(async (res) => {
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Preview failed')
        return res.json()
      })
  },
  awardImportsResolve: (body) => request('/club-admin/award-imports/resolve', { method: 'POST', body: JSON.stringify(body) }),
  awardImportsCommit: (body) => request('/club-admin/award-imports/commit', { method: 'POST', body: JSON.stringify(body) }),
  awardImportsList: () => request('/club-admin/award-imports'),
  awardImportsBatchAwards: (batchId) => request(`/club-admin/award-imports/${batchId}/awards`),
  awardImportsUndo: (batchId) => request(`/club-admin/award-imports/${batchId}/undo`, { method: 'POST' }),

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

  // ─── Team lists (public) ──────────────────────────────────────────────────
  // The side PlayHQ returned with each game, read from what the sync stored.
  aflLineupGames: (orgId, { season_id, grade_id, limit, offset } = {}) => {
    const q = new URLSearchParams()
    if (season_id) q.set('season_id', season_id)
    if (grade_id) q.set('grade_id', grade_id)
    if (limit) q.set('limit', limit)
    if (offset) q.set('offset', offset)
    const qs = q.toString()
    return request(`/afl-lineups/organisations/${orgId}/games${qs ? `?${qs}` : ''}`)
  },
  aflGameLineups: (gameId, orgId) => request(`/afl-lineups/games/${gameId}?org_id=${orgId}`),

  // ─── Votes (admin) ────────────────────────────────────────────────────────
  // Every call names the MEDAL it acts on; omitting it falls back server-side
  // to the club's first medal.
  votesMedals: () => request('/votes/medals'),
  votesCreateMedal: (data) => request('/votes/medals', { method: 'POST', body: JSON.stringify(data) }),
  votesUpdateMedal: (id, data) => request(`/votes/medals/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  votesDeleteMedal: (id, { confirm } = {}) =>
    request(`/votes/medals/${id}${confirm ? '?confirm=true' : ''}`, { method: 'DELETE' }),
  votesRegenerateLink: (id) => request(`/votes/medals/${id}/regenerate`, { method: 'POST' }),
  votesGames: ({ season_id, grade_id, round_key, q, medal_id } = {}) => {
    const p = new URLSearchParams()
    if (season_id) p.set('season_id', season_id)
    if (grade_id) p.set('grade_id', grade_id)
    if (round_key) p.set('round_key', round_key)
    if (q) p.set('q', q)
    if (medal_id) p.set('medal_id', medal_id)
    const qs = p.toString()
    return request(`/votes/games${qs ? `?${qs}` : ''}`)
  },
  votesGameDetail: (gameId, medalId) =>
    request(`/votes/games/${gameId}${medalId ? `?medal_id=${medalId}` : ''}`),
  votesAdminBallot: (gameId, medalId, data) =>
    request(`/votes/games/${gameId}/ballots${medalId ? `?medal_id=${medalId}` : ''}`,
      { method: 'POST', body: JSON.stringify(data) }),
  votesDeleteBallot: (ballotId) => request(`/votes/ballots/${ballotId}`, { method: 'DELETE' }),
  votesLockGame: (gameId, medalId) =>
    request(`/votes/games/${gameId}/lock${medalId ? `?medal_id=${medalId}` : ''}`, { method: 'POST' }),
  votesReopenGame: (gameId, medalId) =>
    request(`/votes/games/${gameId}/reopen${medalId ? `?medal_id=${medalId}` : ''}`, { method: 'POST' }),
  votesBulkState: (body) => request('/votes/bulk-state', { method: 'POST', body: JSON.stringify(body) }),
  votesNudge: (body) => request('/votes/nudge', { method: 'POST', body: JSON.stringify(body) }),
  votesLeaderboard: ({ season_id, grade_id, through_round, medal_id } = {}) => {
    const p = new URLSearchParams()
    if (season_id) p.set('season_id', season_id)
    if (grade_id) p.set('grade_id', grade_id)
    if (through_round) p.set('through_round', through_round)
    if (medal_id) p.set('medal_id', medal_id)
    const qs = p.toString()
    return request(`/votes/leaderboard${qs ? `?${qs}` : ''}`)
  },

  // ─── Votes (public link; no admin auth) ───────────────────────────────────
  votePublicLanding: (token, { team } = {}) =>
    request(`/public/votes/${token}${team ? `?team=${team}` : ''}`),
  votePublicVerify: (token, player_id, pin) =>
    request(`/public/votes/${token}/verify`, { method: 'POST', body: JSON.stringify({ player_id, pin }) }),
  votePublicSwitch: (token) => request(`/public/votes/${token}/switch`, { method: 'POST' }),
  votePublicGame: (token, gameId) => request(`/public/votes/${token}/games/${gameId}`),
  votePublicSubmit: (token, gameId, data) =>
    request(`/public/votes/${token}/games/${gameId}/ballot`, { method: 'POST', body: JSON.stringify(data) }),
}

/**
 * Resolve a stored image path to something the browser can fetch.
 *
 * A player photo uploaded through the admin is stored API-relative
 * ("images/players/{id}/photo?v=…") rather than as an absolute "/api/…" path,
 * because the AFL app is served under /afl/ and cricket's absolute form would
 * 404 here. Anything already absolute — an http(s) URL, or a legacy value
 * starting with "/" — is handed back untouched, so a PlayHQ club crest and an
 * uploaded photo can sit in the same column.
 */
export const mediaUrl = (path) => {
  if (!path) return path
  if (/^(https?:)?\/\//.test(path) || path.startsWith('/') || path.startsWith('data:')) return path
  return `${BASE}/${path}`
}

// Score formatting: AFL scores read "14.8 (92)" — goals.behinds (points).
export const scoreLine = (goals, behinds, score) =>
  (goals == null && score == null) ? '—'
    : `${goals ?? 0}.${behinds ?? 0} (${score ?? (goals ?? 0) * 6 + (behinds ?? 0)})`
