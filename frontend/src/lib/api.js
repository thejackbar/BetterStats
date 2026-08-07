// BASE_URL is Vite's build base ('/' for cricket; '/afl/' for a silo built to
// live under a path prefix — see docs/afl-betterstats-plan.md's domain
// topology). '/' + 'api' keeps cricket byte-identical at '/api'.
const BASE = import.meta.env.VITE_API_URL || (import.meta.env.BASE_URL + 'api')

// Shown while the backend is briefly unavailable (e.g. during a deploy, when
// nginx can't reach the backend and would otherwise surface a raw
// "Bad Gateway"/"Service Unavailable"). Keep this friendly and reassuring.
const BACKEND_DOWN_MESSAGE = 'System refreshing. Please wait a moment…'

// A gateway/unavailable status means the backend is down, not a real app error.
// Its statusText ("Bad Gateway" etc.) should never reach the user.
function statusMessage(res) {
  if (res.status === 502 || res.status === 503 || res.status === 504) {
    return BACKEND_DOWN_MESSAGE
  }
  return res.statusText
}

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...options.headers }
  const res = await fetch(`${BASE}${path}`, { ...options, headers, credentials: 'include' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: statusMessage(res) }))
    let detail
    if (Array.isArray(err.detail)) {
      detail = err.detail.map(e => e.msg || JSON.stringify(e)).join(', ')
    } else if (typeof err.detail === 'string') {
      detail = err.detail
    } else if (err.detail && typeof err.detail === 'object') {
      // Structured errors: a validation list (e.g. squad build) or the
      // require_module 402 upsell payload.
      detail = Array.isArray(err.detail.errors)
        ? err.detail.errors.join(' ')
        : err.detail.message || err.detail.detail || `HTTP ${res.status}`
    } else {
      detail = `HTTP ${res.status}`
    }
    const error = new Error(detail)
    error.status = res.status
    if (err.detail && typeof err.detail === 'object' && !Array.isArray(err.detail)) {
      error.detail = err.detail
    }
    throw error
  }
  // 204 No Content (DELETE endpoints) and any empty 2xx body have nothing to
  // parse, so return null instead of letting res.json() throw "Unexpected end
  // of JSON input".
  if (res.status === 204) return null
  const text = await res.text()
  return text ? JSON.parse(text) : null
}

// Build a query string for the marketing directory filters. Skips empty / null /
// false, and appends array values as repeated params (e.g. ?associations=A&associations=B)
// so FastAPI List[str] params parse correctly.
function mktQS(params) {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params || {})) {
    if (v === '' || v == null || v === false) continue
    if (Array.isArray(v)) v.forEach(i => { if (i != null && i !== '') qs.append(k, i) })
    else qs.append(k, v)
  }
  return qs.toString()
}

