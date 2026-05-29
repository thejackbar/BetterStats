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

// Encode a StatLab context dict into URLSearchParams. Arrays are repeated
// (?key=a&key=b) so the backend's `qp.getlist(k)` reads them as a list.
// Scalars (string / number / true) become a single value; null / undefined /
// '' / false are dropped.
function _appendContext(params, context) {
  Object.entries(context || {}).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '' || v === false) return
    if (Array.isArray(v)) {
      v.forEach(item => {
        if (item === undefined || item === null || item === '') return
        params.append(k, String(item))
      })
      return
    }
    params.set(k, v === true ? 'true' : String(v))
  })
}

export const api = {
  // Clubs (slug-based)
  getClubBySlug: (slug) => request(`/clubs/${slug}`),

  // Organisations (UUID-based, used internally once slug is resolved)
  searchOrgs: (q) => request(`/organisations/search?q=${encodeURIComponent(q)}`),
  getSocialScorecard: (matchId) => request(`/admin/social/scorecard/${matchId}`),
  onboard: (orgId, orgName = '') =>
    request('/organisations/onboard', { method: 'POST', body: JSON.stringify({ org_id: orgId, org_name: orgName }) }),
  listOrgs: () => request('/organisations'),
  getOrg: (orgId) => request(`/organisations/${orgId}`),
  getOrgSeasons: (orgId) => request(`/organisations/${orgId}/seasons`),
  getOrgGrades: (orgId, seasonId) => {
    const params = new URLSearchParams()
    if (seasonId) params.set('season_id', seasonId)
    const qs = params.toString()
    return request(`/organisations/${orgId}/grades${qs ? `?${qs}` : ''}`)
  },
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
  getPlayerStats: (playerId, { seasonId, gradeId, lastNGames, startDate, endDate } = {}) => {
    const params = new URLSearchParams()
    if (seasonId) params.set('season_id', seasonId)
    if (gradeId) params.set('grade_id', gradeId)
    if (lastNGames) params.set('last_n_games', lastNGames)
    if (startDate) params.set('start_date', startDate)
    if (endDate) params.set('end_date', endDate)
    return request(`/players/${playerId}/stats?${params}`)
  },
  getPlayerDismissals: (playerId) => request(`/players/${playerId}/dismissals`),
  getPlayerByPosition: (playerId) => request(`/players/${playerId}/by-position`),
  getPlayerByGrade: (playerId) => request(`/players/${playerId}/by-grade`),
  getPlayerBowlingByGrade: (playerId) => request(`/players/${playerId}/bowling-by-grade`),
  getPlayerBowlingDismissals: (playerId) => request(`/players/${playerId}/bowling-dismissals`),
  getPlayerBowlingByBatterPosition: (playerId) => request(`/players/${playerId}/bowling-by-batter-position`),
  getPlayerByVenue: (playerId) => request(`/players/${playerId}/by-venue`),
  getPlayerByOpposition: (playerId) => request(`/players/${playerId}/by-opposition`),
  getPlayerTeamBreakdown: (playerId, { seasonId } = {}) => {
    const params = new URLSearchParams()
    if (seasonId) params.set('season_id', seasonId)
    const qs = params.toString()
    return request(`/players/${playerId}/team-breakdown${qs ? `?${qs}` : ''}`)
  },
  getPlayerSeasons: (playerId) => request(`/players/${playerId}/seasons`),
  getPlayerMilestones: (playerId) => request(`/players/${playerId}/milestones`),
  getPlayerPartnerships: (playerId) => request(`/players/${playerId}/partnerships`),
  getPlayerActivity: (playerId) => request(`/players/${playerId}/activity`),
  getPlayerUpcomingMilestones: (playerId) => request(`/players/${playerId}/upcoming-milestones`),
  getPlayerRankings: (playerId, { seasonId } = {}) => {
    const params = new URLSearchParams()
    if (seasonId) params.set('season_id', seasonId)
    return request(`/players/${playerId}/rankings?${params}`)
  },
  requestPlayerSync: (playerId, note) =>
    request(`/players/${playerId}/request-sync`, { method: 'POST', body: JSON.stringify({ note }) }),

  // Games
  listGames: (orgId, { seasonId, gradeId, limit, finalsOnly } = {}) => {
    const params = new URLSearchParams({ org_id: orgId })
    if (seasonId) params.set('season_id', seasonId)
    if (gradeId) params.set('grade_id', gradeId)
    if (limit) params.set('limit', limit)
    if (finalsOnly) params.set('finals_only', 'true')
    return request(`/games?${params}`)
  },
  getOrgResults: (orgId, { seasonId, gradeId, finalsOnly } = {}) => {
    const params = new URLSearchParams({ org_id: orgId })
    if (seasonId) params.set('season_id', seasonId)
    if (gradeId) params.set('grade_id', gradeId)
    if (finalsOnly) params.set('finals_only', 'true')
    return request(`/organisations/${orgId}/results?${params}`)
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

  // Families
  listFamilies: (orgId) => request(`/families?org_id=${encodeURIComponent(orgId)}`),
  getFamily: (familyId, orgId) =>
    request(`/families/${familyId}?org_id=${encodeURIComponent(orgId)}`),
  createFamily: (orgId, name, notes) =>
    request('/families', {
      method: 'POST',
      body: JSON.stringify({ org_id: orgId, name, notes: notes || null }),
    }),
  updateFamily: (familyId, orgId, patch) =>
    request(`/families/${familyId}`, {
      method: 'PATCH',
      body: JSON.stringify({ org_id: orgId, ...patch }),
    }),
  deleteFamily: (familyId, orgId) =>
    request(`/families/${familyId}?org_id=${encodeURIComponent(orgId)}`, { method: 'DELETE' }),
  addFamilyMember: (familyId, orgId, playerId, relationship) =>
    request(`/families/${familyId}/members`, {
      method: 'POST',
      body: JSON.stringify({ org_id: orgId, player_id: playerId, relationship: relationship || null }),
    }),
  updateFamilyMember: (familyId, playerId, orgId, relationship) =>
    request(`/families/${familyId}/members/${playerId}`, {
      method: 'PATCH',
      body: JSON.stringify({ org_id: orgId, relationship: relationship || null }),
    }),
  removeFamilyMember: (familyId, playerId, orgId) =>
    request(`/families/${familyId}/members/${playerId}?org_id=${encodeURIComponent(orgId)}`, {
      method: 'DELETE',
    }),
  getFamilySuggestions: (orgId) =>
    request(`/families/suggestions/list?org_id=${encodeURIComponent(orgId)}`),
  dismissFamilySuggestion: (orgId, surnameKey) =>
    request('/families/suggestions/dismiss', {
      method: 'POST',
      body: JSON.stringify({ org_id: orgId, surname_key: surnameKey }),
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

  // Club admin — fees (Phase 1)
  feeListSchedule: (seasonId) => request(`/club-admin/fees/schedule?season_id=${seasonId}`),
  feeCreateSchedule: (data) =>
    request('/club-admin/fees/schedule', { method: 'POST', body: JSON.stringify(data) }),
  feeUpdateSchedule: (id, data) =>
    request(`/club-admin/fees/schedule/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  feeDeleteSchedule: (id) =>
    request(`/club-admin/fees/schedule/${id}`, { method: 'DELETE' }),
  feeSeedDefaults: (seasonId) =>
    request(`/club-admin/fees/schedule/seed-defaults?season_id=${seasonId}`, { method: 'POST' }),
  feeCopySchedule: (seasonId, fromSeasonId) =>
    request('/club-admin/fees/schedule/copy-from', {
      method: 'POST',
      body: JSON.stringify({ season_id: seasonId, from_season_id: fromSeasonId }),
    }),
  feeListGrades: (seasonId) => request(`/club-admin/fees/grades?season_id=${seasonId}`),
  feeSetGradeFormat: (gradeId, feeFormat) =>
    request(`/club-admin/fees/grades/${gradeId}`, {
      method: 'PATCH',
      body: JSON.stringify({ fee_format: feeFormat }),
    }),
  feeListMembers: (seasonId) => request(`/club-admin/fees/members?season_id=${seasonId}`),
  feeCreateMember: (data) =>
    request('/club-admin/fees/members', { method: 'POST', body: JSON.stringify(data) }),
  feeGetMember: (memberId, seasonId) =>
    request(`/club-admin/fees/members/${memberId}?season_id=${seasonId}`),
  feePatchMember: (memberId, data) =>
    request(`/club-admin/fees/members/${memberId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  feePatchMemberSeason: (memberId, data) =>
    request(`/club-admin/fees/members/${memberId}/season`, { method: 'PATCH', body: JSON.stringify(data) }),
  feePatchMatchDay: (entryId, data) =>
    request(`/club-admin/fees/match-days/${entryId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  feeRecompute: (seasonId) =>
    request(`/club-admin/fees/recompute?season_id=${seasonId}`, { method: 'POST' }),
  // Payments
  feeListPayments: ({ seasonId, memberSeasonId, kind } = {}) => {
    const p = new URLSearchParams()
    if (seasonId) p.set('season_id', seasonId)
    if (memberSeasonId) p.set('member_season_id', memberSeasonId)
    if (kind) p.set('kind', kind)
    return request(`/club-admin/fees/payments?${p}`)
  },
  feeCreatePayment: (data) =>
    request('/club-admin/fees/payments', { method: 'POST', body: JSON.stringify(data) }),
  feeUpdatePayment: (id, data) =>
    request(`/club-admin/fees/payments/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  feeDeletePayment: (id) =>
    request(`/club-admin/fees/payments/${id}`, { method: 'DELETE' }),
  // Reports
  feeReportSummary: (seasonId) =>
    request(`/club-admin/fees/reports/summary?season_id=${seasonId}`),
  feeReportNonFinancial: (seasonId) =>
    request(`/club-admin/fees/reports/non-financial?season_id=${seasonId}`),
  feeReportCashflow: (seasonId) =>
    request(`/club-admin/fees/reports/cashflow?season_id=${seasonId}`),
  feeReportExportUrl: (seasonId) =>
    `${BASE}/club-admin/fees/reports/export?season_id=${seasonId}`,
  // Phase 3 — rollover, bulk tier, CSV import
  feeRollover: (seasonId, fromSeasonId, includeLeftClub = false) =>
    request('/club-admin/fees/rollover', {
      method: 'POST',
      body: JSON.stringify({ season_id: seasonId, from_season_id: fromSeasonId, include_left_club: includeLeftClub }),
    }),
  feeBulkSetTier: (seasonId, memberIds, feeScheduleId) =>
    request('/club-admin/fees/members/bulk-tier', {
      method: 'POST',
      body: JSON.stringify({ season_id: seasonId, member_ids: memberIds, fee_schedule_id: feeScheduleId || null }),
    }),
  feeImportPreview: (seasonId, file, { defaultKind = 'membership', defaultMethod = 'EFT' } = {}) => {
    const form = new FormData()
    form.append('season_id', seasonId)
    form.append('file', file)
    form.append('default_kind', defaultKind)
    form.append('default_method', defaultMethod)
    return fetch(`${BASE}/club-admin/fees/payments/import/preview`, {
      method: 'POST', body: form, credentials: 'include',
    }).then(async res => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(typeof err.detail === 'string' ? err.detail : `HTTP ${res.status}`)
      }
      return res.json()
    })
  },
  feeImportCommit: (items) =>
    request('/club-admin/fees/payments/import/commit', {
      method: 'POST', body: JSON.stringify({ items }),
    }),
  // Phase 3.1 — Per-match-day Mark Paid + bulk payment
  feeMarkMatchDayPaid: (entryId, data = {}) =>
    request(`/club-admin/fees/match-days/${entryId}/mark-paid`, {
      method: 'POST', body: JSON.stringify(data),
    }),
  feeUnmarkMatchDayPaid: (entryId) =>
    request(`/club-admin/fees/match-days/${entryId}/mark-paid`, { method: 'DELETE' }),
  feeBulkPayment: (data) =>
    request('/club-admin/fees/payments/bulk', { method: 'POST', body: JSON.stringify(data) }),

  // Club admin — grades
  adminListGrades: () => request('/club-admin/grades'),
  adminRenameGrade: (originalName, displayNameOverride) =>
    request('/club-admin/grades/rename', {
      method: 'PATCH',
      body: JSON.stringify({ original_name: originalName, display_name_override: displayNameOverride }),
    }),

  // Club admin — players
  adminListPlayers: () => request('/club-admin/players'),
  adminCreatePlayer: (data) =>
    request('/club-admin/players', { method: 'POST', body: JSON.stringify(data) }),
  adminPatchPlayer: (playerId, data) =>
    request(`/club-admin/players/${playerId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  adminListSeasons: () => request('/club-admin/seasons'),
  adminReorderSeasons: (items) =>
    request('/club-admin/seasons/reorder', { method: 'PUT', body: JSON.stringify(items) }),
  // Season merges (aliases)
  adminListSeasonMerges: () => request('/club-admin/season-merges'),
  adminCreateSeasonMerge: (canonicalSeasonId, aliasSeasonId) =>
    request('/club-admin/season-merges', {
      method: 'POST',
      body: JSON.stringify({ canonical_season_id: canonicalSeasonId, alias_season_id: aliasSeasonId }),
    }),
  adminUndoSeasonMerge: (mergeId) =>
    request(`/club-admin/season-merges/${mergeId}/undo`, { method: 'POST' }),
  // Activity log (audit trail)
  adminListActivityLog: (limit = 100) =>
    request(`/club-admin/activity-log?limit=${limit}`),
  // Usage breadcrumbs (super-admin only)
  adminUsageRecent: ({ limit = 200, eventType = null, roles = [] } = {}) => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (eventType) params.set('event_type', eventType)
    ;(roles || []).forEach(r => params.append('role', r))
    return request(`/club-admin/usage/recent?${params}`)
  },
  adminUsageTopRoutes: ({ days = 7, limit = 30, eventType = null, roles = [] } = {}) => {
    const params = new URLSearchParams({ days: String(days), limit: String(limit) })
    if (eventType) params.set('event_type', eventType)
    ;(roles || []).forEach(r => params.append('role', r))
    return request(`/club-admin/usage/top-routes?${params}`)
  },
  adminUsageTopUsers: ({ days = 7, limit = 30, roles = [] } = {}) => {
    const params = new URLSearchParams({ days: String(days), limit: String(limit) })
    ;(roles || []).forEach(r => params.append('role', r))
    return request(`/club-admin/usage/top-users?${params}`)
  },
  adminUsageSummary: ({ days = 7, roles = [], eventType = null } = {}) => {
    const params = new URLSearchParams({ days: String(days) })
    ;(roles || []).forEach(r => params.append('role', r))
    if (eventType) params.set('event_type', eventType)
    return request(`/club-admin/usage/summary?${params}`)
  },
  adminUsageTimeseries: ({ days = 7, roles = [], eventType = null } = {}) => {
    const params = new URLSearchParams({ days: String(days) })
    ;(roles || []).forEach(r => params.append('role', r))
    if (eventType) params.set('event_type', eventType)
    return request(`/club-admin/usage/timeseries?${params}`)
  },
  adminUsageByFeature: ({ days = 7, roles = [], eventType = null } = {}) => {
    const params = new URLSearchParams({ days: String(days) })
    ;(roles || []).forEach(r => params.append('role', r))
    if (eventType) params.set('event_type', eventType)
    return request(`/club-admin/usage/by-feature?${params}`)
  },
  adminUsageByRole: ({ days = 7, eventType = null } = {}) => {
    const params = new URLSearchParams({ days: String(days) })
    if (eventType) params.set('event_type', eventType)
    return request(`/club-admin/usage/by-role?${params}`)
  },
  adminUsageByLocation: ({ days = 7, roles = [], eventType = null } = {}) => {
    const params = new URLSearchParams({ days: String(days) })
    ;(roles || []).forEach(r => params.append('role', r))
    if (eventType) params.set('event_type', eventType)
    return request(`/club-admin/usage/by-location?${params}`)
  },
  // Notification centre (bell icon)
  getNotificationsCount: () => request('/club-admin/notifications/count'),
  getNotificationsSummary: () => request('/club-admin/notifications/summary'),
  markNotificationsSeen: (appVersion) =>
    request('/club-admin/notifications/seen', {
      method: 'POST',
      body: JSON.stringify({ app_version: appVersion || null }),
    }),
  // Club user management
  adminListClubUsers: () => request('/club-admin/users'),
  adminListCapabilities: () => request('/club-admin/users/capabilities'),
  adminCreateClubUser: (data) =>
    request('/club-admin/users', { method: 'POST', body: JSON.stringify(data) }),
  adminUpdateClubUser: (userId, data) =>
    request(`/club-admin/users/${userId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  adminDeleteClubUser: (userId) =>
    request(`/club-admin/users/${userId}`, { method: 'DELETE' }),
  adminListGames: (seasonId) => {
    const params = new URLSearchParams()
    if (seasonId) params.set('season_id', seasonId)
    return request(`/club-admin/games?${params}`)
  },
  adminGetSettings: () => request('/club-admin/settings'),
  adminPatchSettings: (data) =>
    request('/club-admin/settings', { method: 'PATCH', body: JSON.stringify(data) }),
  adminUploadLogo: (file) => {
    const form = new FormData()
    form.append('file', file)
    return fetch(`${BASE}/club-admin/logo`, { method: 'POST', body: form, credentials: 'include' })
      .then(async r => {
        if (!r.ok) {
          const e = await r.json().catch(() => ({}))
          throw new Error(typeof e.detail === 'string' ? e.detail : `HTTP ${r.status}`)
        }
        return r.json()
      })
  },
  adminDeleteLogo: () => request('/club-admin/logo', { method: 'DELETE' }),
  adminUploadPlayerPhoto: (playerId, file) => {
    const form = new FormData()
    form.append('file', file)
    return fetch(`${BASE}/club-admin/players/${playerId}/photo`, { method: 'POST', body: form, credentials: 'include' })
      .then(async r => {
        if (!r.ok) {
          const e = await r.json().catch(() => ({}))
          throw new Error(typeof e.detail === 'string' ? e.detail : `HTTP ${r.status}`)
        }
        return r.json()
      })
  },
  adminDeletePlayerPhoto: (playerId) => request(`/club-admin/players/${playerId}/photo`, { method: 'DELETE' }),
  adminListPartnershipRecords: () => request('/club-admin/partnership-records'),
  adminCreatePartnershipRecord: (data) =>
    request('/club-admin/partnership-records', { method: 'POST', body: JSON.stringify(data) }),
  adminDeletePartnershipRecord: (id) =>
    request(`/club-admin/partnership-records/${id}`, { method: 'DELETE' }),
  adminPatchPartnershipRecord: (id, data) =>
    request(`/club-admin/partnership-records/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
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
  adminBackfillAggregates: () =>
    request('/club-admin/backfill-aggregates', { method: 'POST' }),
  adminCleanupOppositionStats: () =>
    request('/club-admin/cleanup-opposition-stats', { method: 'POST' }),
  adminListSyncRuns: (limit = 30) =>
    request(`/club-admin/sync-runs?limit=${limit}`),
  adminGetSyncRun: (runId) => request(`/club-admin/sync-runs/${runId}`),
  adminClearSyncRuns: () =>
    request('/club-admin/sync-runs', { method: 'DELETE' }),
  adminClearResolvedSyncRequests: () =>
    request('/club-admin/sync-requests/resolved', { method: 'DELETE' }),
  adminGetMilestones: () => request('/club-admin/milestones'),

  // Manual stat entries — historical backfill (v1.0.0.0 Beta)
  adminListSeasonAdjustments: () => request('/club-admin/manual-entries/season-adjustments'),
  adminCreateSeasonAdjustment: (data) =>
    request('/club-admin/manual-entries/season-adjustments', { method: 'POST', body: JSON.stringify(data) }),
  adminPatchSeasonAdjustment: (id, data) =>
    request(`/club-admin/manual-entries/season-adjustments/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  adminDeleteSeasonAdjustment: (id) =>
    request(`/club-admin/manual-entries/season-adjustments/${id}`, { method: 'DELETE' }),

  adminListCareerAdjustments: () => request('/club-admin/manual-entries/career-adjustments'),
  adminCreateCareerAdjustment: (data) =>
    request('/club-admin/manual-entries/career-adjustments', { method: 'POST', body: JSON.stringify(data) }),
  adminPatchCareerAdjustment: (id, data) =>
    request(`/club-admin/manual-entries/career-adjustments/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  adminDeleteCareerAdjustment: (id) =>
    request(`/club-admin/manual-entries/career-adjustments/${id}`, { method: 'DELETE' }),

  adminListManualGames: () => request('/club-admin/manual-entries/games'),
  adminGetManualGame: (id) => request(`/club-admin/manual-entries/games/${id}`),
  adminCreateManualGame: (data) =>
    request('/club-admin/manual-entries/games', { method: 'POST', body: JSON.stringify(data) }),
  adminPatchManualGame: (id, data) =>
    request(`/club-admin/manual-entries/games/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  adminDeleteManualGame: (id) =>
    request(`/club-admin/manual-entries/games/${id}`, { method: 'DELETE' }),

  adminListManualEntryAudit: (limit = 200) =>
    request(`/club-admin/manual-entries/audit?limit=${limit}`),
  adminUndoManualEntry: (logId) =>
    request(`/club-admin/manual-entries/audit/${logId}/undo`, { method: 'POST' }),
  adminListGradesBySeason: () => request('/club-admin/manual-entries/grades'),
  adminListManualEntryKnownValues: () => request('/club-admin/manual-entries/known-values'),

  adminDownloadSeasonAdjustmentTemplate: () =>
    fetch(`${BASE}/club-admin/manual-entries/season-adjustments/template.csv`, { credentials: 'include' }),
  adminImportSeasonAdjustments: (file) => {
    const form = new FormData()
    form.append('file', file)
    return fetch(`${BASE}/club-admin/manual-entries/season-adjustments/import`, {
      method: 'POST', body: form, credentials: 'include',
    }).then(async r => {
      const text = await r.text()
      try { return JSON.parse(text) }
      catch { throw new Error(`Server error (${r.status}): ${text.slice(0, 160)}`) }
    })
  },
  adminDownloadManualGamesTemplate: () =>
    fetch(`${BASE}/club-admin/manual-entries/games/template.csv`, { credentials: 'include' }),
  adminImportManualGames: (file) => {
    const form = new FormData()
    form.append('file', file)
    return fetch(`${BASE}/club-admin/manual-entries/games/import`, {
      method: 'POST', body: form, credentials: 'include',
    }).then(async r => {
      const text = await r.text()
      try { return JSON.parse(text) }
      catch { throw new Error(`Server error (${r.status}): ${text.slice(0, 160)}`) }
    })
  },

  // Super admin
  superListClubs: () => request('/club-admin/super/clubs'),
  superCreateClub: (data) =>
    request('/club-admin/super/clubs', { method: 'POST', body: JSON.stringify(data) }),
  superPatchClub: (clubId, data) =>
    request(`/club-admin/super/clubs/${clubId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  superDeleteClub: (clubId) =>
    request(`/club-admin/super/clubs/${clubId}`, { method: 'DELETE' }),
  superListUsers: () => request('/club-admin/super/users'),
  superCreateUser: (data) =>
    request('/club-admin/super/users', { method: 'POST', body: JSON.stringify(data) }),
  superUpdateUser: (userId, data) =>
    request(`/club-admin/super/users/${userId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  superDeleteUser: (userId) =>
    request(`/club-admin/super/users/${userId}`, { method: 'DELETE' }),
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
  forceImportAchievements: (orgId, rows) =>
    request(`/achievements/import/force?org_id=${orgId}`, {
      method: 'POST',
      body: JSON.stringify({ rows }),
    }),

  // Yearbooks
  listYearbooks: (orgId) => request(`/yearbooks/${orgId}`),
  getYearbook: (orgId, seasonId) => request(`/yearbooks/${orgId}/${seasonId}`),
  publishYearbook: (orgId, seasonId) => request(`/yearbooks/${orgId}/${seasonId}/publish`, { method: 'POST' }),
  unpublishYearbook: (orgId, seasonId) => request(`/yearbooks/${orgId}/${seasonId}/unpublish`, { method: 'POST' }),
  generateYearbookStubs: (orgId) => request(`/yearbooks/${orgId}/generate-stubs`, { method: 'POST' }),
  generateYearbookNarrative: (orgId, seasonId) =>
    request(`/yearbooks/${orgId}/${seasonId}/generate-narrative`, { method: 'POST' }),
  getYearbookOverview: (orgId, seasonId, gradeId) => {
    const params = new URLSearchParams()
    if (gradeId) params.set('grade_id', gradeId)
    return request(`/yearbooks/${orgId}/${seasonId}/stats/overview?${params}`)
  },
  getYearbookBatting: (orgId, seasonId, { gradeId, minInnings = 1, limit = 50 } = {}) => {
    const params = new URLSearchParams({ min_innings: minInnings, limit })
    if (gradeId) params.set('grade_id', gradeId)
    return request(`/yearbooks/${orgId}/${seasonId}/stats/batting?${params}`)
  },
  getYearbookBowling: (orgId, seasonId, { gradeId, minWickets = 1, limit = 50 } = {}) => {
    const params = new URLSearchParams({ min_wickets: minWickets, limit })
    if (gradeId) params.set('grade_id', gradeId)
    return request(`/yearbooks/${orgId}/${seasonId}/stats/bowling?${params}`)
  },
  getYearbookFielding: (orgId, seasonId, { gradeId, limit = 50 } = {}) => {
    const params = new URLSearchParams({ limit })
    if (gradeId) params.set('grade_id', gradeId)
    return request(`/yearbooks/${orgId}/${seasonId}/stats/fielding?${params}`)
  },
  getYearbookAllrounders: (orgId, seasonId, { gradeId, minRuns = 100, minWickets = 5 } = {}) => {
    const params = new URLSearchParams({ min_runs: minRuns, min_wickets: minWickets })
    if (gradeId) params.set('grade_id', gradeId)
    return request(`/yearbooks/${orgId}/${seasonId}/stats/allrounders?${params}`)
  },
  getYearbookSuperlatives: (orgId, seasonId, gradeId) => {
    const params = new URLSearchParams()
    if (gradeId) params.set('grade_id', gradeId)
    return request(`/yearbooks/${orgId}/${seasonId}/stats/superlatives?${params}`)
  },
  getYearbookResults: (orgId, seasonId, gradeId) => {
    const params = new URLSearchParams()
    if (gradeId) params.set('grade_id', gradeId)
    return request(`/yearbooks/${orgId}/${seasonId}/stats/results?${params}`)
  },
  getYearbookPartnerships: (orgId, seasonId, gradeId) => {
    const params = new URLSearchParams()
    if (gradeId) params.set('grade_id', gradeId)
    return request(`/yearbooks/${orgId}/${seasonId}/stats/partnerships?${params}`)
  },
  getYearbookMilestones: (orgId, seasonId) =>
    request(`/yearbooks/${orgId}/${seasonId}/stats/milestones`),
  getYearbookGrades: (orgId, seasonId) =>
    request(`/yearbooks/${orgId}/${seasonId}/stats/grades`),
  getYearbookDismissals: (orgId, seasonId, gradeId) => {
    const params = new URLSearchParams()
    if (gradeId) params.set('grade_id', gradeId)
    return request(`/yearbooks/${orgId}/${seasonId}/stats/dismissals?${params}`)
  },
  getYearbookPlayers: (orgId, seasonId, gradeId) => {
    const params = new URLSearchParams()
    if (gradeId) params.set('grade_id', gradeId)
    return request(`/yearbooks/${orgId}/${seasonId}/stats/players?${params}`)
  },
  createYearbookSection: (orgId, seasonId, data) =>
    request(`/yearbooks/${orgId}/${seasonId}/sections`, { method: 'POST', body: JSON.stringify(data) }),
  updateYearbookSection: (orgId, seasonId, sectionId, data) =>
    request(`/yearbooks/${orgId}/${seasonId}/sections/${sectionId}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteYearbookSection: (orgId, seasonId, sectionId) =>
    request(`/yearbooks/${orgId}/${seasonId}/sections/${sectionId}`, { method: 'DELETE' }),
  addHonourBoardEntry: (orgId, seasonId, data) =>
    request(`/yearbooks/${orgId}/${seasonId}/honour-board`, { method: 'POST', body: JSON.stringify(data) }),
  deleteHonourBoardEntry: (orgId, seasonId, entryId) =>
    request(`/yearbooks/${orgId}/${seasonId}/honour-board/${entryId}`, { method: 'DELETE' }),
  uploadYearbookHero: (orgId, seasonId, formData) =>
    fetch(`/api/yearbooks/${orgId}/${seasonId}/upload/hero`, { method: 'POST', body: formData, credentials: 'include' })
      .then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(new Error(e.detail || 'Upload failed')))),
  clearYearbookHero: (orgId, seasonId) =>
    request(`/yearbooks/${orgId}/${seasonId}/upload/hero`, { method: 'DELETE' }),
  uploadYearbookGallery: (orgId, seasonId, formData) =>
    fetch(`/api/yearbooks/${orgId}/${seasonId}/upload/gallery`, { method: 'POST', body: formData, credentials: 'include' })
      .then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(new Error(e.detail || 'Upload failed')))),
  deleteYearbookImage: (orgId, seasonId, imageId) =>
    request(`/yearbooks/${orgId}/${seasonId}/images/${imageId}`, { method: 'DELETE' }),
  createYearbookAward: (orgId, seasonId, data) =>
    request(`/yearbooks/${orgId}/${seasonId}/awards`, { method: 'POST', body: JSON.stringify(data) }),
  deleteYearbookAward: (orgId, seasonId, awardId) =>
    request(`/yearbooks/${orgId}/${seasonId}/awards/${awardId}`, { method: 'DELETE' }),
  addFeaturedAchievement: (orgId, seasonId, achievementId) =>
    request(`/yearbooks/${orgId}/${seasonId}/featured-achievements`, { method: 'POST', body: JSON.stringify({ achievement_id: parseInt(achievementId, 10) }) }),
  removeFeaturedAchievement: (orgId, seasonId, achievementId) =>
    request(`/yearbooks/${orgId}/${seasonId}/featured-achievements/${parseInt(achievementId, 10)}`, { method: 'DELETE' }),

  // Award Definitions
  listAwardDefinitions: (orgId) =>
    request(`/award-definitions?org_id=${orgId}`),
  createAwardDefinition: (data) =>
    request('/award-definitions', { method: 'POST', body: JSON.stringify(data) }),
  updateAwardDefinition: (id, data) =>
    request(`/award-definitions/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteAwardDefinition: (id) =>
    request(`/award-definitions/${id}`, { method: 'DELETE' }),
  seedAwardDefinitions: (orgId, template = 'global') =>
    request(`/award-definitions/seed?org_id=${orgId}&template=${template}`, { method: 'POST' }),

  // StatLab — schema (targets, metrics, context filters, derived queries)
  statlabSchema: () => request('/statlab/schema'),

  // StatLab — main query. Pass `filterTree` for nested AND/OR; the legacy
  // `filters` flat list is preserved for backward compatibility.
  statlabQuery: (orgId, {
    target = 'player_career',
    sortBy = 'runs',
    sortDir = 'desc',
    limit = 100,
    page = 1,
    filters = [],
    filterTree = null,
    context = {},
  } = {}) => {
    const params = new URLSearchParams({ org_id: orgId, target, sort_by: sortBy, sort_dir: sortDir, limit, page })
    if (filterTree) {
      params.set('filter_tree', JSON.stringify(filterTree))
    } else {
      filters.forEach(f => params.append('filters', f))
    }
    _appendContext(params, context)
    return request(`/statlab/query?${params}`)
  },

  // StatLab — derived (streak-style) queries
  statlabDerived: (orgId, name, { limit = 100, page = 1, context = {} } = {}) => {
    const params = new URLSearchParams({ org_id: orgId, limit, page })
    _appendContext(params, context)
    return request(`/statlab/derived/${name}?${params}`)
  },

  // StatLab — distinct values for attribute pickers (gender, role, awards, etc.)
  statlabPickerValues: (orgId, kind, search = '') => {
    const params = new URLSearchParams({ org_id: orgId, kind })
    if (search) params.set('search', search)
    return request(`/statlab/picker-values?${params}`)
  },

  // StatLab — saved reports
  statlabListReports: (orgId) => request(`/statlab/reports?org_id=${orgId}`),
  statlabGetReport: (slug, orgId) => request(`/statlab/reports/${slug}?org_id=${orgId}`),
  statlabCreateReport: (data) =>
    request('/statlab/reports', { method: 'POST', body: JSON.stringify(data) }),
  statlabPatchReport: (reportId, data) =>
    request(`/statlab/reports/${reportId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  statlabDeleteReport: (reportId) =>
    request(`/statlab/reports/${reportId}`, { method: 'DELETE' }),
  statlabListPendingReports: () => request('/statlab/reports/pending'),
  statlabReviewReport: (reportId, data) =>
    request(`/statlab/reports/${reportId}/review`, { method: 'POST', body: JSON.stringify(data) }),

  // Sponsors (public)
  getClubSponsors: (slug) => request(`/clubs/${slug}/sponsors`),

  // Sponsors (admin)
  adminListSponsors: () => request('/club-admin/sponsors'),
  adminCreateSponsor: (data) =>
    request('/club-admin/sponsors', { method: 'POST', body: JSON.stringify(data) }),
  adminPatchSponsor: (id, data) =>
    request(`/club-admin/sponsors/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  adminUploadSponsorLogo: (id, file) => {
    const form = new FormData()
    form.append('file', file)
    return fetch(`${BASE}/club-admin/sponsors/${id}/logo`, { method: 'POST', body: form, credentials: 'include' })
      .then(async r => {
        if (!r.ok) {
          const e = await r.json().catch(() => ({}))
          throw new Error(typeof e.detail === 'string' ? e.detail : `HTTP ${r.status}`)
        }
        return r.json()
      })
  },
  adminDeleteSponsorLogo: (id) =>
    request(`/club-admin/sponsors/${id}/logo`, { method: 'DELETE' }),
  adminDeleteSponsor: (id) =>
    request(`/club-admin/sponsors/${id}`, { method: 'DELETE' }),
  adminReorderSponsors: (items) =>
    request('/club-admin/sponsors/reorder', { method: 'PUT', body: JSON.stringify(items) }),

  // Records
  getRecords: (orgId, { seasonId, gradeId, gradeName, finalsOnly, captainOnly, gender } = {}) => {
    const params = new URLSearchParams()
    if (seasonId) params.set('season_id', seasonId)
    if (gradeId) params.set('grade_id', gradeId)
    if (gradeName) params.set('grade_name', gradeName)
    if (finalsOnly) params.set('finals_only', 'true')
    if (captainOnly) params.set('captain_only', 'true')
    if (gender) params.set('gender', gender)
    return request(`/records/${orgId}?${params}`)
  },
  getRecordsGrades: (orgId, seasonId) => {
    const params = new URLSearchParams()
    if (seasonId) params.set('season_id', seasonId)
    return request(`/records/${orgId}/grades?${params}`)
  },

  // Leaderboard
  battingLeaderboard: (orgId, { seasonId, gradeId, gradeName, sortBy, limit, minRuns, finalsOnly, captainOnly, gender, overseas } = {}) => {
    const params = new URLSearchParams({ org_id: orgId })
    if (seasonId) params.set('season_id', seasonId)
    if (gradeId) params.set('grade_id', gradeId)
    if (gradeName) params.set('grade_name', gradeName)
    if (sortBy) params.set('sort_by', sortBy)
    if (limit) params.set('limit', limit)
    if (minRuns != null) params.set('min_runs', minRuns)
    if (finalsOnly) params.set('finals_only', 'true')
    if (captainOnly) params.set('captain_only', 'true')
    if (gender) params.set('gender', gender)
    if (overseas) params.set('overseas', overseas)
    return request(`/leaderboard/batting?${params}`)
  },
  bowlingLeaderboard: (orgId, { seasonId, gradeId, gradeName, sortBy, limit, minOvers, minWickets, finalsOnly, captainOnly, gender, overseas } = {}) => {
    const params = new URLSearchParams({ org_id: orgId })
    if (seasonId) params.set('season_id', seasonId)
    if (gradeId) params.set('grade_id', gradeId)
    if (gradeName) params.set('grade_name', gradeName)
    if (sortBy) params.set('sort_by', sortBy)
    if (limit) params.set('limit', limit)
    if (minOvers != null) params.set('min_overs', minOvers)
    if (minWickets != null) params.set('min_wickets', minWickets)
    if (finalsOnly) params.set('finals_only', 'true')
    if (captainOnly) params.set('captain_only', 'true')
    if (gender) params.set('gender', gender)
    if (overseas) params.set('overseas', overseas)
    return request(`/leaderboard/bowling?${params}`)
  },
  fieldingLeaderboard: (orgId, { seasonId, gradeId, gradeName, sortBy, limit, finalsOnly, captainOnly, gender, overseas } = {}) => {
    const params = new URLSearchParams({ org_id: orgId })
    if (seasonId) params.set('season_id', seasonId)
    if (gradeId) params.set('grade_id', gradeId)
    if (gradeName) params.set('grade_name', gradeName)
    if (sortBy) params.set('sort_by', sortBy)
    if (limit) params.set('limit', limit)
    if (finalsOnly) params.set('finals_only', 'true')
    if (captainOnly) params.set('captain_only', 'true')
    if (gender) params.set('gender', gender)
    if (overseas) params.set('overseas', overseas)
    return request(`/leaderboard/fielding?${params}`)
  },
  sirsLeaderboard: (orgId, type, { seasonId, gradeName, finalsOnly, captainOnly, limit, gender, overseas } = {}) => {
    const params = new URLSearchParams({ org_id: orgId })
    if (seasonId) params.set('season_id', seasonId)
    if (gradeName) params.set('grade_name', gradeName)
    if (finalsOnly) params.set('finals_only', 'true')
    if (captainOnly) params.set('captain_only', 'true')
    if (limit) params.set('limit', limit)
    if (gender) params.set('gender', gender)
    if (overseas) params.set('overseas', overseas)
    return request(`/leaderboard/sirs/${type}?${params}`)
  },
  getPlayerCaptainStats: (playerId) => request(`/players/${playerId}/captain-stats`),

  // ─── BetterSelect: Fixtures ─────────────────────────────
  bsListFixtures: (upcomingOnly = false) =>
    request(`/fixtures${upcomingOnly ? '?upcoming_only=true' : ''}`),
  bsCreateFixture: (data) =>
    request('/fixtures', { method: 'POST', body: JSON.stringify(data) }),
  bsUpdateFixture: (id, data) =>
    request(`/fixtures/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  bsDeleteFixture: (id) => request(`/fixtures/${id}`, { method: 'DELETE' }),
  bsSyncFixtures: () => request('/fixtures/sync', { method: 'POST' }),

  // ─── BetterSelect: Teams ────────────────────────────────
  bsListTeams: (includeInactive = false) =>
    request(`/teams${includeInactive ? '?include_inactive=true' : ''}`),
  bsCreateTeam: (data) =>
    request('/teams', { method: 'POST', body: JSON.stringify(data) }),
  bsUpdateTeam: (id, data) =>
    request(`/teams/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  bsDeleteTeam: (id) => request(`/teams/${id}`, { method: 'DELETE' }),
  bsSeedTeams: () => request('/teams/seed', { method: 'POST' }),
  bsTeamMembers: (id) => request(`/teams/${id}/members`),
  bsAddTeamMember: (id, playerId) =>
    request(`/teams/${id}/members`, { method: 'POST', body: JSON.stringify({ player_id: playerId }) }),
  bsRemoveTeamMember: (id, playerId) =>
    request(`/teams/${id}/members/${playerId}`, { method: 'DELETE' }),

  // ─── BetterSelect: Availability ─────────────────────────
  bsAvailabilityMatrix: () => request('/availability/matrix'),
  bsSetAvailability: (data) =>
    request('/availability', { method: 'POST', body: JSON.stringify(data) }),
  bsBulkAvailability: (items) =>
    request('/availability/bulk', { method: 'POST', body: JSON.stringify({ items }) }),

  // ─── BetterSelect: Selection (lineups) ──────────────────
  bsGetSelection: (fixtureId) => request(`/selection/${fixtureId}`),
  bsSetSelection: (fixtureId, players) =>
    request(`/selection/${fixtureId}`, { method: 'PUT', body: JSON.stringify({ players }) }),

  // ─── BetterSelect: Player profile ───────────────────────
  bsGetPlayerProfile: (id) => request(`/players/${id}/profile`),
  bsUpdatePlayerProfile: (id, data) =>
    request(`/players/${id}/profile`, { method: 'PATCH', body: JSON.stringify(data) }),
}