// POST a single file as multipart/form-data and return the parsed JSON.
// Used by the image-upload endpoints (logos, hero, news covers, gallery, etc.).
async function uploadFile(path, file, field = 'file') {
  const form = new FormData()
  form.append(field, file)
  const res = await fetch(`${BASE}${path}`, { method: 'POST', body: form, credentials: 'include' })
  if (!res.ok) {
    const e = await res.json().catch(() => ({}))
    throw new Error(typeof e.detail === 'string' ? e.detail : `HTTP ${res.status}`)
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
  unlockClub: (slug, pin) => request(`/clubs/${slug}/unlock`, {
    method: 'POST', body: JSON.stringify({ pin }),
  }),
  requestClubUnpause: (slug, email, message) => request(`/clubs/${slug}/request-unpause`, {
    method: 'POST', body: JSON.stringify({ email, message }),
  }),
  superListUnpauseRequests: (status) => request(`/club-admin/super/unpause-requests${status ? `?status=${status}` : ''}`),
  superActionUnpauseRequest: (id, status) => request(`/club-admin/super/unpause-requests/${id}`, {
    method: 'PATCH', body: JSON.stringify({ status }),
  }),

  // Organisations (UUID-based, used internally once slug is resolved)
  searchOrgs: (q) => request(`/organisations/search?q=${encodeURIComponent(q)}`),
  getSocialScorecard: (matchId) => request(`/admin/social/scorecard/${matchId}`),
  socialMatchLookup: (q) => request(`/admin/social/match-lookup?q=${encodeURIComponent(q)}`),
  getSocialFixtures: () => request('/admin/social/fixtures'),
  getSocialResults: () => request('/admin/social/results'),

  // BetterSocials — media library
  listSocialMedia: () => request('/admin/social/media'),
  uploadSocialMedia: (file) => {
    const form = new FormData()
    form.append('file', file)
    return fetch(`${BASE}/admin/social/media`, { method: 'POST', body: form, credentials: 'include' })
      .then(async r => {
        if (!r.ok) {
          const e = await r.json().catch(() => ({}))
          throw new Error(typeof e.detail === 'string' ? e.detail : `HTTP ${r.status}`)
        }
        return r.json()
      })
  },
  deleteSocialMedia: (id) => request(`/admin/social/media/${id}`, { method: 'DELETE' }),
  // BetterSocials — brand kit
  getSocialBrandKit: () => request('/admin/social/brand-kit'),
  saveSocialBrandKit: (kit) =>
    request('/admin/social/brand-kit', { method: 'PUT', body: JSON.stringify(kit) }),
  onboard: (orgId, orgName = '') =>
    request('/organisations/onboard', { method: 'POST', body: JSON.stringify({ org_id: orgId, org_name: orgName }) }),
  listOrgs: () => request('/organisations'),
  getOrg: (orgId) => request(`/organisations/${orgId}`),
  getOrgSeasons: (orgId) => request(`/organisations/${orgId}/seasons`),
  orgGradeCategories: (orgId) => request(`/organisations/${orgId}/grade-categories`),
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
  // Published team lists (live from the CA feed). mode 'upcoming' | 'past'.
  getOrgLineups: (orgId, { mode, seasonId, gradeId, category, finalsOnly, offset, limit } = {}) => {
    const q = new URLSearchParams()
    if (mode) q.set('mode', mode)
    if (seasonId) q.set('season_id', seasonId)
    if (gradeId) q.set('grade_id', gradeId)
    if (category) q.set('category', category)
    if (finalsOnly) q.set('finals_only', 'true')
    if (offset) q.set('offset', offset)
    if (limit) q.set('limit', limit)
    const qs = q.toString()
    return request(`/organisations/${orgId}/lineups${qs ? `?${qs}` : ''}`)
  },
  // One match's lineup, for a direct link from a Fixtures-page row.
  getOrgLineup: (orgId, matchId) => request(`/organisations/${orgId}/lineups/${matchId}`),

  // Players
  listPlayers: (orgId) => request(`/players?org_id=${orgId}`),
  getPlayer: (playerId) => request(`/players/${playerId}`),
  getPlayerStats: (playerId, { seasonId, gradeId, lastNGames, startDate, endDate, categories } = {}) => {
    const params = new URLSearchParams()
    if (seasonId) params.set('season_id', seasonId)
    if (gradeId) params.set('grade_id', gradeId)
    if (lastNGames) params.set('last_n_games', lastNGames)
    if (startDate) params.set('start_date', startDate)
    if (endDate) params.set('end_date', endDate)
    if (categories) params.set('categories', categories)
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
  // Public teammates: who this player has shared a side with, and the with-vs-
  // without split of the player's output alongside one teammate.
  getPlayerTeammates: (playerId) => request(`/players/${playerId}/teammates`),
  getPlayerTeammateSplit: (playerId, teammateId) => request(`/players/${playerId}/teammates/${teammateId}`),
  getPlayerTeamBreakdown: (playerId, { seasonId } = {}) => {
    const params = new URLSearchParams()
    if (seasonId) params.set('season_id', seasonId)
    const qs = params.toString()
    return request(`/players/${playerId}/team-breakdown${qs ? `?${qs}` : ''}`)
  },
  getPlayerSeasons: (playerId, categories) =>
    request(`/players/${playerId}/seasons` + (categories ? `?categories=${encodeURIComponent(categories)}` : '')),
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
  // Family/Household — non-playing members (parents/guardians)
  addFamilyFeeMember: (familyId, orgId, feeMemberId, relationship, isGuardian) =>
    request(`/families/${familyId}/members/fee-member`, {
      method: 'POST',
      body: JSON.stringify({ org_id: orgId, fee_member_id: feeMemberId, relationship: relationship || null, is_guardian: !!isGuardian }),
    }),
  updateFamilyFeeMember: (familyId, feeMemberId, orgId, patch) =>
    request(`/families/${familyId}/members/fee-member/${feeMemberId}`, {
      method: 'PATCH',
      body: JSON.stringify({ org_id: orgId, ...patch }),
    }),
  removeFamilyFeeMember: (familyId, feeMemberId, orgId) =>
    request(`/families/${familyId}/members/fee-member/${feeMemberId}?org_id=${encodeURIComponent(orgId)}`, {
      method: 'DELETE',
    }),
  getFamilyFinancials: (familyId, orgId, seasonId) =>
    request(`/families/${familyId}/financials?org_id=${encodeURIComponent(orgId)}&season_id=${encodeURIComponent(seasonId)}`),

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

  // Grade category label + public visibility
  classifyGrade: (gradeName, { category, is_public } = {}) =>
    request('/admin/grades/classify', {
      method: 'PATCH',
      body: JSON.stringify({ grade_name: gradeName, category, is_public }),
    }),
  applyGradeSuggestions: () =>
    request('/admin/grades/apply-suggestions', { method: 'POST' }),

  // Committee Administration (core capability, not a paid module)
  committeeListPositions: (includeInactive) =>
    request(`/club-admin/committee/positions${includeInactive ? '?include_inactive=true' : ''}`),
  committeePositionsCurrent: () => request('/club-admin/committee/positions/current'),
  committeeCreatePosition: (data) =>
    request('/club-admin/committee/positions', { method: 'POST', body: JSON.stringify(data) }),
  committeeUpdatePosition: (id, data) =>
    request(`/club-admin/committee/positions/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  committeeArchivePosition: (id) =>
    request(`/club-admin/committee/positions/${id}`, { method: 'DELETE' }),
  committeeSeedStarterPositions: () =>
    request('/club-admin/committee/positions/seed-starter', { method: 'POST' }),
  committeeReorderPositions: (positionIds) =>
    request('/club-admin/committee/positions/reorder', { method: 'POST', body: JSON.stringify({ position_ids: positionIds }) }),
  committeePositionHistory: (id) => request(`/club-admin/committee/positions/${id}/history`),
  committeeStartTerm: (positionId, data) =>
    request(`/club-admin/committee/positions/${positionId}/terms`, { method: 'POST', body: JSON.stringify(data) }),
  committeeUpdateTerm: (termId, data) =>
    request(`/club-admin/committee/terms/${termId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  committeeEndTerm: (termId, data) =>
    request(`/club-admin/committee/terms/${termId}/end`, { method: 'POST', body: JSON.stringify(data) }),
  committeeListTasks: ({ status, category } = {}) => {
    const p = new URLSearchParams()
    if (status) p.set('status', status)
    if (category) p.set('category', category)
    const qs = p.toString()
    return request(`/club-admin/committee/tasks${qs ? `?${qs}` : ''}`)
  },
  committeeCreateTask: (data) =>
    request('/club-admin/committee/tasks', { method: 'POST', body: JSON.stringify(data) }),
  committeeUpdateTask: (id, data) =>
    request(`/club-admin/committee/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  committeeDeleteTask: (id) =>
    request(`/club-admin/committee/tasks/${id}`, { method: 'DELETE' }),
  // Governance (migration 217) — resolutions, named votes, action dependencies,
  // notes and the strategic objectives actions are measured against.
  committeeSetTaskDependencies: (taskId, dependsOn) =>
    request(`/club-admin/committee/tasks/${taskId}/dependencies`, { method: 'PUT', body: JSON.stringify({ depends_on: dependsOn }) }),
  committeeSetMotionVotes: (meetingId, motionId, votes) =>
    request(`/club-admin/committee/meetings/${meetingId}/motions/${motionId}/votes`, { method: 'PUT', body: JSON.stringify({ votes }) }),
  committeeSetResolution: (meetingId, motionId, { resolution_ref, on = true } = {}) =>
    request(`/club-admin/committee/meetings/${meetingId}/motions/${motionId}/resolution`, { method: 'POST', body: JSON.stringify({ resolution_ref, on }) }),
  committeeListResolutions: () => request('/club-admin/committee/resolutions'),
  committeeListNotes: (entityType, entityId) =>
    request(`/club-admin/committee/notes/${entityType}/${entityId}`),
  committeeAddNote: (entityType, entityId, body, authorMemberId) =>
    request(`/club-admin/committee/notes/${entityType}/${entityId}`, { method: 'POST', body: JSON.stringify({ body, author_member_id: authorMemberId || null }) }),
  committeeDeleteNote: (noteId) =>
    request(`/club-admin/committee/notes/${noteId}`, { method: 'DELETE' }),
  committeeListPlans: (includeArchived) =>
    request(`/club-admin/committee/plans${includeArchived ? '?include_archived=true' : ''}`),
  committeePlanReport: (includeArchived) =>
    request(`/club-admin/committee/plans/report${includeArchived ? '?include_archived=true' : ''}`),
  committeeCreatePlan: (data) =>
    request('/club-admin/committee/plans', { method: 'POST', body: JSON.stringify(data) }),
  committeeUpdatePlan: (id, data) =>
    request(`/club-admin/committee/plans/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  committeeDeletePlan: (id) =>
    request(`/club-admin/committee/plans/${id}`, { method: 'DELETE' }),
  committeeListObjectives: (includeArchived) =>
    request(`/club-admin/committee/objectives${includeArchived ? '?include_archived=true' : ''}`),
  committeeObjectiveProgress: () => request('/club-admin/committee/objectives/progress'),
  committeeCreateObjective: (data) =>
    request('/club-admin/committee/objectives', { method: 'POST', body: JSON.stringify(data) }),
  committeeUpdateObjective: (id, data) =>
    request(`/club-admin/committee/objectives/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  committeeDeleteObjective: (id) =>
    request(`/club-admin/committee/objectives/${id}`, { method: 'DELETE' }),
  committeeListDocuments: (category) =>
    request(`/club-admin/committee/documents${category ? `?category=${category}` : ''}`),
  committeeCreateDocument: (data) =>
    request('/club-admin/committee/documents', { method: 'POST', body: JSON.stringify(data) }),
  committeeUpdateDocument: (id, data) =>
    request(`/club-admin/committee/documents/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  committeeDeleteDocument: (id) =>
    request(`/club-admin/committee/documents/${id}`, { method: 'DELETE' }),
  // Uploads go through FormData, not JSON — the file is the payload.
  committeeUploadDocument: (file, fields = {}) => {
    const form = new FormData()
    form.append('file', file)
    Object.entries(fields).forEach(([k, v]) => { if (v) form.append(k, v) })
    return fetch(`${BASE}/club-admin/committee/documents/upload`, {
      method: 'POST', body: form, credentials: 'include',
    }).then(async res => {
      if (!res.ok) {
        const e = await res.json().catch(() => ({}))
        throw new Error(typeof e.detail === 'string' ? e.detail : `HTTP ${res.status}`)
      }
      return res.json()
    })
  },
  // The bytes come from here, access re-checked server-side on every request.
  // Returned as a URL rather than fetched, so the browser can open or save it.
  committeeDocumentFileUrl: (id, { download = false } = {}) =>
    `${BASE}/club-admin/committee/documents/${id}/file${download ? '?download=1' : ''}`,
  committeeOfficeBearerAwards: () =>
    request('/club-admin/committee/office-bearer-awards'),
  committeeAdoptOfficeBearerAwards: () =>
    request('/club-admin/committee/office-bearer-awards/adopt', { method: 'POST' }),
  committeeListEvents: (upcomingOnly) =>
    request(`/club-admin/committee/events${upcomingOnly ? '?upcoming_only=true' : ''}`),
  committeeCreateEvent: (data) =>
    request('/club-admin/committee/events', { method: 'POST', body: JSON.stringify(data) }),
  committeeUpdateEvent: (id, data) =>
    request(`/club-admin/committee/events/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  committeeDeleteEvent: (id) =>
    request(`/club-admin/committee/events/${id}`, { method: 'DELETE' }),

  // Volunteer Management (core capability, not a paid module)
  volunteerDirectory: () => request('/club-admin/volunteers/directory'),
  volunteerUpsertProfile: (data) =>
    request('/club-admin/volunteers/profiles', { method: 'POST', body: JSON.stringify(data) }),
  volunteerProfile: (memberId) => request(`/club-admin/volunteers/members/${memberId}/profile`),
  volunteerListHours: (memberId) => request(`/club-admin/volunteers/members/${memberId}/hours`),
  volunteerLogHours: (data) =>
    request('/club-admin/volunteers/hours', { method: 'POST', body: JSON.stringify(data) }),
  volunteerDeleteHours: (id) =>
    request(`/club-admin/volunteers/hours/${id}`, { method: 'DELETE' }),

  // BetterClubManager Directory (core capability, not a paid module)
  dirPeople: (includeArchived) => request(`/club-admin/directory/people${includeArchived ? '?include_archived=true' : ''}`),
  dirCreateMember: (data) => request('/club-admin/directory/people', { method: 'POST', body: JSON.stringify(data) }),
  dirUpdateMember: (id, data) => request(`/club-admin/directory/people/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  dirArchiveMember: (id) => request(`/club-admin/directory/people/${id}/archive`, { method: 'POST' }),
  dirRestoreMember: (id) => request(`/club-admin/directory/people/${id}/restore`, { method: 'POST' }),
  dirEnsureMemberForPlayer: (playerId) => request(`/club-admin/directory/players/${playerId}/ensure-member`, { method: 'POST' }),
  dirAddRole: (memberId, roleId) => request(`/club-admin/directory/people/${memberId}/roles`, { method: 'POST', body: JSON.stringify({ role_id: roleId }) }),
  dirRemoveRole: (memberId, roleId) => request(`/club-admin/directory/people/${memberId}/roles/${roleId}`, { method: 'DELETE' }),
  dirImportPreview: (csvText) => request('/club-admin/directory/import/preview', { method: 'POST', body: JSON.stringify({ csv: csvText }) }),
  dirImportCommit: (csvText) => request('/club-admin/directory/import/commit', { method: 'POST', body: JSON.stringify({ csv: csvText }) }),
  feeMembersImportPreview: (csvText) => request('/club-admin/fees/members/import/preview', { method: 'POST', body: JSON.stringify({ csv: csvText }) }),
  feeMembersImportCommit: (csvText, seasonId) => request('/club-admin/fees/members/import/commit', { method: 'POST', body: JSON.stringify({ csv: csvText, season_id: seasonId }) }),
  dirMemberOverlays: (memberId) => request(`/club-admin/directory/people/${memberId}/overlays`),
  dirCommitteePositions: () => request('/club-admin/directory/committee-positions'),
  dirFamilies: () => request('/club-admin/directory/families'),
  dirAssignCommittee: (memberId, positionId) => request(`/club-admin/directory/people/${memberId}/committee`, { method: 'POST', body: JSON.stringify({ position_id: positionId }) }),
  dirRemoveCommittee: (memberId, termId) => request(`/club-admin/directory/people/${memberId}/committee/${termId}`, { method: 'DELETE' }),
  dirCreateFamily: (name) => request('/club-admin/directory/families', { method: 'POST', body: JSON.stringify({ name }) }),
  dirAddToFamily: (memberId, familyId, data = {}) => request(`/club-admin/directory/people/${memberId}/families`, { method: 'POST', body: JSON.stringify({ family_id: familyId, ...data }) }),
  dirRemoveFromFamily: (memberId, familyId) => request(`/club-admin/directory/people/${memberId}/families/${familyId}`, { method: 'DELETE' }),

  // BetterClubManager Roster (core capability, not a paid module)
  rosterAreas: () => request('/club-admin/roster/areas'),
  rosterCreateArea: (data) => request('/club-admin/roster/areas', { method: 'POST', body: JSON.stringify(data) }),
  rosterUpdateArea: (id, data) => request(`/club-admin/roster/areas/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  rosterDeleteArea: (id) => request(`/club-admin/roster/areas/${id}`, { method: 'DELETE' }),
  rosterSeedStarter: () => request('/club-admin/roster/areas/seed-starter', { method: 'POST' }),
  rosterReorderAreas: (areaIds) => request('/club-admin/roster/areas/reorder', { method: 'POST', body: JSON.stringify({ area_ids: areaIds }) }),
  rosterDepartments: () => request('/club-admin/roster/departments'),
  rosterCreateDepartment: (data) => request('/club-admin/roster/departments', { method: 'POST', body: JSON.stringify(data) }),
  rosterUpdateDepartment: (id, data) => request(`/club-admin/roster/departments/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  rosterDeleteDepartment: (id) => request(`/club-admin/roster/departments/${id}`, { method: 'DELETE' }),
  rosterReorderDepartments: (deptIds) => request('/club-admin/roster/departments/reorder', { method: 'POST', body: JSON.stringify({ department_ids: deptIds }) }),
  rosterSeedDepartments: () => request('/club-admin/roster/departments/seed-starter', { method: 'POST' }),
  rosterAddPattern: (areaId, data) => request(`/club-admin/roster/areas/${areaId}/patterns`, { method: 'POST', body: JSON.stringify(data) }),
  rosterDeletePattern: (id) => request(`/club-admin/roster/patterns/${id}`, { method: 'DELETE' }),
  rosterGetSettings: () => request('/club-admin/roster/settings'),
  rosterSetSettings: (data) => request('/club-admin/roster/settings', { method: 'PATCH', body: JSON.stringify(data) }),
  // Everyone rostered on for a day / week / month, with the contacts behind
  // them — what "email everyone rostered this week" resolves to.
  rosterContacts: (scope = 'week', on) =>
    request(`/club-admin/roster/contacts?scope=${scope}${on ? `&on=${on}` : ''}`),
  rosterWeek: (weekStart) => request(`/club-admin/roster/week${weekStart ? '?week_start=' + weekStart : ''}`),
  // Shifts are editable in their own right, not only generated from a pattern.
  rosterCreateShift: (data) =>
    request('/club-admin/roster/shifts', { method: 'POST', body: JSON.stringify(data) }),
  rosterUpdateShift: (id, data) =>
    request(`/club-admin/roster/shifts/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  rosterDeleteShift: (id) => request(`/club-admin/roster/shifts/${id}`, { method: 'DELETE' }),
  rosterMember: (id) => request(`/club-admin/roster/members/${id}`),
  rosterSetAvailability: (id, days) =>
    request(`/club-admin/roster/members/${id}/availability`, { method: 'PUT', body: JSON.stringify({ days }) }),
  rosterHours: (start, end) => request(`/club-admin/roster/hours?start=${start}&end=${end}`),
  rosterAssign: (weekId, shiftId, memberId) => request(`/club-admin/roster/week/${weekId}/assign`, { method: 'POST', body: JSON.stringify({ shift_id: shiftId, member_id: memberId }) }),
  rosterAutofill: (weekId) => request(`/club-admin/roster/week/${weekId}/autofill`, { method: 'POST' }),
  rosterPublish: (weekId) => request(`/club-admin/roster/week/${weekId}/publish`, { method: 'POST' }),
  // Which roles the club is short of, from the shifts nobody has filled.
  rosterShortages: (weeks = 4) => request(`/club-admin/roster/shortages?weeks=${weeks}`),
  rosterReset: (weekId) => request(`/club-admin/roster/week/${weekId}/reset`, { method: 'POST' }),
  // Confirming the roster: check what was worked, then post it to the hours ledger.
  rosterConfirmReview: (weekId) => request(`/club-admin/roster/week/${weekId}/confirm-review`),
  rosterSaveWorkedHours: (weekId, entries) =>
    request(`/club-admin/roster/week/${weekId}/worked-hours`, { method: 'PUT', body: JSON.stringify({ entries }) }),
  rosterConfirm: (weekId, entries) =>
    request(`/club-admin/roster/week/${weekId}/confirm`, { method: 'POST', body: JSON.stringify({ entries }) }),
  rosterUnconfirm: (weekId) => request(`/club-admin/roster/week/${weekId}/unconfirm`, { method: 'POST' }),
  rosterClearConfig: () => request('/club-admin/roster/clear-config', { method: 'POST' }),
  facilityRequests: () => request('/club-admin/facility-requests'),
  facilityRequestCreate: (data) => request('/club-admin/facility-requests', { method: 'POST', body: JSON.stringify(data) }),
  facilityRequestApprove: (id, force) => request(`/club-admin/facility-requests/${id}/approve${force ? '?force=true' : ''}`, { method: 'POST' }),
  facilityRequestDecline: (id) => request(`/club-admin/facility-requests/${id}/decline`, { method: 'POST' }),
  facilityRequestsClear: () => request('/club-admin/facility-requests/clear', { method: 'POST' }),

  // Qualification Management (core capability, not a paid module)
  qualListTypes: (includeInactive) =>
    request(`/club-admin/qualifications/types${includeInactive ? '?include_inactive=true' : ''}`),
  qualCreateType: (data) =>
    request('/club-admin/qualifications/types', { method: 'POST', body: JSON.stringify(data) }),
  qualUpdateType: (id, data) =>
    request(`/club-admin/qualifications/types/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  qualArchiveType: (id) =>
    request(`/club-admin/qualifications/types/${id}`, { method: 'DELETE' }),
  qualSeedStarterTypes: () =>
    request('/club-admin/qualifications/types/seed-starter', { method: 'POST' }),
  qualListMemberQualifications: (memberId) => request(`/club-admin/qualifications/members/${memberId}`),
  qualAddQualification: (data) =>
    request('/club-admin/qualifications/members/qualification', { method: 'POST', body: JSON.stringify(data) }),
  qualUpdateQualification: (id, data) =>
    request(`/club-admin/qualifications/qualification/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  qualDeleteQualification: (id) =>
    request(`/club-admin/qualifications/qualification/${id}`, { method: 'DELETE' }),
  qualExpiringReport: (withinDays) =>
    request(`/club-admin/qualifications/expiring${withinDays ? `?within_days=${withinDays}` : ''}`),

  // Committee Meeting Assistant + AGM elections/voting/motions (core capability,
  // not a paid module — same MANAGE_COMMITTEE cap as the rest of committee.py)
  committeeListAgendaTemplates: () => request('/club-admin/committee/agenda-templates'),
  committeeCreateAgendaTemplate: (data) =>
    request('/club-admin/committee/agenda-templates', { method: 'POST', body: JSON.stringify(data) }),
  committeeUpdateAgendaTemplate: (id, data) =>
    request(`/club-admin/committee/agenda-templates/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  committeeDeleteAgendaTemplate: (id) =>
    request(`/club-admin/committee/agenda-templates/${id}`, { method: 'DELETE' }),

  committeeListMeetings: (meetingType) =>
    request(`/club-admin/committee/meetings${meetingType ? `?meeting_type=${meetingType}` : ''}`),
  committeeCreateMeeting: (data) =>
    request('/club-admin/committee/meetings', { method: 'POST', body: JSON.stringify(data) }),
  committeeGetMeeting: (id) => request(`/club-admin/committee/meetings/${id}`),
  // One fetch for the live meeting screen: meeting, agenda in order, motions
  // with votes, actions raised, attendance, and who can be marked present.
  committeeMeetingRoom: (id) => request(`/club-admin/committee/meetings/${id}/room`),
  // Returns a draft; it is not saved. The secretary decides what is true.
  committeeDraftMinutes: (id) =>
    request(`/club-admin/committee/meetings/${id}/draft-minutes`, { method: 'POST' }),
  committeeReorderAgenda: (meetingId, ids) =>
    request(`/club-admin/committee/meetings/${meetingId}/agenda-items/reorder`, { method: 'POST', body: JSON.stringify({ ids }) }),
  committeeReorderMotions: (meetingId, ids) =>
    request(`/club-admin/committee/meetings/${meetingId}/motions/reorder`, { method: 'POST', body: JSON.stringify({ ids }) }),
  committeeUpdateMeeting: (id, data) =>
    request(`/club-admin/committee/meetings/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  committeeDeleteMeeting: (id) =>
    request(`/club-admin/committee/meetings/${id}`, { method: 'DELETE' }),
  committeeSetAttendance: (meetingId, entries) =>
    request(`/club-admin/committee/meetings/${meetingId}/attendance`, { method: 'PUT', body: JSON.stringify({ entries }) }),

  committeeCreateAgendaItem: (meetingId, data) =>
    request(`/club-admin/committee/meetings/${meetingId}/agenda-items`, { method: 'POST', body: JSON.stringify(data) }),
  committeeUpdateAgendaItem: (meetingId, itemId, data) =>
    request(`/club-admin/committee/meetings/${meetingId}/agenda-items/${itemId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  committeeDeleteAgendaItem: (meetingId, itemId) =>
    request(`/club-admin/committee/meetings/${meetingId}/agenda-items/${itemId}`, { method: 'DELETE' }),

  committeeCreateMotion: (meetingId, data) =>
    request(`/club-admin/committee/meetings/${meetingId}/motions`, { method: 'POST', body: JSON.stringify(data) }),
  committeeUpdateMotion: (meetingId, motionId, data) =>
    request(`/club-admin/committee/meetings/${meetingId}/motions/${motionId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  committeeDeleteMotion: (meetingId, motionId) =>
    request(`/club-admin/committee/meetings/${meetingId}/motions/${motionId}`, { method: 'DELETE' }),

  committeeCreateNomination: (meetingId, data) =>
    request(`/club-admin/committee/meetings/${meetingId}/nominations`, { method: 'POST', body: JSON.stringify(data) }),
  committeeUpdateNomination: (meetingId, nominationId, data) =>
    request(`/club-admin/committee/meetings/${meetingId}/nominations/${nominationId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  committeeDeleteNomination: (meetingId, nominationId) =>
    request(`/club-admin/committee/meetings/${meetingId}/nominations/${nominationId}`, { method: 'DELETE' }),

  // Events/Ticketing (core capability, not a paid module) — ClubEvent CRUD
  // itself is committeeListEvents/CreateEvent/UpdateEvent/DeleteEvent above;
  // these are the registration/capacity endpoints on top.
  eventListRegistrations: (eventId) => request(`/club-admin/events/${eventId}/registrations`),
  eventCreateRegistration: (eventId, data) =>
    request(`/club-admin/events/${eventId}/registrations`, { method: 'POST', body: JSON.stringify(data) }),
  eventUpdateRegistration: (eventId, regId, data) =>
    request(`/club-admin/events/${eventId}/registrations/${regId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  eventDeleteRegistration: (eventId, regId) =>
    request(`/club-admin/events/${eventId}/registrations/${regId}`, { method: 'DELETE' }),
  // Public — unauthenticated event view + register (event_id-keyed link)
  publicEventGet: (eventId) => request(`/public/events/${eventId}`),
  publicEventRegister: (eventId, data) =>
    request(`/public/events/${eventId}/register`, { method: 'POST', body: JSON.stringify(data) }),

  // Assets & Facilities (core capability, not a paid module)
  assetsListFacilities: (includeInactive) =>
    request(`/club-admin/assets/facilities${includeInactive ? '?include_inactive=true' : ''}`),
  assetsSeedFacilities: () => request('/club-admin/assets/facilities/seed-starter', { method: 'POST' }),
  assetsSeedItems: () => request('/club-admin/assets/items/seed-starter', { method: 'POST' }),
  assetsCreateFacility: (data) =>
    request('/club-admin/assets/facilities', { method: 'POST', body: JSON.stringify(data) }),
  assetsUpdateFacility: (id, data) =>
    request(`/club-admin/assets/facilities/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  assetsDeleteFacility: (id) =>
    request(`/club-admin/assets/facilities/${id}`, { method: 'DELETE' }),

  assetsListBookings: ({ facilityId, upcomingOnly } = {}) => {
    const qs = new URLSearchParams()
    if (facilityId) qs.set('facility_id', facilityId)
    if (upcomingOnly) qs.set('upcoming_only', 'true')
    const q = qs.toString()
    return request(`/club-admin/assets/bookings${q ? `?${q}` : ''}`)
  },
  assetsCreateBooking: (data) =>
    request('/club-admin/assets/bookings', { method: 'POST', body: JSON.stringify(data) }),
  assetsUpdateBooking: (id, data) =>
    request(`/club-admin/assets/bookings/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  assetsDeleteBooking: (id) =>
    request(`/club-admin/assets/bookings/${id}`, { method: 'DELETE' }),

  assetsListItems: ({ includeInactive, category, status } = {}) => {
    const qs = new URLSearchParams()
    if (includeInactive) qs.set('include_inactive', 'true')
    if (category) qs.set('category', category)
    if (status) qs.set('status', status)
    const q = qs.toString()
    return request(`/club-admin/assets/items${q ? `?${q}` : ''}`)
  },
  assetsCreateItem: (data) =>
    request('/club-admin/assets/items', { method: 'POST', body: JSON.stringify(data) }),
  assetsUpdateItem: (id, data) =>
    request(`/club-admin/assets/items/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  assetsDeleteItem: (id) =>
    request(`/club-admin/assets/items/${id}`, { method: 'DELETE' }),

  assetsListMaintenanceLogs: (subjectType, subjectId) =>
    request(`/club-admin/assets/maintenance-logs?subject_type=${subjectType}&subject_id=${subjectId}`),
  assetsCreateMaintenanceLog: (data) =>
    request('/club-admin/assets/maintenance-logs', { method: 'POST', body: JSON.stringify(data) }),
  assetsDeleteMaintenanceLog: (id) =>
    request(`/club-admin/assets/maintenance-logs/${id}`, { method: 'DELETE' }),

  // Member self-service portal — admin-side visibility check (migration 178).
  // No capability required; the real gates sit on the endpoints below.
  memberPortalStatus: () => request('/club-admin/member-portal/status'),

  // Stripe Connect — club-to-member fee payments (migration 178). Gated by
  // MANAGE_FEES + platform_settings.member_portal_enabled_for_org server-side.
  stripeConnectStatus: () => request('/club-admin/stripe-connect/status'),
  stripeConnectConnect: () => request('/club-admin/stripe-connect/connect', { method: 'POST' }),
  stripeConnectRefresh: () => request('/club-admin/stripe-connect/refresh', { method: 'POST' }),
  stripeConnectDashboardLink: () => request('/club-admin/stripe-connect/dashboard-link', { method: 'POST' }),
  stripeConnectDisconnect: () => request('/club-admin/stripe-connect/disconnect', { method: 'POST' }),

  // Public member self-service portal (unauthenticated — magic-link email
  // sign-in, no shared link/PIN). See services/member_portal_auth.py.
  portalStatus: (slug) => request(`/public/member-portal/${slug}/status`),
  portalRequestLink: (slug, email) =>
    request(`/public/member-portal/${slug}/request-link`, { method: 'POST', body: JSON.stringify({ email }) }),
  portalVerify: (slug, token) =>
    request(`/public/member-portal/${slug}/verify?token=${encodeURIComponent(token)}`),
  portalMe: (slug) => request(`/public/member-portal/${slug}/me`),
  portalUpdateMe: (slug, data) =>
    request(`/public/member-portal/${slug}/me`, { method: 'PATCH', body: JSON.stringify(data) }),
  portalLogout: (slug) => request(`/public/member-portal/${slug}/logout`, { method: 'POST' }),
  portalPay: (slug, kind) =>
    request(`/public/member-portal/${slug}/pay`, { method: 'POST', body: JSON.stringify({ kind }) }),

  // Merch storefront — admin (migration 179). Gated by MANAGE_MERCH + merch
  // module + platform_settings.merch_storefront_enabled_for_org.
  merchStorefrontStatus: () => request('/club-admin/merch/storefront-status'),
  merchListOrders: (status) => request(`/club-admin/merch/orders${status ? `?status=${status}` : ''}`),
  merchUpdateOrder: (id, status) =>
    request(`/club-admin/merch/orders/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) }),

  // Merch storefront — public (unauthenticated). See routers/public_merch_store.py.
  shopStatus: (slug) => request(`/public/merch-store/${slug}/status`),
  shopCatalogue: (slug) => request(`/public/merch-store/${slug}/catalogue`),
  shopCheckout: (slug, data) =>
    request(`/public/merch-store/${slug}/checkout`, { method: 'POST', body: JSON.stringify(data) }),

  // Club Diary — annual/recurring compliance & maintenance task calendar
  // (core capability, not a paid module).
  diaryListCategories: () => request('/club-admin/club-diary/categories'),
  diaryCreateCategory: (name) =>
    request('/club-admin/club-diary/categories', { method: 'POST', body: JSON.stringify({ name }) }),
  diaryUpdateCategory: (id, data) =>
    request(`/club-admin/club-diary/categories/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  diaryDeleteCategory: (id) =>
    request(`/club-admin/club-diary/categories/${id}`, { method: 'DELETE' }),
  diaryListDefinitions: (includeInactive) =>
    request(`/club-admin/club-diary/definitions${includeInactive ? '?include_inactive=true' : ''}`),
  diaryCreateDefinition: (data) =>
    request('/club-admin/club-diary/definitions', { method: 'POST', body: JSON.stringify(data) }),
  diaryUpdateDefinition: (id, data) =>
    request(`/club-admin/club-diary/definitions/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  diaryArchiveDefinition: (id) =>
    request(`/club-admin/club-diary/definitions/${id}`, { method: 'DELETE' }),
  diarySeedStarterDefinitions: () =>
    request('/club-admin/club-diary/definitions/seed-starter', { method: 'POST' }),
  diaryDefinitionHistory: (id) => request(`/club-admin/club-diary/definitions/${id}/history`),
  diaryBoard: () => request('/club-admin/club-diary/board'),
  diaryUpdateOccurrence: (id, data) =>
    request(`/club-admin/club-diary/occurrences/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  diarySeedStarterCategories: () =>
    request('/club-admin/club-diary/categories/seed-starter', { method: 'POST' }),
  diaryAddDependency: (definitionId, dependsOnId) =>
    request(`/club-admin/club-diary/definitions/${definitionId}/dependencies`, { method: 'POST', body: JSON.stringify({ depends_on_definition_id: dependsOnId }) }),
  diaryRemoveDependency: (definitionId, dependsOnId) =>
    request(`/club-admin/club-diary/definitions/${definitionId}/dependencies/${dependsOnId}`, { method: 'DELETE' }),
  diarySeasonYears: () => request('/club-admin/club-diary/season-years'),
  diaryGenerateSeason: (year) =>
    request(`/club-admin/club-diary/season/${year}/generate`, { method: 'POST' }),
  diarySeasonPlan: (year) => request(`/club-admin/club-diary/season/${year}`),

  // Shared member/person picker across BetterClubManager (all org members).
  feeAllMembers: () => request('/club-admin/fees/all-members'),
  // Type-to-search across everyone in the club, members and not-yet-enrolled
  // players alike. Used instead of shipping a whole roster to draw a dropdown.
  searchClubPeople: (q, limit) =>
    request(`/club-admin/fees/people/search?q=${encodeURIComponent(q)}${limit ? `&limit=${limit}` : ''}`),

  // Roles & Activities taxonomy (core capability, shared by Volunteers + Qualifications)
  raRoleTypes: (includeInactive) =>
    request(`/club-admin/roles-activities/role-types${includeInactive ? '?include_inactive=true' : ''}`),
  raCreateRoleType: (data) =>
    request('/club-admin/roles-activities/role-types', { method: 'POST', body: JSON.stringify(data) }),
  raUpdateRoleType: (id, data) =>
    request(`/club-admin/roles-activities/role-types/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  raArchiveRoleType: (id) =>
    request(`/club-admin/roles-activities/role-types/${id}`, { method: 'DELETE' }),
  raSeedRoleTypes: () =>
    request('/club-admin/roles-activities/role-types/seed-starter', { method: 'POST' }),
  // opts: { includeInactive, committee } (committee true|false filters by kind)
  raRoles: (opts = {}) => {
    const qs = new URLSearchParams()
    if (opts.includeInactive) qs.set('include_inactive', 'true')
    if (opts.committee === true) qs.set('committee', 'true')
    if (opts.committee === false) qs.set('committee', 'false')
    const q = qs.toString()
    return request(`/club-admin/roles-activities/roles${q ? `?${q}` : ''}`)
  },
  raCreateRole: (data) =>
    request('/club-admin/roles-activities/roles', { method: 'POST', body: JSON.stringify(data) }),
  raUpdateRole: (id, data) =>
    request(`/club-admin/roles-activities/roles/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  raArchiveRole: (id) =>
    request(`/club-admin/roles-activities/roles/${id}`, { method: 'DELETE' }),
  raSeedRoles: (committee) =>
    request(`/club-admin/roles-activities/roles/seed-starter${committee ? '?committee=true' : ''}`, { method: 'POST' }),
  raActivityTypes: (includeInactive) =>
    request(`/club-admin/roles-activities/activity-types${includeInactive ? '?include_inactive=true' : ''}`),
  raCreateActivityType: (data) =>
    request('/club-admin/roles-activities/activity-types', { method: 'POST', body: JSON.stringify(data) }),
  raUpdateActivityType: (id, data) =>
    request(`/club-admin/roles-activities/activity-types/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  raArchiveActivityType: (id) =>
    request(`/club-admin/roles-activities/activity-types/${id}`, { method: 'DELETE' }),
  raSeedActivityTypes: () =>
    request('/club-admin/roles-activities/activity-types/seed-starter', { method: 'POST' }),
  raActivities: (includeInactive) =>
    request(`/club-admin/roles-activities/activities${includeInactive ? '?include_inactive=true' : ''}`),
  raCreateActivity: (data) =>
    request('/club-admin/roles-activities/activities', { method: 'POST', body: JSON.stringify(data) }),
  raUpdateActivity: (id, data) =>
    request(`/club-admin/roles-activities/activities/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  raArchiveActivity: (id) =>
    request(`/club-admin/roles-activities/activities/${id}`, { method: 'DELETE' }),
  raSeedActivities: () =>
    request('/club-admin/roles-activities/activities/seed-starter', { method: 'POST' }),

  // Event types (club-defined catalogue + starter sets)
  eventListTypes: (includeInactive) =>
    request(`/club-admin/events/event-types${includeInactive ? '?include_inactive=true' : ''}`),
  eventCreateType: (data) =>
    request('/club-admin/events/event-types', { method: 'POST', body: JSON.stringify(data) }),
  eventUpdateType: (id, data) =>
    request(`/club-admin/events/event-types/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  eventArchiveType: (id) =>
    request(`/club-admin/events/event-types/${id}`, { method: 'DELETE' }),
  eventSeedTypes: (committeeOnly) =>
    request(`/club-admin/events/event-types/seed-starter${committeeOnly ? '?committee_only=true' : ''}`, { method: 'POST' }),

  // Club admin — Membership Types (migration 175) — the cross-season
  // catalogue a member's membership_type_id points at.
  feeListMembershipTypes: (includeInactive) =>
    request(`/club-admin/fees/membership-types${includeInactive ? '?include_inactive=true' : ''}`),
  feeCreateMembershipType: (data) =>
    request('/club-admin/fees/membership-types', { method: 'POST', body: JSON.stringify(data) }),
  feeUpdateMembershipType: (id, data) =>
    request(`/club-admin/fees/membership-types/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  feeArchiveMembershipType: (id) =>
    request(`/club-admin/fees/membership-types/${id}`, { method: 'DELETE' }),
  feeSeedStarterMembershipTypes: () =>
    request('/club-admin/fees/membership-types/seed-starter', { method: 'POST' }),

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
        const err = await res.json().catch(() => ({ detail: statusMessage(res) }))
        throw new Error(typeof err.detail === 'string' ? err.detail : `HTTP ${res.status}`)
      }
      return res.json()
    })
  },
  feeImportCommit: (items) =>
    request('/club-admin/fees/payments/import/commit', {
      method: 'POST', body: JSON.stringify({ items }),
    }),
  // Square import (reuses BetterMerch's Square connection)
  feeSquareStatus: () => request('/club-admin/fees/square/status'),
  feeSquareSettings: (data) =>
    request('/club-admin/fees/square/settings', { method: 'POST', body: JSON.stringify(data) }),
  feeSquarePreview: (seasonId) =>
    request(`/club-admin/fees/square/preview?season_id=${seasonId}`, { method: 'POST' }),
  feeSquareCommit: (items) =>
    request('/club-admin/fees/square/commit', { method: 'POST', body: JSON.stringify({ items }) }),
  feeSquareDismiss: (data) =>
    request('/club-admin/fees/square/dismiss', { method: 'POST', body: JSON.stringify(data) }),
  // Xero import (own OAuth connection, owned entirely by BetterFees)
  feeXeroStatus: () => request('/club-admin/fees/xero/status'),
  feeXeroConnectUrl: () => request('/club-admin/fees/xero/connect-url'),
  feeXeroTenants: () => request('/club-admin/fees/xero/tenants'),
  feeXeroSetTenant: (tenantId, tenantName) =>
    request('/club-admin/fees/xero/tenant', { method: 'POST', body: JSON.stringify({ tenant_id: tenantId, tenant_name: tenantName }) }),
  feeXeroBankAccounts: () => request('/club-admin/fees/xero/bank-accounts'),
  feeXeroSetBankAccount: (bankAccountId, bankAccountName) =>
    request('/club-admin/fees/xero/bank-account', { method: 'POST', body: JSON.stringify({ bank_account_id: bankAccountId, bank_account_name: bankAccountName }) }),
  feeXeroSettings: (data) =>
    request('/club-admin/fees/xero/settings', { method: 'POST', body: JSON.stringify(data) }),
  feeXeroPreview: (seasonId) =>
    request(`/club-admin/fees/xero/preview?season_id=${seasonId}`, { method: 'POST' }),
  feeXeroCommit: (items) =>
    request('/club-admin/fees/xero/commit', { method: 'POST', body: JSON.stringify({ items }) }),
  feeXeroDismiss: (data) =>
    request('/club-admin/fees/xero/dismiss', { method: 'POST', body: JSON.stringify(data) }),
  feeXeroDisconnect: () => request('/club-admin/fees/xero/disconnect', { method: 'POST' }),
  // ─── BetterMerch (BetterAdmin module) — club stock register ─────────────────
  merchOverview: () => request('/club-admin/merch/overview'),
  merchAlerts: () => request('/club-admin/merch/alerts'),
  merchListProducts: ({ category, categoryId, q, includeInactive } = {}) => {
    const p = new URLSearchParams()
    if (category) p.set('category', category)
    if (categoryId) p.set('category_id', categoryId)
    if (q) p.set('q', q)
    if (includeInactive) p.set('include_inactive', 'true')
    const qs = p.toString()
    return request(`/club-admin/merch/products${qs ? `?${qs}` : ''}`)
  },
  merchListCategories: () => request('/club-admin/merch/categories'),
  merchSeedCategories: () => request('/club-admin/merch/categories/seed-defaults', { method: 'POST' }),
  merchCreateCategory: (data) =>
    request('/club-admin/merch/categories', { method: 'POST', body: JSON.stringify(data) }),
  merchRenameCategory: (id, data) =>
    request(`/club-admin/merch/categories/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  merchDeleteCategory: (id) =>
    request(`/club-admin/merch/categories/${id}`, { method: 'DELETE' }),
  merchGetProduct: (id) => request(`/club-admin/merch/products/${id}`),
  merchCreateProduct: (data) =>
    request('/club-admin/merch/products', { method: 'POST', body: JSON.stringify(data) }),
  merchUpdateProduct: (id, data) =>
    request(`/club-admin/merch/products/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  merchDeleteProduct: (id) =>
    request(`/club-admin/merch/products/${id}`, { method: 'DELETE' }),
  merchAddVariant: (productId, data) =>
    request(`/club-admin/merch/products/${productId}/variants`, { method: 'POST', body: JSON.stringify(data) }),
  merchUpdateVariant: (id, data) =>
    request(`/club-admin/merch/variants/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  merchDeleteVariant: (id) =>
    request(`/club-admin/merch/variants/${id}`, { method: 'DELETE' }),
  merchListMovements: ({ variantId, productId, playerId, kind, unpaidOnly, limit } = {}) => {
    const p = new URLSearchParams()
    if (variantId) p.set('variant_id', variantId)
    if (productId) p.set('product_id', productId)
    if (playerId) p.set('player_id', playerId)
    if (kind) p.set('kind', kind)
    if (unpaidOnly) p.set('unpaid_only', 'true')
    if (limit) p.set('limit', String(limit))
    const qs = p.toString()
    return request(`/club-admin/merch/movements${qs ? `?${qs}` : ''}`)
  },
  merchRecordMovement: (data) =>
    request('/club-admin/merch/movements', { method: 'POST', body: JSON.stringify(data) }),
  merchUpdateMovement: (id, data) =>
    request(`/club-admin/merch/movements/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  merchDeleteMovement: (id) =>
    request(`/club-admin/merch/movements/${id}`, { method: 'DELETE' }),
  merchListAssets: ({ includeInactive } = {}) =>
    request(`/club-admin/merch/assets${includeInactive ? '?include_inactive=true' : ''}`),
  merchCreateAsset: (data) =>
    request('/club-admin/merch/assets', { method: 'POST', body: JSON.stringify(data) }),
  merchUpdateAsset: (id, data) =>
    request(`/club-admin/merch/assets/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  merchDeleteAsset: (id) =>
    request(`/club-admin/merch/assets/${id}`, { method: 'DELETE' }),
  merchSearchPlayers: (q) =>
    request(`/club-admin/merch/players${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  merchPlayer: (playerId) => request(`/club-admin/merch/players/${playerId}/merch`),
  merchReportSummary: () => request('/club-admin/merch/reports/summary'),
  merchExportUrl: () => `${BASE}/club-admin/merch/reports/export`,
  // BetterMerch — Square POS integration
  merchSquareStatus: () => request('/club-admin/merch/square/status'),
  merchSquareConnectUrl: () => request('/club-admin/merch/square/connect-url'),
  merchSquareLocations: () => request('/club-admin/merch/square/locations'),
  merchSquareSetLocation: (locationId, locationName) =>
    request('/club-admin/merch/square/location', { method: 'POST', body: JSON.stringify({ location_id: locationId, location_name: locationName }) }),
  merchSquareSettings: (data) =>
    request('/club-admin/merch/square/settings', { method: 'POST', body: JSON.stringify(data) }),
  merchSquareSync: () => request('/club-admin/merch/square/sync', { method: 'POST' }),
  merchSquareDisconnect: () => request('/club-admin/merch/square/disconnect', { method: 'POST' }),
  // ─── BetterCRM — club-scope (BetterAdmin module) ─────────────────────────────
  // Pipelines are opt-in "trackers" a club adds from a preset catalogue
  // (Sponsors/Grants/Alumni & Fundraising) or builds fully custom — see
  // services/crm.py's PIPELINE_TEMPLATES. Nothing is auto-seeded.
  crmTrackerCatalogue: () => request('/club-admin/crm/trackers'),
  crmActiveTrackers: () => request('/club-admin/crm/trackers/active'),
  crmAddTracker: (data) => request('/club-admin/crm/trackers', { method: 'POST', body: JSON.stringify(data) }),
  crmRemoveTracker: (pipelineId) => request(`/club-admin/crm/trackers/${pipelineId}`, { method: 'DELETE' }),
  crmReactivateTracker: (pipelineId) => request(`/club-admin/crm/trackers/${pipelineId}/reactivate`, { method: 'POST' }),
  crmPipelineBoard: (pipelineId) => request(`/club-admin/crm/pipelines/${pipelineId}/board`),
  crmStages: (pipelineId) => request(`/club-admin/crm/pipelines/${pipelineId}/stages`),
  crmAddStage: (pipelineId, data) => request(`/club-admin/crm/pipelines/${pipelineId}/stages`, { method: 'POST', body: JSON.stringify(data) }),
  crmUpdateStage: (stageId, data) => request(`/club-admin/crm/stages/${stageId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  crmDeleteStage: (stageId) => request(`/club-admin/crm/stages/${stageId}`, { method: 'DELETE' }),
  crmListDeals: (pipelineId, { status, includeArchived } = {}) => {
    const p = new URLSearchParams()
    if (status) p.set('status', status)
    if (includeArchived) p.set('include_archived', 'true')
    const qs = p.toString()
    return request(`/club-admin/crm/pipelines/${pipelineId}/deals${qs ? `?${qs}` : ''}`)
  },
  crmCreateDeal: (pipelineId, data) => request(`/club-admin/crm/pipelines/${pipelineId}/deals`, { method: 'POST', body: JSON.stringify(data) }),
  crmGetDeal: (id) => request(`/club-admin/crm/deals/${id}`),
  crmUpdateDeal: (id, data) => request(`/club-admin/crm/deals/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  crmMoveDealStage: (id, data) => request(`/club-admin/crm/deals/${id}/stage`, { method: 'POST', body: JSON.stringify(data) }),
  crmCloseDeal: (id, data) => request(`/club-admin/crm/deals/${id}/close`, { method: 'POST', body: JSON.stringify(data) }),
  crmArchiveDeal: (id) => request(`/club-admin/crm/deals/${id}`, { method: 'DELETE' }),
  crmDeleteDealPermanent: (id) => request(`/club-admin/crm/deals/${id}/permanent`, { method: 'DELETE' }),
  crmListActivities: (dealId) => request(`/club-admin/crm/deals/${dealId}/activities`),
  crmAddActivity: (dealId, data) => request(`/club-admin/crm/deals/${dealId}/activities`, { method: 'POST', body: JSON.stringify(data) }),
  crmListDealContacts: (dealId) => request(`/club-admin/crm/deals/${dealId}/contacts`),
  crmLinkContact: (dealId, data) => request(`/club-admin/crm/deals/${dealId}/contacts`, { method: 'POST', body: JSON.stringify(data) }),
  crmUnlinkContact: (dealId, personId) => request(`/club-admin/crm/deals/${dealId}/contacts/${personId}`, { method: 'DELETE' }),
  crmSetPointOfContact: (dealId, data) => request(`/club-admin/crm/deals/${dealId}/point-of-contact`, { method: 'POST', body: JSON.stringify(data) }),
  crmListPeople: (q) => request(`/club-admin/crm/people${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  crmCreatePerson: (data) => request('/club-admin/crm/people', { method: 'POST', body: JSON.stringify(data) }),
  crmUpdatePerson: (id, data) => request(`/club-admin/crm/people/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  superCrmUpdatePerson: (id, data) => request(`/club-admin/super/crm/people/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  crmAddPersonRole: (id, data) => request(`/club-admin/crm/people/${id}/roles`, { method: 'POST', body: JSON.stringify(data) }),
  // ─── BetterCRM — platform scope (BetterCricket's own sales pipeline) ────────
  superCrmPipeline: () => request('/club-admin/super/crm/pipeline'),
  superCrmStages: () => request('/club-admin/super/crm/stages'),
  superCrmAddStage: (_pipelineId, data) => request('/club-admin/super/crm/stages', { method: 'POST', body: JSON.stringify(data) }),
  superCrmUpdateStage: (stageId, data) => request(`/club-admin/super/crm/stages/${stageId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  superCrmDeleteStage: (stageId) => request(`/club-admin/super/crm/stages/${stageId}`, { method: 'DELETE' }),
  superCrmListDeals: ({ status, includeArchived } = {}) => {
    const p = new URLSearchParams()
    if (status) p.set('status', status)
    if (includeArchived) p.set('include_archived', 'true')
    const qs = p.toString()
    return request(`/club-admin/super/crm/deals${qs ? `?${qs}` : ''}`)
  },
  superCrmRecalcEngagement: () => request('/club-admin/super/crm/recalc-engagement', { method: 'POST' }),
  superCrmRecalcEngagementStatus: () => request('/club-admin/super/crm/recalc-engagement/status'),
  // Turn the current filtered deal set into an auto-generated BetterComms List.
  superCrmListExportPrepare: (dealIds) =>
    request('/club-admin/super/crm/list-export/prepare', { method: 'POST', body: JSON.stringify({ deal_ids: dealIds }) }),
  superCrmListExportCommit: (data) =>
    request('/club-admin/super/crm/list-export/commit', { method: 'POST', body: JSON.stringify(data) }),
  superCrmGetSettings: () => request('/club-admin/super/crm/settings'),
  superCrmUpdateSettings: (data) => request('/club-admin/super/crm/settings', { method: 'PATCH', body: JSON.stringify(data) }),
  superCrmCreateDeal: (data) => request('/club-admin/super/crm/deals', { method: 'POST', body: JSON.stringify(data) }),
  superCrmGetDeal: (id) => request(`/club-admin/super/crm/deals/${id}`),
  superCrmUpdateDeal: (id, data) => request(`/club-admin/super/crm/deals/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  superCrmMoveDealStage: (id, data) => request(`/club-admin/super/crm/deals/${id}/stage`, { method: 'POST', body: JSON.stringify(data) }),
  superCrmRecalcProductInterest: (id) => request(`/club-admin/super/crm/deals/${id}/recalc-product-interest`, { method: 'POST' }),
  superCrmListTargets: (periodType) =>
    request(`/club-admin/super/crm/targets${periodType ? `?period_type=${periodType}` : ''}`),
  superCrmUpsertTarget: (body) => request('/club-admin/super/crm/targets', { method: 'POST', body: JSON.stringify(body) }),
  superCrmDeleteTarget: (id) => request(`/club-admin/super/crm/targets/${id}`, { method: 'DELETE' }),
  superCrmTargetActuals: (periodType, periodKey) =>
    request(`/club-admin/super/crm/targets/actuals?period_type=${periodType}&period_key=${encodeURIComponent(periodKey)}`),
  superCrmListAutomation: () => request('/club-admin/super/crm/automation'),
  superCrmCreateAutomation: (data) =>
    request('/club-admin/super/crm/automation', { method: 'POST', body: JSON.stringify(data) }),
  superCrmUpdateAutomation: (id, data) =>
    request(`/club-admin/super/crm/automation/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  superCrmDeleteAutomation: (id) => request(`/club-admin/super/crm/automation/${id}`, { method: 'DELETE' }),
  superCrmCloseDeal: (id, data) => request(`/club-admin/super/crm/deals/${id}/close`, { method: 'POST', body: JSON.stringify(data) }),
  superCrmArchiveDeal: (id) => request(`/club-admin/super/crm/deals/${id}`, { method: 'DELETE' }),
  superCrmDeleteDealPermanent: (id, resetClub) =>
    request(`/club-admin/super/crm/deals/${id}/permanent${resetClub ? '?reset_club=true' : ''}`, { method: 'DELETE' }),
  superCrmListActivities: (dealId) => request(`/club-admin/super/crm/deals/${dealId}/activities`),
  superCrmAddActivity: (dealId, data) => request(`/club-admin/super/crm/deals/${dealId}/activities`, { method: 'POST', body: JSON.stringify(data) }),
  superCrmListDealContacts: (dealId) => request(`/club-admin/super/crm/deals/${dealId}/contacts`),
  superCrmLinkContact: (dealId, data) => request(`/club-admin/super/crm/deals/${dealId}/contacts`, { method: 'POST', body: JSON.stringify(data) }),
  superCrmUnlinkContact: (dealId, personId) => request(`/club-admin/super/crm/deals/${dealId}/contacts/${personId}`, { method: 'DELETE' }),
  superCrmSetPointOfContact: (dealId, data) => request(`/club-admin/super/crm/deals/${dealId}/point-of-contact`, { method: 'POST', body: JSON.stringify(data) }),
  superCrmOwners: () => request('/club-admin/super/crm/owners'),
  superCrmListPeople: (q, marketingClubId) => {
    const p = new URLSearchParams()
    if (q) p.set('q', q)
    if (marketingClubId) p.set('marketing_club_id', marketingClubId)
    const qs = p.toString()
    return request(`/club-admin/super/crm/people${qs ? `?${qs}` : ''}`)
  },
  // ─── CRM calendar events ─────────────────────────────────────────────────────
  superCrmListDealEvents: (dealId) => request(`/club-admin/super/crm/deals/${dealId}/events`),
  superCrmAddDealEvent: (dealId, data) => request(`/club-admin/super/crm/deals/${dealId}/events`, { method: 'POST', body: JSON.stringify(data) }),
  superCrmListEvents: (params = {}) => {
    const p = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) if (v != null && v !== '') p.set(k, v)
    const qs = p.toString()
    return request(`/club-admin/super/crm/events${qs ? `?${qs}` : ''}`)
  },
  superCrmCreateEvent: (data) => request('/club-admin/super/crm/events', { method: 'POST', body: JSON.stringify(data) }),
  superCrmUpdateEvent: (id, data) => request(`/club-admin/super/crm/events/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  superCrmDeleteEvent: (id) => request(`/club-admin/super/crm/events/${id}`, { method: 'DELETE' }),
  superCrmConvertClub: (marketingClubId, data) =>
    request(`/club-admin/super/crm/from-club/${marketingClubId}`, { method: 'POST', body: JSON.stringify(data) }),
  // ─── BetterImport — overlap-safe historical CSV/XLSX import ──────────────────
  importPreview: (file) => uploadFile('/club-admin/imports/preview', file),
  importResolve: (payload) =>
    request('/club-admin/imports/resolve', { method: 'POST', body: JSON.stringify(payload) }),
  importCommit: (payload) =>
    request('/club-admin/imports/commit', { method: 'POST', body: JSON.stringify(payload) }),
  importList: () => request('/club-admin/imports'),
  importUndo: (batchId) =>
    request(`/club-admin/imports/${batchId}/undo`, { method: 'POST' }),
  importUndoPlayer: (batchId, playerId) =>
    request(`/club-admin/imports/${batchId}/undo-player/${playerId}`, { method: 'POST' }),
  importListPlayers: (batchId) => request(`/club-admin/imports/${batchId}/players`),
  // ─── BetterImport (profiles) — bulk player contact/profile CSV import ────────
  playerImportPreview: (file) => uploadFile('/club-admin/player-import/preview', file),
  playerImportResolve: (payload) =>
    request('/club-admin/player-import/resolve', { method: 'POST', body: JSON.stringify(payload) }),
  playerImportCommit: (payload) =>
    request('/club-admin/player-import/commit', { method: 'POST', body: JSON.stringify(payload) }),
  // ─── KlubPro → BetterStats migration (super-admin onboarding) ────────────────
  kpStatus: () => request('/club-admin/klubpro/status'),
  kpDashboard: () => request('/club-admin/klubpro/dashboard'),
  kpOrganisations: () => request('/club-admin/klubpro/organisations'),
  kpSetClubMapping: (payload) =>
    request('/club-admin/klubpro/club-mapping', { method: 'PATCH', body: JSON.stringify(payload) }),
  kpPlayers: (cm) => request(`/club-admin/klubpro/clubs/${cm}/players`),
  kpSetMatch: (cm, payload) =>
    request(`/club-admin/klubpro/clubs/${cm}/players/match`, { method: 'POST', body: JSON.stringify(payload) }),
  kpBulkApprove: (cm, items) =>
    request(`/club-admin/klubpro/clubs/${cm}/players/bulk-approve`, { method: 'POST', body: JSON.stringify({ items }) }),
  kpPlayerDryRun: (cm) => request(`/club-admin/klubpro/clubs/${cm}/players/dry-run`),
  kpPlayerImport: (cm) =>
    request(`/club-admin/klubpro/clubs/${cm}/players/import`, { method: 'POST', body: JSON.stringify({ confirm: true }) }),
  kpSponsors: (cm) => request(`/club-admin/klubpro/clubs/${cm}/sponsors`),
  kpSponsorDryRun: (cm, ids) =>
    request(`/club-admin/klubpro/clubs/${cm}/sponsors/dry-run`, { method: 'POST', body: JSON.stringify({ selected_ids: ids }) }),
  kpSponsorImport: (cm, ids) =>
    request(`/club-admin/klubpro/clubs/${cm}/sponsors/import`, { method: 'POST', body: JSON.stringify({ selected_ids: ids, confirm: true }) }),
  kpBatches: (orgId) => request(`/club-admin/klubpro/batches${orgId ? `?org_id=${orgId}` : ''}`),
  kpRollback: (batchId) =>
    request(`/club-admin/klubpro/batches/${batchId}/rollback`, { method: 'POST' }),
  // Marketing club directory (super-admin only) — crawl + outreach.
  mktStats: () => request('/club-admin/marketing/stats'),
  mktStatus: () => request('/club-admin/marketing/status'),
  mktClubs: (params = {}) => {
    const qs = mktQS(params)
    return request(`/club-admin/marketing/clubs${qs ? `?${qs}` : ''}`)
  },
  // Cheap name-only typeahead for the CRM New Deal club search — NOT mktClubs
  // (the full directory list), which also computes a COUNT(*) and scans all
  // usage_events for visit/login-intent stats the New Deal modal never shows.
  mktQuickSearchClubs: (q, limit = 8) =>
    request(`/club-admin/marketing/clubs/quick-search?q=${encodeURIComponent(q)}&limit=${limit}`),
  mktAssociations: () => request('/club-admin/marketing/associations'),
  mktCountries: () => request('/club-admin/marketing/countries'),
  mktResolveAssociation: (id, name) =>
    request('/club-admin/marketing/associations/resolve',
      { method: 'POST', body: JSON.stringify({ id, name }) }),
  mktSetAssocShortcode: (id, short) =>
    request(`/club-admin/marketing/associations/${id}/shortcode`,
      { method: 'PATCH', body: JSON.stringify({ short_code: short }) }),
  mktSetClubExcluded: (clubId, excluded) =>
    request(`/club-admin/marketing/clubs/${clubId}/excluded`,
      { method: 'PATCH', body: JSON.stringify({ excluded }) }),
  mktSetClubUtm: (clubId, utm) =>
    request(`/club-admin/marketing/clubs/${clubId}/utm`,
      { method: 'PATCH', body: JSON.stringify({ utm }) }),
  mktClubVisits: (clubId) =>
    request(`/club-admin/marketing/clubs/${clubId}/visits`),
  mktClubEngagement: (clubId) =>
    request(`/club-admin/marketing/clubs/${clubId}/engagement-breakdown`),
  mktClubLoginIntent: (clubId) =>
    request(`/club-admin/marketing/clubs/${clubId}/login-intent`),
  mktClubBoundary: (clubId) =>
    request(`/club-admin/marketing/clubs/${clubId}/boundary`),
  mktUtmValues: () => request('/club-admin/marketing/utm-values'),
  mktSetUtmAlias: (body) =>
    request('/club-admin/marketing/utm-aliases', { method: 'PUT', body: JSON.stringify(body) }),
  mktSetClubSales: (clubId, body) =>
    request(`/club-admin/marketing/clubs/${clubId}/sales`,
      { method: 'PATCH', body: JSON.stringify(body) }),
  mktCrawlControl: (paused) =>
    request('/club-admin/marketing/crawl/control', { method: 'POST', body: JSON.stringify({ paused }) }),
  mktCrawl: (limit) =>
    request(`/club-admin/marketing/crawl${limit ? `?limit=${limit}` : ''}`, { method: 'POST' }),
  mktExportComms: (payload) =>
    request('/club-admin/marketing/export-comms', { method: 'POST', body: JSON.stringify(payload) }),
  mktExportTwenty: (payload) =>
    request('/club-admin/marketing/export-twenty', { method: 'POST', body: JSON.stringify(payload) }),
  mktExportTwentyStatus: () => request('/club-admin/marketing/export-twenty/status'),
  mktPushToCrm: (payload) =>
    request('/club-admin/marketing/push-to-crm', { method: 'POST', body: JSON.stringify(payload) }),
  mktPushToCrmStatus: () => request('/club-admin/marketing/push-to-crm/status'),
  mktRefreshTwentyEngagement: () =>
    request('/club-admin/marketing/refresh-twenty-engagement', { method: 'POST' }),
  mktRefreshTwentyEngagementStatus: () => request('/club-admin/marketing/refresh-twenty-engagement/status'),
  mktRefreshTwentyLeadsTasks: () =>
    request('/club-admin/marketing/refresh-twenty-leads-tasks', { method: 'POST' }),
  mktRefreshTwentyLeadsTasksStatus: () => request('/club-admin/marketing/refresh-twenty-leads-tasks/status'),
  mktSetContactSelected: (contactId, selected) =>
    request(`/club-admin/marketing/contacts/${contactId}`, { method: 'PATCH', body: JSON.stringify({ selected }) }),
  mktUpdateContact: (contactId, patch) =>
    request(`/club-admin/marketing/contacts/${contactId}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  mktAddContact: (clubId, data) =>
    request(`/club-admin/marketing/clubs/${clubId}/contacts`, { method: 'POST', body: JSON.stringify(data) }),
  mktDeleteContact: (contactId) =>
    request(`/club-admin/marketing/contacts/${contactId}`, { method: 'DELETE' }),
  mktSyncSuppressions: (orgId) =>
    request(`/club-admin/marketing/sync-suppressions${orgId ? `?organisation_id=${orgId}` : ''}`, { method: 'POST' }),
  mktExportCsvUrl: (filters = {}) => {
    const qs = mktQS(filters)
    return `${BASE}/club-admin/marketing/export.csv${qs ? `?${qs}` : ''}`
  },
  mktSetClubEmailed: (clubId, emailed, note) =>
    request(`/club-admin/marketing/clubs/${clubId}/emailed`,
      { method: 'PATCH', body: JSON.stringify({ emailed, note: note || null }) }),
  // Bulk apply emailed / excluded to the current filtered list.
  mktBulkEmailed: (value, filters = {}) =>
    request('/club-admin/marketing/clubs/bulk-emailed',
      { method: 'POST', body: JSON.stringify({ ...filters, value }) }),
  mktBulkExcluded: (value, filters = {}) =>
    request('/club-admin/marketing/clubs/bulk-excluded',
      { method: 'POST', body: JSON.stringify({ ...filters, value }) }),
  // Image URLs (used directly in <img src>; cookie auth travels with the request)
  kpPlayerImageUrl: (klubproPlayerId, thumb = false) =>
    `${BASE}/club-admin/klubpro/images/player/${klubproPlayerId}${thumb ? '?thumb=1' : ''}`,
  kpSponsorImageUrl: (klubproSponsorId) =>
    `${BASE}/club-admin/klubpro/images/sponsor/${klubproSponsorId}`,
  bsPlayerPhotoUrl: (playerId) => `${BASE}/images/players/${playerId}/photo`,
  // Phase 3.1 — Per-match-day Mark Paid + bulk payment
  feeMarkMatchDayPaid: (entryId, data = {}) =>
    request(`/club-admin/fees/match-days/${entryId}/mark-paid`, {
      method: 'POST', body: JSON.stringify(data),
    }),
  feeUnmarkMatchDayPaid: (entryId) =>
    request(`/club-admin/fees/match-days/${entryId}/mark-paid`, { method: 'DELETE' }),
  feeWaiveMatchDay: (entryId, data = {}) =>
    request(`/club-admin/fees/match-days/${entryId}/waive`, {
      method: 'POST', body: JSON.stringify(data),
    }),
  feeUnwaiveMatchDay: (entryId) =>
    request(`/club-admin/fees/match-days/${entryId}/waive`, { method: 'DELETE' }),
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
  claimFillIn: (data) =>
    request('/players/claim-fill-in', { method: 'POST', body: JSON.stringify(data) }),
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
  // Usage breadcrumbs (super-admin only). `q` is a free-text search over the
  // path / route / UTM fields — threaded through every analytics view so the
  // whole page reflects "show me everything matching <term>".
  adminUsageRecent: ({ limit = 200, eventType = null, roles = [], q = '' } = {}) => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (eventType) params.set('event_type', eventType)
    ;(roles || []).forEach(r => params.append('role', r))
    if (q) params.set('q', q)
    return request(`/club-admin/usage/recent?${params}`)
  },
  adminUsageTopRoutes: ({ days = 7, limit = 30, eventType = null, roles = [], q = '' } = {}) => {
    const params = new URLSearchParams({ days: String(days), limit: String(limit) })
    if (eventType) params.set('event_type', eventType)
    ;(roles || []).forEach(r => params.append('role', r))
    if (q) params.set('q', q)
    return request(`/club-admin/usage/top-routes?${params}`)
  },
  adminUsageTopUsers: ({ days = 7, limit = 30, roles = [], q = '' } = {}) => {
    const params = new URLSearchParams({ days: String(days), limit: String(limit) })
    ;(roles || []).forEach(r => params.append('role', r))
    if (q) params.set('q', q)
    return request(`/club-admin/usage/top-users?${params}`)
  },
  adminUsageSummary: ({ days = 7, roles = [], eventType = null, q = '' } = {}) => {
    const params = new URLSearchParams({ days: String(days) })
    ;(roles || []).forEach(r => params.append('role', r))
    if (eventType) params.set('event_type', eventType)
    if (q) params.set('q', q)
    return request(`/club-admin/usage/summary?${params}`)
  },
  adminUsageTimeseries: ({ days = 7, roles = [], eventType = null, q = '' } = {}) => {
    const params = new URLSearchParams({ days: String(days) })
    ;(roles || []).forEach(r => params.append('role', r))
    if (eventType) params.set('event_type', eventType)
    if (q) params.set('q', q)
    return request(`/club-admin/usage/timeseries?${params}`)
  },
  adminUsageByFeature: ({ days = 7, roles = [], eventType = null, q = '' } = {}) => {
    const params = new URLSearchParams({ days: String(days) })
    ;(roles || []).forEach(r => params.append('role', r))
    if (eventType) params.set('event_type', eventType)
    if (q) params.set('q', q)
    return request(`/club-admin/usage/by-feature?${params}`)
  },
  adminUsageByRole: ({ days = 7, eventType = null } = {}) => {
    const params = new URLSearchParams({ days: String(days) })
    if (eventType) params.set('event_type', eventType)
    return request(`/club-admin/usage/by-role?${params}`)
  },
  adminUsageByLocation: ({ days = 7, roles = [], eventType = null, q = '' } = {}) => {
    const params = new URLSearchParams({ days: String(days) })
    ;(roles || []).forEach(r => params.append('role', r))
    if (eventType) params.set('event_type', eventType)
    if (q) params.set('q', q)
    return request(`/club-admin/usage/by-location?${params}`)
  },
  adminUsageByClub: ({ days = 7, roles = [], eventType = null, q = '' } = {}) => {
    const params = new URLSearchParams({ days: String(days) })
    ;(roles || []).forEach(r => params.append('role', r))
    if (eventType) params.set('event_type', eventType)
    if (q) params.set('q', q)
    return request(`/club-admin/usage/by-club?${params}`)
  },
  adminUsageVisitors: ({ days = 7, eventType = null, anonOnly = false, q = '' } = {}) => {
    const params = new URLSearchParams({ days: String(days) })
    if (eventType) params.set('event_type', eventType)
    if (anonOnly) params.set('anon_only', 'true')
    if (q) params.set('q', q)
    return request(`/club-admin/usage/visitors?${params}`)
  },
  // Marketing attribution: Meta-ad headline, campaigns/UTM table, ad creatives,
  // landing pages, ad-click conversion. `q` searches the same path/UTM fields.
  adminUsageCampaigns: ({ days = 30, q = '' } = {}) => {
    const params = new URLSearchParams({ days: String(days) })
    if (q) params.set('q', q)
    return request(`/club-admin/usage/campaigns?${params}`)
  },
  // Realtime snapshot: active visitors, per-minute, live feed, top pages, sources, UTMs.
  adminUsageLive: () => request('/club-admin/usage/live'),
  // Snapshot of running background work — syncs, IQ prewarms, in-flight
  // registrations, active Setup Wizard sessions (Current Background Processes).
  adminUsageBackgroundProcesses: () => request('/club-admin/usage/background-processes'),
  // Idle-abandonment limits for the Current Background Processes panel (the
  // Settings dialog): how long a mid-flow registration / onboarding club can sit
  // idle before it's dropped from the panel as abandoned.
  adminUsageBackgroundSettings: () => request('/club-admin/usage/background-settings'),
  adminUpdateUsageBackgroundSettings: (data) =>
    request('/club-admin/usage/background-settings', { method: 'PATCH', body: JSON.stringify(data) }),
  // City-level visitor points for the Usage page map (city-centroid precision only).
  adminUsageGeo: ({ hours = 24 } = {}) => request(`/club-admin/usage/geo?hours=${hours}`),
  // Session duration + per-page dwell time (derived from the page_exit beacon).
  adminUsageSessionDuration: ({ days = 7 } = {}) => {
    const params = new URLSearchParams({ days: String(days) })
    return request(`/club-admin/usage/session-duration?${params}`)
  },
  // One visitor's ordered page-view path, split into sessions with per-page
  // dwell time — the "what did they click through, in what order" view.
  adminUsageJourney: (visitorId, { limit = 300 } = {}) => {
    const params = new URLSearchParams({ visitor_id: visitorId, limit: String(limit) })
    return request(`/club-admin/usage/journey?${params}`)
  },
  // Notification centre (bell icon)
  getNotificationsCount: () => request('/club-admin/notifications/count'),
  getNotificationsSummary: () => request('/club-admin/notifications/summary'),
  markNotificationsSeen: (appVersion) =>
    request('/club-admin/notifications/seen', {
      method: 'POST',
      body: JSON.stringify({ app_version: appVersion || null }),
    }),
  // Club Setup Wizard (always available; /state fails only without a club context)
  getOnboardingWizardState: () => request('/club-admin/onboarding-wizard/state'),
  getSetupFlow: () => request('/club-admin/onboarding-wizard/flow'),
  markOnboardingWizardOpened: () => request('/club-admin/onboarding-wizard/opened', { method: 'POST' }),
  dismissOnboardingWizard: () => request('/club-admin/onboarding-wizard/dismiss', { method: 'POST' }),
  setOnboardingWizardStep: (stepKey, done = true) =>
    request(`/club-admin/onboarding-wizard/steps/${stepKey}`, { method: 'POST', body: JSON.stringify({ done }) }),
  setSetupStep: (stepKey, body) =>
    request(`/club-admin/onboarding-wizard/steps/${stepKey}`, { method: 'POST', body: JSON.stringify(body) }),
  // BetterIQ opposition prewarm (Setup Wizard IQ step)
  iqPrewarmOptions: () => request('/iq/opposition/prewarm/options'),
  iqPrewarmStart: (gradeIds) =>
    request('/iq/opposition/prewarm', { method: 'POST', body: JSON.stringify({ grade_ids: gradeIds }) }),
  iqPrewarmStatus: () => request('/iq/opposition/prewarm/status'),
  // Admin sidebar bookmarks (per-user favourites)
  listBookmarks: () => request('/club-admin/bookmarks'),
  addBookmark: (path, label) =>
    request('/club-admin/bookmarks', {
      method: 'POST',
      body: JSON.stringify({ path, label: label || null }),
    }),
  removeBookmark: (path) =>
    request(`/club-admin/bookmarks?path=${encodeURIComponent(path)}`, { method: 'DELETE' }),

  // Club user management
  getInvite: (token) => request(`/auth/invite/${token}`),
  acceptInvite: (token, data) =>
    request(`/auth/invite/${token}/accept`, { method: 'POST', body: JSON.stringify(data) }),
  getPasswordReset: (token) => request(`/auth/reset-password/${token}`),
  acceptPasswordReset: (token, data) =>
    request(`/auth/reset-password/${token}/accept`, { method: 'POST', body: JSON.stringify(data) }),
  forgotPassword: (email) => request('/auth/forgot-password', { method: 'POST', body: JSON.stringify({ email }) }),
  adminListClubUsers: () => request('/club-admin/users'),
  adminListCapabilities: () => request('/club-admin/users/capabilities'),
  adminCreateClubUser: (data) =>
    request('/club-admin/users', { method: 'POST', body: JSON.stringify(data) }),
  adminUpdateClubUser: (userId, data) =>
    request(`/club-admin/users/${userId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  adminDeleteClubUser: (userId) =>
    request(`/club-admin/users/${userId}`, { method: 'DELETE' }),
  adminSendPasswordReset: (userId) =>
    request(`/club-admin/users/${userId}/send-password-reset`, { method: 'POST' }),
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
  adminUploadFont: (role, file, family) => {
    const form = new FormData()
    form.append('file', file)
    if (family) form.append('family', family)
    return fetch(`${BASE}/club-admin/font/${role}`, { method: 'POST', body: form, credentials: 'include' })
      .then(async r => {
        if (!r.ok) {
          const e = await r.json().catch(() => ({}))
          throw new Error(typeof e.detail === 'string' ? e.detail : `HTTP ${r.status}`)
        }
        return r.json()
      })
  },
  adminDeleteFont: (role) => request(`/club-admin/font/${role}`, { method: 'DELETE' }),
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
  adminCreateManualSeason: (data) =>
    request('/club-admin/manual-entries/seasons', { method: 'POST', body: JSON.stringify(data) }),
  adminDeleteManualSeason: (id) =>
    request(`/club-admin/manual-entries/seasons/${id}`, { method: 'DELETE' }),
  adminCreateManualGrade: (data) =>
    request('/club-admin/manual-entries/grades', { method: 'POST', body: JSON.stringify(data) }),
  adminDeleteManualGrade: (id) =>
    request(`/club-admin/manual-entries/grades/${id}`, { method: 'DELETE' }),
  adminListManualEntryKnownValues: () => request('/club-admin/manual-entries/known-values'),
  adminCheckScorecardDuplicate: (playedAt, opponent = '', excludeId = '') =>
    request(`/club-admin/manual-entries/scorecard/check-duplicate?played_at=${encodeURIComponent(playedAt)}&opponent=${encodeURIComponent(opponent)}${excludeId ? `&exclude_id=${encodeURIComponent(excludeId)}` : ''}`),

  // Upload Historical Scorecard: POST photo(s), get a reviewed both-team scorecard
  // back (the model reads them, we don't write anything until the admin imports).
  adminExtractScorecard: (fileList) => {
    const form = new FormData()
    Array.from(fileList).forEach(f => form.append('files', f))
    return fetch(`${BASE}/club-admin/manual-entries/scorecard/extract`, {
      method: 'POST', body: form, credentials: 'include',
    }).then(async r => {
      const text = await r.text()
      let body
      try { body = JSON.parse(text) } catch { throw new Error(`Server error (${r.status}): ${text.slice(0, 200)}`) }
      if (!r.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `HTTP ${r.status}`)
      return body
    })
  },

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

  // Public marketing Contact form — store a club onboarding enquiry.
  submitOnboarding: (payload) =>
    request('/public/contact', { method: 'POST', body: JSON.stringify(payload) }),
  // Club lookup behind the Contact form's Club name field. Same Cricket
  // Australia club list the self-serve registration wizard searches, on the
  // Contact form's own endpoint so it works whether or not self-serve
  // registration is switched on.
  contactClubSearch: (q) =>
    request(`/public/contact/club-search?q=${encodeURIComponent(q)}`),

  // Super admin
  superOverview: () => request('/club-admin/super/overview'),
  superListOnboarding: () => request('/club-admin/super/onboarding-requests'),
  // Login-attempt audit log (super admin). opts: { limit, onlyFailures, q }
  superListLoginAttempts: (opts = {}) => {
    const p = new URLSearchParams()
    if (opts.limit) p.set('limit', opts.limit)
    if (opts.onlyFailures) p.set('only_failures', 'true')
    if (opts.q) p.set('q', opts.q)
    const qs = p.toString()
    return request(`/club-admin/super/login-attempts${qs ? `?${qs}` : ''}`)
  },
  superUpdateOnboarding: (id, status) =>
    request(`/club-admin/super/onboarding-requests/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) }),
  superDeleteOnboarding: (id) =>
    request(`/club-admin/super/onboarding-requests/${id}`, { method: 'DELETE' }),
  // Meta Ads HQ dashboard (super admin) — BetterCricket's own campaign spend.
  metaAdsSummary: () => request('/club-admin/meta-ads/summary'),
  metaAdsHistory: (days = 14) => request(`/club-admin/meta-ads/history?days=${days}`),
  metaAdsAdHistory: (adId, days = 30) => request(`/club-admin/meta-ads/ad-history/${adId}?days=${days}`),
  metaAdsRefresh: () => request('/club-admin/meta-ads/refresh', { method: 'POST' }),
  // Manual +/- correction to the Meta-reported lead count (indicative only).
  metaAdsAdjustLeads: (delta, note = '') =>
    request('/club-admin/meta-ads/leads/adjust', { method: 'POST', body: JSON.stringify({ delta, note }) }),
  metaAdsLeadAdjustments: () => request('/club-admin/meta-ads/leads/adjustments'),
  metaAdsAdSignups: () => request('/club-admin/meta-ads/ad-signups'),
  metaAdsRegistrationFunnel: (days = 30) => request(`/club-admin/meta-ads/registration-funnel?days=${days}`),
  // "Clubs selected"/"Clubs searched" are a follow-up/lead-management list,
  // not a funnel-stat window — default to a full year so a super admin sees
  // every past lead, not just the last 30 days (server caps at 730).
  metaAdsSelectedClubs: (days = 365) => request(`/club-admin/meta-ads/selected-clubs?days=${days}`),
  // Clubs typed into the search box (results loaded) but not necessarily
  // clicked — the interest before a selection. See searched-clubs endpoint.
  metaAdsSearchedClubs: (days = 365) => request(`/club-admin/meta-ads/searched-clubs?days=${days}`),
  metaAdsHideSelection: (name, days = 365) =>
    request(`/club-admin/meta-ads/selected-clubs/hide?days=${days}`, { method: 'POST', body: JSON.stringify({ name }) }),
  metaAdsUnhideSelection: (name, days = 365) =>
    request(`/club-admin/meta-ads/selected-clubs/unhide?days=${days}`, { method: 'POST', body: JSON.stringify({ name }) }),
  // Campaign picker — list the ad account's campaigns + which one the dashboard
  // is scoped to, and switch it (stored in the DB, no .env edit / redeploy).
  metaAdsCampaigns: () => request('/club-admin/meta-ads/campaigns'),
  metaAdsSetCampaign: (campaignId) =>
    request('/club-admin/meta-ads/campaign', { method: 'POST', body: JSON.stringify({ campaign_id: campaignId }) }),
  // "Counting since" cutoff — excludes data from before it out of the
  // on-site funnel/table numbers and Meta's own campaign insights (never the
  // "Free trial registrations" KPI, which always counts every real
  // completed registration). Pass null/omit `since` to clear it.
  metaAdsCountingSince: () => request('/club-admin/meta-ads/counting-since'),
  metaAdsSetCountingSince: (since) =>
    request('/club-admin/meta-ads/counting-since', { method: 'POST', body: JSON.stringify({ since }) }),
  // Re-scope the admin app to another club (super admin only). Pass null to
  // return to the staff member's home club. Returns the fresh /auth/me payload.
  switchClub: (clubId) =>
    request('/auth/switch-club', { method: 'POST', body: JSON.stringify({ club_id: clubId }) }),
  superListClubs: (includeArchived = false) =>
    request(`/club-admin/super/clubs${includeArchived ? '?include_archived=true' : ''}`),
  // CSV export: clubs with a module trial expiring within `days` (default 3),
  // club admin name/email with a Club Directory fallback baked in server-side.
  superExportTrialsEndingSoon: (days = 3) =>
    fetch(`${BASE}/club-admin/super/clubs/trials-ending-soon.csv?days=${days}`, { credentials: 'include' }),
  superGetGeneralSettings: () => request('/club-admin/super/general-settings'),
  superUpdateGeneralSettings: (data) =>
    request('/club-admin/super/general-settings', { method: 'PATCH', body: JSON.stringify(data) }),
  // Backup/restore task history + current DB size stats (super admin).
  superListBackupTasks: (params = {}) => {
    const q = new URLSearchParams(params).toString()
    return request(`/club-admin/super/backups${q ? `?${q}` : ''}`)
  },
  superBackupStats: () => request('/club-admin/super/backups/stats'),
  superRunBackupNow: () => request('/club-admin/super/backups/run', { method: 'POST' }),
  // Manual, on-demand download of a backup bundle file — still age-encrypted
  // in transit, same as it sits on disk (no offsite auto-sync anywhere).
  superDownloadBackupFile: (taskId, file) =>
    fetch(`${BASE}/club-admin/super/backups/${taskId}/download?file=${file}`, { credentials: 'include' }),
  // Restore is available both over SSH (ops/backup/restore.sh, unchanged) and
  // here — gated by a typed confirmation word plus the private key itself,
  // entered fresh every time and never stored (see backup_admin.py's module
  // docstring for the full safety model).
  superBackupRestoreFull: (taskId, confirmWord, privateKey) =>
    request(`/club-admin/super/backups/${taskId}/restore-full`, {
      method: 'POST', body: JSON.stringify({ confirm_word: confirmWord, private_key: privateKey }),
    }),
  superBackupRestoreClub: (taskId, orgId, confirmWord, privateKey) =>
    request(`/club-admin/super/backups/${taskId}/restore-club`, {
      method: 'POST', body: JSON.stringify({ org_id: orgId, confirm_word: confirmWord, private_key: privateKey }),
    }),
  // Self-serve club trial registration (internal, flag-gated — see
  // docs/self-serve-trial-onboarding-plan.md). 404s while the platform flag is off.
  selfServeTrialStatus: () => request('/self-serve-trial/status'),
  selfServeTrialSearch: (q) => request(`/self-serve-trial/search?q=${encodeURIComponent(q)}`),
  selfServeTrialPrepare: (data) =>
    request('/self-serve-trial/prepare', { method: 'POST', body: JSON.stringify(data) }),
  selfServeTrialValidateAdmin: (data) =>
    request('/self-serve-trial/validate-admin', { method: 'POST', body: JSON.stringify(data) }),
  selfServeTrialSendCode: (email) =>
    request('/self-serve-trial/verify-email/send', { method: 'POST', body: JSON.stringify({ email }) }),
  selfServeTrialCheckCode: (email, code) =>
    request('/self-serve-trial/verify-email/check', { method: 'POST', body: JSON.stringify({ email, code }) }),
  selfServeTrialVerificationStatus: (email) =>
    request(`/self-serve-trial/verify-email/status?email=${encodeURIComponent(email)}`),
  selfServeTrialAcknowledge: (data) =>
    request('/self-serve-trial/acknowledge', { method: 'POST', body: JSON.stringify(data) }),
  selfServeTrialSubmit: (data) =>
    request('/self-serve-trial/submit', { method: 'POST', body: JSON.stringify(data) }),
  selfServeTrialLoginAs: (userId) =>
    request(`/self-serve-trial/login-as/${userId}`, { method: 'POST' }),

  // Public self-serve trial registration (the /trial ad-campaign landing page)
  // — unauthenticated mirrors of the selfServeTrial* endpoints above, same
  // wizard, no super-admin session. 404s while the platform flag is off.
  publicSelfServeStatus: () => request('/public/self-serve/status'),
  publicSelfServeSearch: (q) => request(`/public/self-serve/search?q=${encodeURIComponent(q)}`),
  publicSelfServePrepare: (data) =>
    request('/public/self-serve/prepare', { method: 'POST', body: JSON.stringify(data) }),
  publicSelfServeValidateAdmin: (data) =>
    request('/public/self-serve/validate-admin', { method: 'POST', body: JSON.stringify(data) }),
  publicSelfServeSendCode: (email) =>
    request('/public/self-serve/verify-email/send', { method: 'POST', body: JSON.stringify({ email }) }),
  publicSelfServeCheckCode: (email, code) =>
    request('/public/self-serve/verify-email/check', { method: 'POST', body: JSON.stringify({ email, code }) }),
  publicSelfServeAcknowledge: (data) =>
    request('/public/self-serve/acknowledge', { method: 'POST', body: JSON.stringify(data) }),
  publicSelfServeSubmit: (data) =>
    request('/public/self-serve/submit', { method: 'POST', body: JSON.stringify(data) }),
  // Fire-and-forget step-transition beacon for the registration funnel
  // breakdown on the Meta Ads dashboard — callers should not await/block on
  // this (see trackFunnelStep in SelfServeTrialModal.jsx).
  publicSelfServeTrackStep: (step, visitorId, club = null) =>
    request('/public/self-serve/track-step', {
      method: 'POST',
      body: JSON.stringify({
        step,
        visitor_id: visitorId,
        // Sent with club_prepared (the picked club) and club_searched (the top
        // result a search returned) so a dropped-off visitor's club is
        // recoverable on the Meta Ads page. `query` is the raw text typed,
        // sent only with club_searched.
        club_name: club?.name || undefined,
        club_org_id: club?.org_id || undefined,
        query: club?.query || undefined,
      }),
    }),
  superCreateClub: (data) =>
    request('/club-admin/super/clubs', { method: 'POST', body: JSON.stringify(data) }),
  superPatchClub: (clubId, data) =>
    request(`/club-admin/super/clubs/${clubId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  superArchiveClub: (clubId) =>
    request(`/club-admin/super/clubs/${clubId}/archive`, { method: 'POST' }),
  superRestoreClub: (clubId) =>
    request(`/club-admin/super/clubs/${clubId}/restore`, { method: 'POST' }),
  // Club merger — fold a source club's synced history into a target club,
  // then archive the source (services/org_merge.py).
  superClubMergePreview: (sourceClubId, targetClubId) =>
    request(`/club-admin/super/clubs/${sourceClubId}/merge-preview?target_id=${targetClubId}`),
  superClubMerge: (sourceClubId, targetClubId) =>
    request(`/club-admin/super/clubs/${sourceClubId}/merge-into/${targetClubId}`, { method: 'POST' }),
  // Retroactive fix for a club merged before season/grade-stats repointing
  // was added to merge_organisation — repoints orphaned player_season_stats/
  // player_season_grade_stats rows left on the old predecessor's season/grade.
  superClubRepairMergeStats: (clubId) =>
    request(`/club-admin/super/clubs/${clubId}/repair-merge-stats`, { method: 'POST' }),
  // Pause Sync / Cancel Sync / Continue Sync for a club's current Full Sync
  // (migration 160) — All Clubs row actions.
  superClubSyncControl: (clubId, action) =>
    request(`/club-admin/super/clubs/${clubId}/sync-control`, { method: 'POST', body: JSON.stringify({ action }) }),
  // Per-module subscriptions (migration 118).
  superStartModuleTrial: (clubId, moduleKey, body = {}) =>
    request(`/club-admin/super/clubs/${clubId}/modules/${moduleKey}/trial`, { method: 'POST', body: JSON.stringify(body) }),
  superPatchModule: (clubId, moduleKey, data) =>
    request(`/club-admin/super/clubs/${clubId}/modules/${moduleKey}`, { method: 'PATCH', body: JSON.stringify(data) }),
  superRemoveModule: (clubId, moduleKey) =>
    request(`/club-admin/super/clubs/${clubId}/modules/${moduleKey}`, { method: 'DELETE' }),
  // Primary / owner admin (migration 118).
  superListClubAdmins: (clubId) => request(`/club-admin/super/clubs/${clubId}/admins`),
  superSetPrimaryAdmin: (clubId, userId) =>
    request(`/club-admin/super/clubs/${clubId}/primary-admin`, { method: 'PUT', body: JSON.stringify({ user_id: userId }) }),
  getPrimaryAdmin: () => request('/club-admin/primary-admin'),
  transferPrimaryAdmin: (userId) =>
    request('/club-admin/primary-admin/transfer', { method: 'POST', body: JSON.stringify({ user_id: userId }) }),
  // Account / plan status page (Phase 19) — per-module Subscribed / In Trial /
  // Trial Expired / Never Trialed status plus trial/subscribe eligibility.
  accountGetPlan: () => request('/club-admin/account/plan'),
  // Per-account UI preferences (namespaced JSON). getUiPrefs -> { prefs }.
  // setUiPrefs shallow-merges by namespace (send { ns: value }, or { ns: null }
  // to clear). Persists across sessions/devices, unlike localStorage.
  getUiPrefs: () => request('/club-admin/account/ui-prefs'),
  setUiPrefs: (prefs) => request('/club-admin/account/ui-prefs', { method: 'PATCH', body: JSON.stringify({ prefs }) }),
  // Self-service instant trial start / cancel (Dashboard "START TRIAL" and the
  // Account page's per-row actions) — bypass the module-requests queue entirely.
  startModuleTrial: (moduleKey) =>
    request(`/club-admin/modules/${moduleKey}/start-trial`, { method: 'POST' }),
  cancelModule: (moduleKey, confirmText) =>
    request(`/club-admin/modules/${moduleKey}/cancel`, { method: 'POST', body: JSON.stringify({ confirm: confirmText }) }),
  // Module action requests — the trial/subscription queue (migration 119).
  requestModule: (moduleKey, kind = 'trial', note) =>
    request('/club-admin/module-requests', { method: 'POST', body: JSON.stringify({ module_key: moduleKey, kind, note }) }),
  // Stripe Checkout billing (migration 150) — flag-gated, see
  // platform_settings.billing_checkout_enabled. billingQuote is pure price
  // math (no Stripe call); billingCreateCheckoutSession creates a real
  // Checkout Session and returns its redirect URL. couponCode (migration 154)
  // is optional on both — a discount-coupon redeemed alongside a fresh
  // subscribe, see services/discount_coupons.py.
  billingQuote: (moduleKeys, couponCode) =>
    request('/club-admin/billing/quote', {
      method: 'POST',
      body: JSON.stringify({ module_keys: moduleKeys, coupon_code: couponCode || undefined }),
    }),
  billingCreateCheckoutSession: (moduleKeys, couponCode) =>
    request('/club-admin/billing/checkout-session', {
      method: 'POST',
      body: JSON.stringify({ module_keys: moduleKeys, coupon_code: couponCode || undefined }),
    }),
  billingListInvoices: () => request('/club-admin/billing/invoices'),
  // Payment method management — routers/billing.py. Primary-admin self-serve
  // (current club) and Super Admin (any club by org_id) share the same
  // response shape ({default_payment_method_id, payment_methods}).
  billingListPaymentMethods: () => request('/club-admin/billing/payment-methods'),
  billingCreatePaymentMethodSetupSession: () =>
    request('/club-admin/billing/payment-methods/setup-session', { method: 'POST' }),
  billingSetDefaultPaymentMethod: (pmId) =>
    request(`/club-admin/billing/payment-methods/${pmId}/default`, { method: 'POST' }),
  billingRemovePaymentMethod: (pmId) =>
    request(`/club-admin/billing/payment-methods/${pmId}`, { method: 'DELETE' }),
  superListPaymentMethods: (orgId) =>
    request(`/club-admin/billing/super/clubs/${orgId}/payment-methods`),
  superCreatePaymentMethodSetupSession: (orgId) =>
    request(`/club-admin/billing/super/clubs/${orgId}/payment-methods/setup-session`, { method: 'POST' }),
  superSetDefaultPaymentMethod: (orgId, pmId) =>
    request(`/club-admin/billing/super/clubs/${orgId}/payment-methods/${pmId}/default`, { method: 'POST' }),
  superRemovePaymentMethod: (orgId, pmId) =>
    request(`/club-admin/billing/super/clubs/${orgId}/payment-methods/${pmId}`, { method: 'DELETE' }),
  // Super-Admin-only rollup of every discount actually paid out, sourced from
  // billing_invoices — see routers/billing.py::discount_report.
  superDiscountReport: (dateFrom, dateTo) => {
    const params = new URLSearchParams()
    if (dateFrom) params.set('date_from', dateFrom)
    if (dateTo) params.set('date_to', dateTo)
    const qs = params.toString()
    return request(`/club-admin/billing/discount-report${qs ? `?${qs}` : ''}`)
  },
  // Setup Wizard analytics (super-admin) — routers/wizard_analytics.py.
  superWizardAnalytics: () => request('/club-admin/super/wizard-analytics'),
  // BetterCricket-managed discount coupons (migration 154) —
  // routers/discount_coupons.py. couponRedeem is the club-facing "apply a
  // code to my already-live subscription ahead of renewal" action; the rest
  // are Super-Admin catalogue CRUD.
  couponRedeem: (code) =>
    request('/club-admin/coupons/redeem', { method: 'POST', body: JSON.stringify({ code }) }),
  superListCoupons: () => request('/club-admin/coupons'),
  superCreateCoupon: (data) =>
    request('/club-admin/coupons', { method: 'POST', body: JSON.stringify(data) }),
  superUpdateCoupon: (couponId, data) =>
    request(`/club-admin/coupons/${couponId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  superDeactivateCoupon: (couponId) =>
    request(`/club-admin/coupons/${couponId}/deactivate`, { method: 'POST' }),
  superCouponRedemptions: (couponId) => request(`/club-admin/coupons/${couponId}/redemptions`),
  superRevokeCouponRedemption: (couponId, redemptionId) =>
    request(`/club-admin/coupons/${couponId}/revoke/${redemptionId}`, { method: 'POST' }),
  superForceApplyCoupon: (organisationId, code) =>
    request('/club-admin/coupons/force-apply', {
      method: 'POST',
      body: JSON.stringify({ organisation_id: organisationId, code }),
    }),
  listMyModuleRequests: () => request('/club-admin/module-requests'),
  superListModuleRequests: (status) =>
    request(`/club-admin/super/module-requests${status ? `?status=${encodeURIComponent(status)}` : ''}`),
  superCountModuleRequests: () => request('/club-admin/super/module-requests/count'),
  superApproveModuleRequest: (id, body = {}) =>
    request(`/club-admin/super/module-requests/${id}/approve`, { method: 'POST', body: JSON.stringify(body) }),
  superDismissModuleRequest: (id) =>
    request(`/club-admin/super/module-requests/${id}/dismiss`, { method: 'POST' }),
  // BetterComms sending tiers (migration 125). Club-facing:
  commsGetLimits: () => request('/club-admin/comms/limits'),
  commsRequestLimit: (body = {}) =>
    request('/club-admin/comms/limits/request', { method: 'POST', body: JSON.stringify(body) }),
  // Super-admin tier-request queue + suspensions.
  superListCommsRequests: (status) =>
    request(`/club-admin/super/comms/requests${status ? `?status=${encodeURIComponent(status)}` : ''}`),
  superCountCommsRequests: () => request('/club-admin/super/comms/requests/count'),
  superApproveCommsRequest: (id, body = {}) =>
    request(`/club-admin/super/comms/requests/${id}/approve`, { method: 'POST', body: JSON.stringify(body) }),
  superDenyCommsRequest: (id, body = {}) =>
    request(`/club-admin/super/comms/requests/${id}/deny`, { method: 'POST', body: JSON.stringify(body) }),
  superReinstateComms: (clubId, body = {}) =>
    request(`/club-admin/super/clubs/${clubId}/comms/reinstate`, { method: 'POST', body: JSON.stringify(body) }),
  // Account send rate (AWS ceiling + our pacing rate), super-admin managed.
  superGetCommsRates: () => request('/club-admin/super/comms/rates'),
  superUpdateCommsRates: (body = {}) =>
    request('/club-admin/super/comms/rates', { method: 'PATCH', body: JSON.stringify(body) }),
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
  forceImportAchievements: (orgId, rows, { batchId = null, filename = null } = {}) =>
    request(`/achievements/import/force?org_id=${orgId}`, {
      method: 'POST',
      body: JSON.stringify({ rows, batch_id: batchId, filename }),
    }),
  linkAchievementPlayers: (orgId, links, batchId = null) =>
    request(`/achievements/link?org_id=${orgId}`, {
      method: 'POST',
      body: JSON.stringify({ links, batch_id: batchId }),
    }),
  listAchievementImports: (orgId) =>
    request(`/achievements/imports?org_id=${orgId}`),
  undoAchievementImport: (orgId, batchId) =>
    request(`/achievements/imports/${batchId}/undo?org_id=${orgId}`, { method: 'POST' }),
  parseAchievementsPdf: (orgId, file) => {
    const form = new FormData()
    form.append('file', file)
    return fetch(`${BASE}/achievements/parse-pdf?org_id=${orgId}`, {
      method: 'POST',
      body: form,
      credentials: 'include',
    }).then(async r => {
      const data = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(data.detail || 'Could not read the PDF')
      return data
    })
  },
  parseAchievementsUrl: (orgId, url) =>
    request(`/achievements/parse-url?org_id=${orgId}`, {
      method: 'POST',
      body: JSON.stringify({ url }),
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

  // ─── Club Room Mode ────────────────────────────────────────────────────────
  clubRoomGetSettings: () => request('/club-admin/club-room/settings'),
  clubRoomPatchSettings: (data) =>
    request('/club-admin/club-room/settings', { method: 'PATCH', body: JSON.stringify(data) }),
  clubRoomCreateSlide: (data) =>
    request('/club-admin/club-room/slides', { method: 'POST', body: JSON.stringify(data) }),
  clubRoomPatchSlide: (id, data) =>
    request(`/club-admin/club-room/slides/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  clubRoomDeleteSlide: (id) =>
    request(`/club-admin/club-room/slides/${id}`, { method: 'DELETE' }),
  clubRoomReorderSlides: (items) =>
    request('/club-admin/club-room/slides/reorder', { method: 'PUT', body: JSON.stringify(items) }),
  clubRoomListMedia: (source) =>
    request(`/club-admin/club-room/media${source ? `?source=${source}` : ''}`),
  clubRoomUploadMedia: (file, caption) => {
    const form = new FormData()
    form.append('file', file)
    if (caption) form.append('caption', caption)
    return fetch(`${BASE}/club-admin/club-room/media`, { method: 'POST', body: form, credentials: 'include' })
      .then(async r => {
        if (!r.ok) {
          const e = await r.json().catch(() => ({}))
          throw new Error(typeof e.detail === 'string' ? e.detail : `HTTP ${r.status}`)
        }
        return r.json()
      })
  },
  clubRoomSaveSocialExport: (blob, caption) => {
    const form = new FormData()
    form.append('file', blob, 'post.png')
    if (caption) form.append('caption', caption)
    return fetch(`${BASE}/club-admin/club-room/media/social-export`, { method: 'POST', body: form, credentials: 'include' })
      .then(async r => {
        if (!r.ok) {
          const e = await r.json().catch(() => ({}))
          throw new Error(typeof e.detail === 'string' ? e.detail : `HTTP ${r.status}`)
        }
        return r.json()
      })
  },
  clubRoomDeleteMedia: (id) =>
    request(`/club-admin/club-room/media/${id}`, { method: 'DELETE' }),
  clubRoomListReports: () => request('/club-admin/club-room/reports'),
  clubRoomPlay: () => request('/club-admin/club-room/play'),
  clubRoomGetPublicLink: () => request('/club-admin/club-room/public-link'),
  clubRoomSetPublicLink: (data) =>
    request('/club-admin/club-room/public-link', { method: 'POST', body: JSON.stringify(data) }),
  clubRoomRegeneratePublicLink: () =>
    request('/club-admin/club-room/public-link/regenerate', { method: 'POST' }),

  // Club Room Mode — public link (unauthenticated)
  publicClubRoomLanding: (token) => request(`/public/club-room/${token}`),
  publicClubRoomVerify: (token, pin) =>
    request(`/public/club-room/${token}/verify`, { method: 'POST', body: JSON.stringify({ pin }) }),
  publicClubRoomPlay: (token) => request(`/public/club-room/${token}/play`),

  // ─── Front-end Website (public) ───────────────────────────────────────────
  webGetSite: (slug) => request(`/clubs/${slug}/website`),
  webListNews: (slug, { limit = 24, offset = 0 } = {}) =>
    request(`/clubs/${slug}/website/news?limit=${limit}&offset=${offset}`),
  webGetArticle: (slug, newsSlug) => request(`/clubs/${slug}/website/news/${newsSlug}`),
  webGetPage: (slug, pageSlug) => request(`/clubs/${slug}/website/pages/${pageSlug}`),
  webGetHonours: (slug) => request(`/clubs/${slug}/website/honours`),
  webGetCommittee: (slug) => request(`/clubs/${slug}/website/committee`),
  webGetGallery: (slug) => request(`/clubs/${slug}/website/gallery`),
  webGetAlbum: (slug, albumId) => request(`/clubs/${slug}/website/gallery/${albumId}`),

  // ─── Front-end Website (admin) ────────────────────────────────────────────
  webAdminSettings: () => request('/club-admin/website/settings'),
  webAdminSaveSettings: (data) =>
    request('/club-admin/website/settings', { method: 'PUT', body: JSON.stringify(data) }),
  webAdminUploadHero: (file) => uploadFile('/club-admin/website/hero', file),
  webAdminDeleteHero: () => request('/club-admin/website/hero', { method: 'DELETE' }),
  // News
  webAdminListNews: () => request('/club-admin/website/news'),
  webAdminGetNews: (id) => request(`/club-admin/website/news/${id}`),
  webAdminCreateNews: (data) =>
    request('/club-admin/website/news', { method: 'POST', body: JSON.stringify(data) }),
  webAdminUpdateNews: (id, data) =>
    request(`/club-admin/website/news/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  webAdminDeleteNews: (id) => request(`/club-admin/website/news/${id}`, { method: 'DELETE' }),
  webAdminUploadNewsCover: (id, file) => uploadFile(`/club-admin/website/news/${id}/cover`, file),
  webAdminDeleteNewsCover: (id) =>
    request(`/club-admin/website/news/${id}/cover`, { method: 'DELETE' }),
  // Pages
  webAdminListPages: () => request('/club-admin/website/pages'),
  webAdminCreatePage: (data) =>
    request('/club-admin/website/pages', { method: 'POST', body: JSON.stringify(data) }),
  webAdminUpdatePage: (id, data) =>
    request(`/club-admin/website/pages/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  webAdminDeletePage: (id) => request(`/club-admin/website/pages/${id}`, { method: 'DELETE' }),
  webAdminReorderPages: (ids) =>
    request('/club-admin/website/pages/reorder', { method: 'POST', body: JSON.stringify({ ids }) }),
  // Honours
  webAdminListHonours: () => request('/club-admin/website/honours'),
  webAdminHonourCategories: () => request('/club-admin/website/honour-categories'),
  webAdminCreateBoard: (data) =>
    request('/club-admin/website/honours/boards', { method: 'POST', body: JSON.stringify(data) }),
  webAdminUpdateBoard: (id, data) =>
    request(`/club-admin/website/honours/boards/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  webAdminDeleteBoard: (id) =>
    request(`/club-admin/website/honours/boards/${id}`, { method: 'DELETE' }),
  webAdminCreateEntry: (boardId, data) =>
    request(`/club-admin/website/honours/boards/${boardId}/entries`, { method: 'POST', body: JSON.stringify(data) }),
  webAdminUpdateEntry: (id, data) =>
    request(`/club-admin/website/honours/entries/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  webAdminDeleteEntry: (id) =>
    request(`/club-admin/website/honours/entries/${id}`, { method: 'DELETE' }),
  // Committee
  webAdminCommitteeConfig: () => request('/club-admin/website/committee-config'),
  webAdminSaveCommitteeConfig: (data) =>
    request('/club-admin/website/committee-config', { method: 'PUT', body: JSON.stringify(data) }),
  webAdminListCommittee: () => request('/club-admin/website/committee'),
  webAdminCreateCommittee: (data) =>
    request('/club-admin/website/committee', { method: 'POST', body: JSON.stringify(data) }),
  webAdminUpdateCommittee: (id, data) =>
    request(`/club-admin/website/committee/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  webAdminDeleteCommittee: (id) =>
    request(`/club-admin/website/committee/${id}`, { method: 'DELETE' }),
  webAdminUploadCommitteePhoto: (id, file) =>
    uploadFile(`/club-admin/website/committee/${id}/photo`, file),
  webAdminDeleteCommitteePhoto: (id) =>
    request(`/club-admin/website/committee/${id}/photo`, { method: 'DELETE' }),
  // Gallery
  webAdminListGallery: () => request('/club-admin/website/gallery'),
  webAdminCreateAlbum: (data) =>
    request('/club-admin/website/gallery/albums', { method: 'POST', body: JSON.stringify(data) }),
  webAdminUpdateAlbum: (id, data) =>
    request(`/club-admin/website/gallery/albums/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  webAdminDeleteAlbum: (id) =>
    request(`/club-admin/website/gallery/albums/${id}`, { method: 'DELETE' }),
  webAdminAddGalleryImage: (albumId, file) =>
    uploadFile(`/club-admin/website/gallery/albums/${albumId}/images`, file),
  webAdminUpdateGalleryImage: (id, data) =>
    request(`/club-admin/website/gallery/images/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  webAdminDeleteGalleryImage: (id) =>
    request(`/club-admin/website/gallery/images/${id}`, { method: 'DELETE' }),

  // Records
  getRecords: (orgId, { seasonId, gradeId, gradeName, finalsOnly, captainOnly, gender, categories } = {}) => {
    const params = new URLSearchParams()
    if (seasonId) params.set('season_id', seasonId)
    if (gradeId) params.set('grade_id', gradeId)
    if (gradeName) params.set('grade_name', gradeName)
    if (finalsOnly) params.set('finals_only', 'true')
    if (captainOnly) params.set('captain_only', 'true')
    if (gender) params.set('gender', gender)
    if (categories) params.set('categories', categories)
    return request(`/records/${orgId}?${params}`)
  },
  getRecordsGrades: (orgId, seasonId) => {
    const params = new URLSearchParams()
    if (seasonId) params.set('season_id', seasonId)
    return request(`/records/${orgId}/grades?${params}`)
  },
  getRecordsMilestones: (orgId, gradeName) => {
    const params = new URLSearchParams()
    if (gradeName) params.set('grade_name', gradeName)
    return request(`/records/${orgId}/milestones?${params}`)
  },

  // Leaderboard
  battingLeaderboard: (orgId, { seasonId, gradeId, gradeName, sortBy, limit, minRuns, finalsOnly, captainOnly, gender, overseas, categories } = {}) => {
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
    if (categories) params.set('categories', categories)
    return request(`/leaderboard/batting?${params}`)
  },
  bowlingLeaderboard: (orgId, { seasonId, gradeId, gradeName, sortBy, limit, minOvers, minWickets, finalsOnly, captainOnly, gender, overseas, categories } = {}) => {
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
    if (categories) params.set('categories', categories)
    return request(`/leaderboard/bowling?${params}`)
  },
  fieldingLeaderboard: (orgId, { seasonId, gradeId, gradeName, sortBy, limit, finalsOnly, captainOnly, gender, overseas, categories } = {}) => {
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
    if (categories) params.set('categories', categories)
    return request(`/leaderboard/fielding?${params}`)
  },
  sirsLeaderboard: (orgId, type, { seasonId, gradeName, finalsOnly, captainOnly, limit, gender, overseas, categories } = {}) => {
    const params = new URLSearchParams({ org_id: orgId })
    if (seasonId) params.set('season_id', seasonId)
    if (gradeName) params.set('grade_name', gradeName)
    if (finalsOnly) params.set('finals_only', 'true')
    if (captainOnly) params.set('captain_only', 'true')
    if (limit) params.set('limit', limit)
    if (gender) params.set('gender', gender)
    if (overseas) params.set('overseas', overseas)
    if (categories) params.set('categories', categories)
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
  bsTeamGradeOptions: () => request('/teams/grade-options'),
  bsTeamLadders: () => request('/ladders/teams'),
  laddersPublic: (slug) => request(`/ladders/public/${slug}`),
  laddersGrade: (gradeId) => request(`/ladders/grade/${gradeId}`),
  bsCreateTeam: (data) =>
    request('/teams', { method: 'POST', body: JSON.stringify(data) }),
  bsUpdateTeam: (id, data) =>
    request(`/teams/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  bsDeleteTeam: (id) => request(`/teams/${id}`, { method: 'DELETE' }),
  bsSeedTeams: (body) => request('/teams/seed', { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  bsSeedCandidates: ({ seasons = 3 } = {}) => request(`/teams/seed-candidates?seasons=${seasons}`),
  bsResequenceTeams: () => request('/teams/resequence', { method: 'POST' }),
  bsAutoAssignSuggest: ({ seasons = 2, onlyUnassigned = true } = {}) =>
    request(`/teams/auto-assign-suggest?seasons=${seasons}&only_unassigned=${onlyUnassigned}`),
  bsTeamMembers: (id) => request(`/teams/${id}/members`),
  bsAddTeamMember: (id, playerId) =>
    request(`/teams/${id}/members`, { method: 'POST', body: JSON.stringify({ player_id: playerId }) }),
  bsRemoveTeamMember: (id, playerId) =>
    request(`/teams/${id}/members/${playerId}`, { method: 'DELETE' }),
  // Assign one or many players to a single selection-pool squad (or null to
  // unassign). Powers the Squads board's drag-to-reassign and bulk-add.
  bsAssignSquad: (playerIds, squadTeamId) =>
    request('/teams/squad-assign', { method: 'POST', body: JSON.stringify({ player_ids: playerIds, squad_team_id: squadTeamId ?? null }) }),

  // ─── BetterSelect: Availability ─────────────────────────
  bsAvailabilityMatrix: () => request('/availability/matrix'),
  bsSetAvailability: (data) =>
    request('/availability', { method: 'POST', body: JSON.stringify(data) }),
  bsBulkAvailability: (items) =>
    request('/availability/bulk', { method: 'POST', body: JSON.stringify({ items }) }),
  bsAvailabilityPeriods: (includePast = false) =>
    request(`/availability/periods${includePast ? '?include_past=true' : ''}`),
  bsCreateAvailabilityPeriod: (data) =>
    request('/availability/periods', { method: 'POST', body: JSON.stringify(data) }),
  bsDeleteAvailabilityPeriod: (id) =>
    request(`/availability/periods/${id}`, { method: 'DELETE' }),

  // ─── BetterSelect: self-service availability link (admin) ───
  bsGetSelfService: () => request('/availability/self-service'),
  bsSetSelfService: (data) =>
    request('/availability/self-service', { method: 'POST', body: JSON.stringify(data) }),
  bsRegenerateSelfService: () =>
    request('/availability/self-service/regenerate', { method: 'POST' }),

  // ─── Public: self-service availability (no admin auth; player cookie) ───
  // Outside the admin surface — players reach these via the magic link + PIN.
  availPublicLanding: (token) => request(`/public/availability/${token}`),
  availPublicVerify: (token, player_id, pin) =>
    request(`/public/availability/${token}/verify`, { method: 'POST', body: JSON.stringify({ player_id, pin }) }),
  availPublicSwitch: (token) =>
    request(`/public/availability/${token}/switch`, { method: 'POST' }),
  availPublicMe: (token) => request(`/public/availability/${token}/me`),
  availPublicSet: (token, data) =>
    request(`/public/availability/${token}/me`, { method: 'POST', body: JSON.stringify(data) }),

  // ─── BetterSelect: vote collection (admin) ───
  votesGetSettings: () => request('/votes/settings'),
  votesSetSettings: (data) =>
    request('/votes/settings', { method: 'POST', body: JSON.stringify(data) }),
  votesRegenerateLink: () => request('/votes/settings/regenerate', { method: 'POST' }),
  votesFixtures: ({ year, grade_id, round_key, q } = {}) => {
    const params = new URLSearchParams()
    if (year) params.set('year', year)
    if (grade_id) params.set('grade_id', grade_id)
    if (round_key) params.set('round_key', round_key)
    if (q) params.set('q', q)
    const qs = params.toString()
    return request(`/votes/fixtures${qs ? `?${qs}` : ''}`)
  },
  votesFixtureDetail: (fixtureId) => request(`/votes/fixtures/${fixtureId}`),
  votesAdminBallot: (fixtureId, data) =>
    request(`/votes/fixtures/${fixtureId}/ballots`, { method: 'POST', body: JSON.stringify(data) }),
  votesDeleteBallot: (ballotId) => request(`/votes/ballots/${ballotId}`, { method: 'DELETE' }),
  votesSetFixtureSource: (fixtureId, eligibility_source) =>
    request(`/votes/fixtures/${fixtureId}/source`, { method: 'POST', body: JSON.stringify({ eligibility_source }) }),
  votesLockFixture: (fixtureId) => request(`/votes/fixtures/${fixtureId}/lock`, { method: 'POST' }),
  votesReopenFixture: (fixtureId) => request(`/votes/fixtures/${fixtureId}/reopen`, { method: 'POST' }),
  votesLeaderboard: ({ year, grade_id, through_round } = {}) => {
    const q = new URLSearchParams()
    if (year) q.set('year', year)
    if (grade_id) q.set('grade_id', grade_id)
    if (through_round) q.set('through_round', through_round)
    const qs = q.toString()
    return request(`/votes/leaderboard${qs ? `?${qs}` : ''}`)
  },
  votesBulkState: ({ fixture_ids, action }) =>
    request('/votes/bulk-state', { method: 'POST', body: JSON.stringify({ fixture_ids, action }) }),
  votesNudge: (fixtureId, body) =>
    request('/votes/nudge', {
      method: 'POST',
      body: JSON.stringify(fixtureId ? { fixture_id: fixtureId, ...body } : body),
    }),

  // ─── Public: vote collection (no admin auth; player cookie or typed name) ───
  votePublicLanding: (token, { team, round_key, q } = {}) => {
    const params = new URLSearchParams()
    if (team) params.set('team', team)
    if (round_key) params.set('round_key', round_key)
    if (q) params.set('q', q)
    const qs = params.toString()
    return request(`/public/votes/${token}${qs ? `?${qs}` : ''}`)
  },
  votePublicVerify: (token, player_id, pin) =>
    request(`/public/votes/${token}/verify`, { method: 'POST', body: JSON.stringify({ player_id, pin }) }),
  votePublicSwitch: (token) =>
    request(`/public/votes/${token}/switch`, { method: 'POST' }),
  votePublicFixture: (token, fixtureId) => request(`/public/votes/${token}/fixtures/${fixtureId}`),
  votePublicSubmit: (token, fixtureId, data) =>
    request(`/public/votes/${token}/fixtures/${fixtureId}/ballot`, { method: 'POST', body: JSON.stringify(data) }),

  // ─── BetterFantasyCricket: public member play ───────────
  fanLanding: (token) => request(`/public/fantasy/${token}`),
  fanRegister: (token, data) => request(`/public/fantasy/${token}/register`, { method: 'POST', body: JSON.stringify(data) }),
  fanLogin: (token, data) => request(`/public/fantasy/${token}/login`, { method: 'POST', body: JSON.stringify(data) }),
  fanLogout: (token) => request(`/public/fantasy/${token}/logout`, { method: 'POST' }),
  fanPool: (token) => request(`/public/fantasy/${token}/pool`),
  fanMe: (token) => request(`/public/fantasy/${token}/me`),
  fanRound: (token, n) => request(`/public/fantasy/${token}/round${n != null ? `?n=${n}` : ''}`),
  fanSaveSquad: (token, data) => request(`/public/fantasy/${token}/squad`, { method: 'POST', body: JSON.stringify(data) }),
  fanTransfer: (token, out_player_id, in_player_id) =>
    request(`/public/fantasy/${token}/transfer`, { method: 'POST', body: JSON.stringify({ out_player_id, in_player_id }) }),
  fanSetCaptain: (token, captain_player_id, vice_player_id) =>
    request(`/public/fantasy/${token}/captain`, { method: 'POST', body: JSON.stringify({ captain_player_id, vice_player_id }) }),
  fanChip: (token, chip) => request(`/public/fantasy/${token}/chip`, { method: 'POST', body: JSON.stringify({ chip }) }),
  fanCancelChip: (token, chip) => request(`/public/fantasy/${token}/chip/cancel`, { method: 'POST', body: JSON.stringify({ chip }) }),
  fanLadder: (token) => request(`/public/fantasy/${token}/ladder`),
  fanLeagues: (token) => request(`/public/fantasy/${token}/leagues`),
  fanLeague: (token, leagueId) => request(`/public/fantasy/${token}/leagues/${leagueId}`),
  fanLeaveLeague: (token, leagueId) => request(`/public/fantasy/${token}/leagues/${leagueId}/leave`, { method: 'POST' }),
  fanCreateLeague: (token, name) => request(`/public/fantasy/${token}/leagues`, { method: 'POST', body: JSON.stringify({ name }) }),
  fanJoinLeague: (token, code) => request(`/public/fantasy/${token}/leagues/join`, { method: 'POST', body: JSON.stringify({ code }) }),
  fanH2H: (token, leagueId, { round, opponent_squad_id } = {}) => {
    const qs = new URLSearchParams()
    if (round != null) qs.set('round', round)
    if (opponent_squad_id) qs.set('opponent_squad_id', opponent_squad_id)
    const q = qs.toString()
    return request(`/public/fantasy/${token}/h2h/${leagueId}${q ? `?${q}` : ''}`)
  },
  fanRounds: (token) => request(`/public/fantasy/${token}/rounds`),
  fanLive: (token) => request(`/public/fantasy/${token}/live`),
  fanPlayer: (token, playerId) => request(`/public/fantasy/${token}/player/${playerId}`),
  fanNotifications: (token) => request(`/public/fantasy/${token}/notifications`),
  fanUpdateProfile: (token, data) => request(`/public/fantasy/${token}/profile`, { method: 'POST', body: JSON.stringify(data) }),
  fanDraftLeagues: (token) => request(`/public/fantasy/${token}/draft-leagues`),
  fanJoinDraft: (token, leagueId) => request(`/public/fantasy/${token}/draft-leagues/${leagueId}/join`, { method: 'POST' }),
  fanDraftState: (token, leagueId) => request(`/public/fantasy/${token}/draft/${leagueId}`),
  fanDraftPick: (token, leagueId, player_id) =>
    request(`/public/fantasy/${token}/draft/${leagueId}/pick`, { method: 'POST', body: JSON.stringify({ player_id }) }),
  fanDraftNominate: (token, leagueId, player_id, opening_bid) =>
    request(`/public/fantasy/${token}/draft/${leagueId}/nominate`, { method: 'POST', body: JSON.stringify({ player_id, opening_bid }) }),
  fanDraftBid: (token, leagueId, amount) =>
    request(`/public/fantasy/${token}/draft/${leagueId}/bid`, { method: 'POST', body: JSON.stringify({ amount }) }),
  fanDraftWishlist: (token, leagueId, player_ids) =>
    request(`/public/fantasy/${token}/draft/${leagueId}/wishlist`, { method: 'PUT', body: JSON.stringify({ player_ids }) }),
  fanDraftLadder: (token, leagueId) => request(`/public/fantasy/${token}/draft/${leagueId}/ladder`),
  fanDraftWaiver: (token, leagueId, add_player_id, drop_player_id) =>
    request(`/public/fantasy/${token}/draft/${leagueId}/waiver`, { method: 'POST', body: JSON.stringify({ add_player_id, drop_player_id }) }),
  fanDraftManage: (token, leagueId) => request(`/public/fantasy/${token}/draft/${leagueId}/manage`),
  fanDraftTrade: (token, leagueId, receiver_squad_id, give, get) =>
    request(`/public/fantasy/${token}/draft/${leagueId}/trade`, { method: 'POST', body: JSON.stringify({ receiver_squad_id, give, get }) }),
  fanRespondTrade: (token, tradeId, accept) =>
    request(`/public/fantasy/${token}/trades/${tradeId}/respond`, { method: 'POST', body: JSON.stringify({ accept }) }),

  // ─── BetterSelect: Selection (lineups) ──────────────────
  bsSelectionOverview: () => request('/selection/overview'),
  bsGetSelection: (fixtureId) => request(`/selection/${fixtureId}`),
  bsSetSelection: (fixtureId, players, demotions = []) =>
    request(`/selection/${fixtureId}`, { method: 'PUT', body: JSON.stringify({ players, demotions }) }),
  bsSetDefaultTeamSize: (size) =>
    request('/selection/default-team-size', { method: 'POST', body: JSON.stringify({ size }) }),
  // The previous fixture's named XI (for Selection's "fill from last week").
  bsPreviousXI: (fixtureId) => request(`/selection/${fixtureId}/previous-xi`),
  // Player ids named in any saved XI for the round containing `on` (a date) —
  // powers the cross-screen "Selected" filter.
  bsSelectedPlayers: (on) => request(`/selection/selected-players?on=${encodeURIComponent(on)}`),

  // ─── BetterSelect: Net Manager ──────────────────────────
  // Active roster to check players in from (same pool as availability).
  nmRoster: () => request('/nets/roster'),
  // Club default timer/rotation settings.
  nmGetSettings: () => request('/nets/settings'),
  nmSetSettings: (data) =>
    request('/nets/settings', { method: 'PUT', body: JSON.stringify(data) }),
  // Sessions (training days).
  nmListSessions: (limit = 40) => request(`/nets/sessions?limit=${limit}`),
  nmCreateSession: (data = {}) =>
    request('/nets/sessions', { method: 'POST', body: JSON.stringify(data) }),
  nmGetSession: (id) => request(`/nets/sessions/${id}`),
  nmUpdateSession: (id, data) =>
    request(`/nets/sessions/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  nmDeleteSession: (id) => request(`/nets/sessions/${id}`, { method: 'DELETE' }),
  // Replace a session's attendance snapshot (checked-in players + guests, who batted).
  nmSetAttendance: (id, attendees) =>
    request(`/nets/sessions/${id}/attendance`, { method: 'PUT', body: JSON.stringify({ attendees }) }),
  // Reports.
  nmAttendanceReport: (days = 120) => request(`/nets/reports/attendance?days=${days}`),
  nmPlayerAttendance: (playerId) => request(`/nets/players/${playerId}/attendance`),

  // ─── BetterSelect: Player profile ───────────────────────
  bsGetPlayerProfile: (id) => request(`/players/${id}/profile`),
  bsUpdatePlayerProfile: (id, data) =>
    request(`/players/${id}/profile`, { method: 'PATCH', body: JSON.stringify(data) }),

  // Former/alternate names — so a live feed (Play.Cricket, a Grassroots
  // scorecard) using an old name still resolves to this player.
  playerAliases: (id) => request(`/players/${id}/aliases`),
  addPlayerAlias: (id, alias_name) =>
    request(`/players/${id}/aliases`, { method: 'POST', body: JSON.stringify({ alias_name }) }),
  deletePlayerAlias: (id, aliasId) =>
    request(`/players/${id}/aliases/${aliasId}`, { method: 'DELETE' }),

  // ─── BetterIQ: Opposition analysis ──────────────────────
  // Opponents we have history against + upcoming fixtures to scout.
  iqListOpponents: () => request('/iq/opposition/opponents'),
  // Instant report from data we already hold (head-to-head, our record vs them).
  // `grade` (a grade name) and `seasonIds` (array of season ids) scope the
  // historical sections to match the record card's All-time/Season/Grade toggle.
  iqOppositionReport: ({ opponent, fixtureId, grade, seasonIds, name } = {}) => {
    const qs = _iqQs(opponent, fixtureId, null, name)
    const extra = new URLSearchParams()
    if (grade) extra.set('grade', grade)
    if (seasonIds && seasonIds.length) extra.set('season_ids', seasonIds.join(','))
    const tail = extra.toString()
    return request(`/iq/opposition/report?${qs}${tail ? `&${tail}` : ''}`)
  },
  // Live dossier (squad + form + deep vs-us). Poll until status === 'ready'.
  // `team` (a grade_id from the dossier's `teams`) narrows the scout to one side;
  // omit it for the whole club. `opponent` can be ANY CA org GUID (club search):
  // a club outside our competitions is discovered via its own org endpoints.
  iqOppositionDossier: ({ opponent, fixtureId, team, name } = {}) =>
    request(`/iq/opposition/dossier?${_iqQs(opponent, fixtureId, team, name)}`),
  // Live ladder standing for an upcoming opponent (our row + theirs).
  iqOpponentLadder: ({ opponent, fixtureId } = {}) =>
    request(`/iq/opposition/ladder?${_iqQs(opponent, fixtureId)}`),
  iqMatchOpponent: ({ opponentName, oppKey, displayName } = {}) =>
    request(`/iq/opposition/match?opponent_name=${encodeURIComponent(opponentName)}&opp_key=${encodeURIComponent(oppKey)}${displayName ? `&display_name=${encodeURIComponent(displayName)}` : ''}`, { method: 'POST' }),
  iqRefreshDossier: ({ opponent, fixtureId, team, name } = {}) =>
    request(`/iq/opposition/dossier/refresh?${_iqQs(opponent, fixtureId, team, name)}`, { method: 'POST' }),
  // Search opposition players by name across every opponent we've faced.
  iqSearchOpponentPlayers: (q) => request(`/iq/opposition/player-search?q=${encodeURIComponent(q)}`),
  // Every player at a club across the last 5 years (light list from the cached
  // career blob) — so a player who hasn't appeared this season is still
  // searchable/selectable on the scout pages. Poll while status === 'building'.
  iqClubPlayers: ({ org, clubName } = {}) =>
    request(`/iq/opposition/club-players?org=${encodeURIComponent(org)}${clubName ? `&club_name=${encodeURIComponent(clubName)}` : ''}`),
  // Last-5-years season-by-season career for any player at any club (CA season
  // aggregates; the whole club is cached once, sliced per player). Poll while
  // status === 'building'. `org` = the club's CA org GUID (dossier opponent.org_id).
  iqPlayerCareer: ({ org, player, clubName } = {}) =>
    request(`/iq/opposition/player-career?org=${encodeURIComponent(org)}&player=${encodeURIComponent(player)}${clubName ? `&club_name=${encodeURIComponent(clubName)}` : ''}`),
  // Scorecard-level deep dive on one external player (dismissals, positions,
  // conversion across the window). First build takes a minute or two; poll.
  iqPlayerDeep: ({ org, player, playerName, clubName } = {}) =>
    request(`/iq/opposition/player-deep?org=${encodeURIComponent(org)}&player=${encodeURIComponent(player)}${playerName ? `&player_name=${encodeURIComponent(playerName)}` : ''}${clubName ? `&club_name=${encodeURIComponent(clubName)}` : ''}`),
  // Manual scouting tags for opponent players (handedness, bowler type, notes…).
  iqOpponentTags: () => request('/iq/opposition/player-tags'),
  iqSaveOpponentTag: (playerId, body) =>
    request(`/iq/opposition/player-tags/${encodeURIComponent(playerId)}`, { method: 'PUT', body: JSON.stringify(body) }),

  // ─── BetterIQ: Selection analysis ───────────────────────
  // Fixtures with a saved BetterSelect lineup, ready to analyse.
  iqSelectionLineups: () => request('/iq/selection/lineups'),
  // Balance / form / warnings / promote-rest / fairness for one fixture's XI.
  iqSelectionAnalysis: (fixtureId) =>
    request(`/iq/selection/analysis?fixture_id=${encodeURIComponent(fixtureId)}`),

  // Every player in OUR club (full history, light career summary) — backs the
  // unified Player search, which spans our players and any external club.
  iqAllPlayers: () => request('/iq/players'),
  // Natural-language question grounded in the club's own data.
  iqAsk: (question, history = []) => request('/iq/ask', { method: 'POST', body: JSON.stringify({ question, history }) }),

  // ─── BetterIQ: Player trends & development ──────────────
  iqTrendsOverview: (seasonId, gradeId) => {
    const qs = new URLSearchParams()
    if (seasonId) qs.set('season_id', seasonId)
    if (gradeId) qs.set('grade_id', gradeId)
    const s = qs.toString()
    return request(`/iq/trends/overview${s ? `?${s}` : ''}`)
  },
  iqTrendsPlayers: (seasonId, gradeId) => {
    const qs = new URLSearchParams()
    if (seasonId) qs.set('season_id', seasonId)
    if (gradeId) qs.set('grade_id', gradeId)
    const s = qs.toString()
    return request(`/iq/trends/players${s ? `?${s}` : ''}`)
  },
  iqTrendsPlayer: (playerId) => request(`/iq/trends/player/${encodeURIComponent(playerId)}`),
  iqPlayerDeepDive: (playerId) => request(`/iq/trends/player/${encodeURIComponent(playerId)}/deep`),
  // 6-axis batting/bowling radar, normalised vs the squad (50 = squad average).
  iqPlayerRadar: (playerId, seasonId) =>
    request(`/iq/trends/player/${encodeURIComponent(playerId)}/radar${seasonId ? `?season_id=${encodeURIComponent(seasonId)}` : ''}`),
  // Bowler wicket-quality deep dive (set vs new batters, fielders, discipline).
  iqBowlerDeepDive: (playerId) => request(`/iq/trends/player/${encodeURIComponent(playerId)}/bowling-deep`),
  // Teammates: who a player has shared a side with (most games first), and the
  // with-vs-without split of the focal player's output alongside one teammate.
  iqTeammates: (playerId) => request(`/iq/teammates/${encodeURIComponent(playerId)}`),
  iqTeammateSplit: (playerId, teammateId) =>
    request(`/iq/teammates/${encodeURIComponent(playerId)}/with/${encodeURIComponent(teammateId)}`),
  // Manual scouting card for one of OUR players (batting/bowling intel — the
  // ball-level read CA can't give us). Mirror of the opponent player tags.
  iqPlayerScouting: (playerId) => request(`/iq/trends/player/${encodeURIComponent(playerId)}/scouting`),
  iqSavePlayerScouting: (playerId, body) =>
    request(`/iq/trends/player/${encodeURIComponent(playerId)}/scouting`, { method: 'PUT', body: JSON.stringify(body) }),

  // ─── BetterIQ: Team self-analysis ───────────────────────
  iqTeamSeasons: () => request('/iq/team/seasons'),
  iqTeamGrades: (seasonId) => request(`/iq/team/grades${seasonId ? `?season_id=${encodeURIComponent(seasonId)}` : ''}`),
  iqTeamOverview: (seasonId, gradeId, seasonIds) => {
    const qs = new URLSearchParams()
    if (seasonId) qs.set('season_id', seasonId)
    if (gradeId) qs.set('grade_id', gradeId)
    if (Array.isArray(seasonIds)) seasonIds.forEach(id => id && qs.append('season_ids', id))
    const s = qs.toString()
    return request(`/iq/team/overview${s ? `?${s}` : ''}`)
  },
  iqTeamMvp: (seasonId, gradeId) => {
    const qs = new URLSearchParams()
    if (seasonId) qs.set('season_id', seasonId)
    if (gradeId) qs.set('grade_id', gradeId)
    const s = qs.toString()
    return request(`/iq/team/mvp${s ? `?${s}` : ''}`)
  },
  // Innings phase shape (Powerplay/Middle/Death) from ball-by-ball data — recent
  // live-scored games only. Our team's, and an opponent's.
  iqTeamPhases: (seasonId, gradeId, side) => {
    const qs = new URLSearchParams()
    if (seasonId) qs.set('season_id', seasonId)
    if (gradeId) qs.set('grade_id', gradeId)
    if (side) qs.set('side', side)
    const s = qs.toString()
    return request(`/iq/team/phases${s ? `?${s}` : ''}`)
  },
  iqOppositionPhases: ({ opponent, fixtureId } = {}) =>
    request(`/iq/opposition/phases?${_iqQs(opponent, fixtureId)}`),

  // ─── BetterIQ: Post-match review ────────────────────────
  iqReviewGames: (seasonId, gradeId) => {
    const qs = new URLSearchParams()
    if (seasonId) qs.set('season_id', seasonId)
    if (gradeId) qs.set('grade_id', gradeId)
    const s = qs.toString()
    return request(`/iq/review/games${s ? `?${s}` : ''}`)
  },
  iqGameReview: (gameId) => request(`/iq/review/game/${encodeURIComponent(gameId)}`),

  // ─── BetterComms (BetterAdmin module) — bulk email ──────────────────────────
  commsListContacts: ({ query = '', subscribed } = {}) => {
    const qs = new URLSearchParams()
    if (query) qs.set('query', query)
    if (subscribed != null) qs.set('subscribed', String(subscribed))
    const s = qs.toString()
    return request(`/club-admin/comms/contacts${s ? `?${s}` : ''}`)
  },
  commsCreateContact: (email, name) =>
    request('/club-admin/comms/contacts', { method: 'POST', body: JSON.stringify({ email, name }) }),
  commsUpdateContact: (id, patch) =>
    request(`/club-admin/comms/contacts/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  commsDeleteContact: (id) =>
    request(`/club-admin/comms/contacts/${id}`, { method: 'DELETE' }),
  commsBulkDeleteContacts: (contactIds) =>
    request('/club-admin/comms/contacts/bulk-delete', { method: 'POST', body: JSON.stringify({ contact_ids: contactIds }) }),
  commsRemoveContactsFromAllLists: (contactIds) =>
    request('/club-admin/comms/contacts/remove-from-all-lists', { method: 'POST', body: JSON.stringify({ contact_ids: contactIds }) }),
  commsImportContacts: (text) =>
    request('/club-admin/comms/contacts/import', { method: 'POST', body: JSON.stringify({ text }) }),
  commsFirstNameFindReplace: (find, replace) =>
    request('/club-admin/comms/contacts/first-name-find-replace', { method: 'POST', body: JSON.stringify({ find, replace }) }),
  commsAudiencePreview: (audience) =>
    request('/club-admin/comms/audience/preview', { method: 'POST', body: JSON.stringify(audience) }),

  commsListCampaigns: () => request('/club-admin/comms/campaigns'),
  commsCampaignEngagement: () => request('/club-admin/comms/campaigns/engagement'),
  commsCreateCampaign: (data) =>
    request('/club-admin/comms/campaigns', { method: 'POST', body: JSON.stringify(data) }),
  commsGetCampaign: (id) => request(`/club-admin/comms/campaigns/${id}`),
  commsUpdateCampaign: (id, data) =>
    request(`/club-admin/comms/campaigns/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  commsDeleteCampaign: (id) =>
    request(`/club-admin/comms/campaigns/${id}`, { method: 'DELETE' }),
  commsTestCampaign: (id, email) =>
    request(`/club-admin/comms/campaigns/${id}/test`, { method: 'POST', body: JSON.stringify({ email }) }),
  commsSendCampaign: (id) =>
    request(`/club-admin/comms/campaigns/${id}/send`, { method: 'POST' }),
  commsCampaignStatus: (id) => request(`/club-admin/comms/campaigns/${id}/status`),
  commsCampaignRecipients: (id, only) =>
    request(`/club-admin/comms/campaigns/${id}/recipients${only ? `?only=${only}` : ''}`),
  commsPreviewCampaign: (id, index = 0) => request(`/club-admin/comms/campaigns/${id}/preview?index=${index}`),

  commsGetSettings: () => request('/club-admin/comms/settings'),
  commsSetSettings: (data) =>
    request('/club-admin/comms/settings', { method: 'PUT', body: JSON.stringify(data) }),
  commsSendTestEmail: (email) =>
    request('/club-admin/comms/test-email', { method: 'POST', body: JSON.stringify({ email }) }),
  commsSesStatus: () => request('/club-admin/comms/ses-status'), // super admin only
  commsProvisionTenants: (all = false) =>
    request(`/club-admin/comms/ses/provision-tenants${all ? '?all=true' : ''}`, { method: 'POST' }),
  // Super-admin: club vs BetterCricket marketing-outreach context.
  commsGetContext: () => request('/club-admin/comms/context'),
  commsSetMarketingOrg: (organisationId) =>
    request('/club-admin/comms/marketing-org', { method: 'POST', body: JSON.stringify({ organisation_id: organisationId }) }),
  commsEnsureMarketingOrg: () => request('/club-admin/comms/marketing-org/ensure', { method: 'POST' }),
  // Deliverability (Phase 1): global suppression + per-contact event history.
  commsListSuppressions: () => request('/club-admin/comms/suppressions'),
  commsRemoveSuppression: (email) =>
    request(`/club-admin/comms/suppressions?email=${encodeURIComponent(email)}`, { method: 'DELETE' }),
  commsContactEvents: (contactId) => request(`/club-admin/comms/contacts/${contactId}/events`),
  commsContactDetail: (contactId) => request(`/club-admin/comms/contacts/${contactId}`),
  commsMergeVariables: () => request('/club-admin/comms/merge-variables'),
  // Dynamic segments (Phase 2): saved queries over contacts + cricket data.
  commsListSegments: () => request('/club-admin/comms/segments'),
  commsCreateSegment: (name, definition) =>
    request('/club-admin/comms/segments', { method: 'POST', body: JSON.stringify({ name, definition }) }),
  commsUpdateSegment: (id, name, definition) =>
    request(`/club-admin/comms/segments/${id}`, { method: 'PUT', body: JSON.stringify({ name, definition }) }),
  commsDeleteSegment: (id) => request(`/club-admin/comms/segments/${id}`, { method: 'DELETE' }),
  commsPreviewSegment: (definition) =>
    request('/club-admin/comms/segments/preview', { method: 'POST', body: JSON.stringify({ name: '', definition }) }),
  commsResolveSegment: (definition) =>
    request('/club-admin/comms/segments/resolve', { method: 'POST', body: JSON.stringify({ name: '', definition }) }),
  commsSegmentExportCsvUrl: (id) => `${BASE}/club-admin/comms/segments/${id}/export.csv`,
  commsSegmentOptions: () => request('/club-admin/comms/segments/options'),
  // Static lists (Phase 2): curated sets of contacts.
  commsListLists: () => request('/club-admin/comms/lists'),
  commsCreateList: (name) => request('/club-admin/comms/lists', { method: 'POST', body: JSON.stringify({ name }) }),
  // Turn a filtered Clubhouse Directory selection into an auto-generated list.
  // Sends person keys, never emails — the server reads the addresses from its
  // own Directory data.
  commsCreateListFromDirectory: ({ name, keys }) =>
    request('/club-admin/comms/lists/from-directory', { method: 'POST', body: JSON.stringify({ name, keys }) }),
  commsRenameList: (id, name) => request(`/club-admin/comms/lists/${id}`, { method: 'PUT', body: JSON.stringify({ name }) }),
  commsDeleteList: (id) => request(`/club-admin/comms/lists/${id}`, { method: 'DELETE' }),
  commsListMembers: (id) => request(`/club-admin/comms/lists/${id}/members`),
  commsAddListMembers: (id, contactIds) =>
    request(`/club-admin/comms/lists/${id}/members`, { method: 'POST', body: JSON.stringify({ contact_ids: contactIds }) }),
  commsRemoveListMember: (id, contactId) =>
    request(`/club-admin/comms/lists/${id}/members/${contactId}`, { method: 'DELETE' }),
  commsRemoveListMembers: (id, contactIds) =>
    request(`/club-admin/comms/lists/${id}/members/remove`, { method: 'POST', body: JSON.stringify({ contact_ids: contactIds }) }),
  commsCopyListMembers: (contactIds, listIds) =>
    request('/club-admin/comms/lists/members/copy', { method: 'POST', body: JSON.stringify({ contact_ids: contactIds, list_ids: listIds }) }),
  commsListExportCsvUrl: (id) => `${BASE}/club-admin/comms/lists/${id}/export.csv`,
  // Email templates (Phase 3).
  commsListTemplates: () => request('/club-admin/comms/templates'),
  commsGetTemplate: (id) => request(`/club-admin/comms/templates/${id}`),
  commsCreateTemplate: (name, html) =>
    request('/club-admin/comms/templates', { method: 'POST', body: JSON.stringify({ name, html }) }),
  commsUpdateTemplate: (id, name, html) =>
    request(`/club-admin/comms/templates/${id}`, { method: 'PUT', body: JSON.stringify({ name, html }) }),
  commsDeleteTemplate: (id) => request(`/club-admin/comms/templates/${id}`, { method: 'DELETE' }),
  commsDuplicateTemplate: (id) =>
    request(`/club-admin/comms/templates/${id}/duplicate`, { method: 'POST' }),
  commsPreviewTemplate: (html, utm) =>
    request('/club-admin/comms/templates/preview', { method: 'POST', body: JSON.stringify({ html, utm }) }),

  // BetterFantasyCricket (admin surface)
  fantasyConfig: () => request('/club-admin/fantasy/config'),
  fantasyGetSeason: () => request('/club-admin/fantasy/season'),
  fantasyCreateSeason: (season_year, name) =>
    request('/club-admin/fantasy/season', { method: 'POST', body: JSON.stringify({ season_year, name }) }),
  fantasyBuildPool: (seasonId, reset) =>
    request(`/club-admin/fantasy/season/${seasonId}/build-pool${reset ? '?reset=true' : ''}`, { method: 'POST' }),
  fantasyGenerateRounds: (seasonId) =>
    request(`/club-admin/fantasy/season/${seasonId}/generate-rounds`, { method: 'POST' }),
  fantasyListPool: (seasonId) => request(`/club-admin/fantasy/season/${seasonId}/pool`),
  fantasyPatchPool: (poolId, data) =>
    request(`/club-admin/fantasy/pool/${poolId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  fantasyListRounds: (seasonId) => request(`/club-admin/fantasy/season/${seasonId}/rounds`),
  fantasySettleRound: (roundId) =>
    request(`/club-admin/fantasy/rounds/${roundId}/settle`, { method: 'POST' }),
  fantasySettleDue: (seasonId) =>
    request(`/club-admin/fantasy/season/${seasonId}/settle-due`, { method: 'POST' }),
  fantasyDeleteSeason: (seasonId) =>
    request(`/club-admin/fantasy/season/${seasonId}`, { method: 'DELETE' }),
  fantasyListDraftLeagues: (seasonId) => request(`/club-admin/fantasy/season/${seasonId}/draft-leagues`),
  fantasyCreateDraftLeague: (seasonId, data) =>
    request(`/club-admin/fantasy/season/${seasonId}/draft-leagues`, { method: 'POST', body: JSON.stringify(data) }),
  fantasyStartDraft: (leagueId) => request(`/club-admin/fantasy/draft-leagues/${leagueId}/start`, { method: 'POST' }),
  fantasyAdvanceDraft: (leagueId) => request(`/club-admin/fantasy/draft-leagues/${leagueId}/advance`, { method: 'POST' }),
  fantasyProcessWaivers: (leagueId) => request(`/club-admin/fantasy/draft-leagues/${leagueId}/process-waivers`, { method: 'POST' }),
  fantasySetRegistration: (seasonId, registration_open) =>
    request(`/club-admin/fantasy/season/${seasonId}/registration`, { method: 'POST', body: JSON.stringify({ registration_open }) }),
  fantasyRegenerateLink: () => request('/club-admin/fantasy/regenerate-link', { method: 'POST' }),
  fantasyUpdateRules: (seasonId, data) =>
    request(`/club-admin/fantasy/season/${seasonId}/rules`, { method: 'PATCH', body: JSON.stringify(data) }),
  fantasyUpdateScoring: (seasonId, data) =>
    request(`/club-admin/fantasy/season/${seasonId}/scoring`, { method: 'PATCH', body: JSON.stringify(data) }),
  fantasyAvailablePlayers: (seasonId, q = '') =>
    request(`/club-admin/fantasy/season/${seasonId}/available-players?q=${encodeURIComponent(q)}`),
  fantasyAddPoolPlayer: (seasonId, data) =>
    request(`/club-admin/fantasy/season/${seasonId}/pool`, { method: 'POST', body: JSON.stringify(data) }),
  fantasyAddNewPlayer: (seasonId, data) =>
    request(`/club-admin/fantasy/season/${seasonId}/pool/new-player`, { method: 'POST', body: JSON.stringify(data) }),
  fantasyRemovePoolPlayer: (poolId) =>
    request(`/club-admin/fantasy/pool/${poolId}`, { method: 'DELETE' }),
  fantasyManagers: () => request('/club-admin/fantasy/managers'),
  fantasyUpdateManager: (managerId, data) =>
    request(`/club-admin/fantasy/managers/${managerId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  fantasyDeleteManager: (managerId) =>
    request(`/club-admin/fantasy/managers/${managerId}`, { method: 'DELETE' }),
  fantasyManagerTeams: (managerId) =>
    request(`/club-admin/fantasy/managers/${managerId}/teams`),
}

function _iqQs(opponent, fixtureId, team, name) {
  const qs = new URLSearchParams()
  if (opponent) qs.set('opponent', opponent)
  if (fixtureId) qs.set('fixture_id', fixtureId)
  if (team) qs.set('team', team)
  // Display name for a club outside our history (picked from the CA-wide club
  // search) — without it the backend can only echo the org GUID back.
  if (name) qs.set('name', name)
  return qs.toString()
}
