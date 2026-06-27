const BASE = import.meta.env.VITE_API_URL || '/api'

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...options.headers }
  const res = await fetch(`${BASE}${path}`, { ...options, headers, credentials: 'include' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
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
    throw new Error(detail)
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

  // Organisations (UUID-based, used internally once slug is resolved)
  searchOrgs: (q) => request(`/organisations/search?q=${encodeURIComponent(q)}`),
  getSocialScorecard: (matchId) => request(`/admin/social/scorecard/${matchId}`),
  getSocialFixtures: () => request('/admin/social/fixtures'),
  getSocialResults: () => request('/admin/social/results'),
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
  // ─── BetterImport — overlap-safe historical CSV/XLSX import ──────────────────
  importPreview: (file) => uploadFile('/club-admin/imports/preview', file),
  importResolve: (payload) =>
    request('/club-admin/imports/resolve', { method: 'POST', body: JSON.stringify(payload) }),
  importCommit: (payload) =>
    request('/club-admin/imports/commit', { method: 'POST', body: JSON.stringify(payload) }),
  importList: () => request('/club-admin/imports'),
  importUndo: (batchId) =>
    request(`/club-admin/imports/${batchId}/undo`, { method: 'POST' }),
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
  mktAssociations: () => request('/club-admin/marketing/associations'),
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
  mktCrawlControl: (paused) =>
    request('/club-admin/marketing/crawl/control', { method: 'POST', body: JSON.stringify({ paused }) }),
  mktCrawl: (limit) =>
    request(`/club-admin/marketing/crawl${limit ? `?limit=${limit}` : ''}`, { method: 'POST' }),
  mktExportComms: (payload) =>
    request('/club-admin/marketing/export-comms', { method: 'POST', body: JSON.stringify(payload) }),
  mktSetContactSelected: (contactId, selected) =>
    request(`/club-admin/marketing/contacts/${contactId}`, { method: 'PATCH', body: JSON.stringify({ selected }) }),
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
  adminUsageByClub: ({ days = 7, roles = [], eventType = null } = {}) => {
    const params = new URLSearchParams({ days: String(days) })
    ;(roles || []).forEach(r => params.append('role', r))
    if (eventType) params.set('event_type', eventType)
    return request(`/club-admin/usage/by-club?${params}`)
  },
  adminUsageVisitors: ({ days = 7, eventType = null, anonOnly = false } = {}) => {
    const params = new URLSearchParams({ days: String(days) })
    if (eventType) params.set('event_type', eventType)
    if (anonOnly) params.set('anon_only', 'true')
    return request(`/club-admin/usage/visitors?${params}`)
  },
  // Realtime snapshot: active visitors, per-minute, live feed, top pages, sources, UTMs.
  adminUsageLive: () => request('/club-admin/usage/live'),
  // Notification centre (bell icon)
  getNotificationsCount: () => request('/club-admin/notifications/count'),
  getNotificationsSummary: () => request('/club-admin/notifications/summary'),
  markNotificationsSeen: (appVersion) =>
    request('/club-admin/notifications/seen', {
      method: 'POST',
      body: JSON.stringify({ app_version: appVersion || null }),
    }),
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
  adminCheckScorecardDuplicate: (playedAt, opponent = '') =>
    request(`/club-admin/manual-entries/scorecard/check-duplicate?played_at=${encodeURIComponent(playedAt)}&opponent=${encodeURIComponent(opponent)}`),

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

  // Super admin
  superOverview: () => request('/club-admin/super/overview'),
  superListOnboarding: () => request('/club-admin/super/onboarding-requests'),
  superUpdateOnboarding: (id, status) =>
    request(`/club-admin/super/onboarding-requests/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) }),
  // Re-scope the admin app to another club (super admin only). Pass null to
  // return to the staff member's home club. Returns the fresh /auth/me payload.
  switchClub: (clubId) =>
    request('/auth/switch-club', { method: 'POST', body: JSON.stringify({ club_id: clubId }) }),
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
  bsTeamGradeOptions: () => request('/teams/grade-options'),
  bsTeamLadders: () => request('/ladders/teams'),
  laddersPublic: (slug) => request(`/ladders/public/${slug}`),
  laddersGrade: (gradeId) => request(`/ladders/grade/${gradeId}`),
  bsCreateTeam: (data) =>
    request('/teams', { method: 'POST', body: JSON.stringify(data) }),
  bsUpdateTeam: (id, data) =>
    request(`/teams/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  bsDeleteTeam: (id) => request(`/teams/${id}`, { method: 'DELETE' }),
  bsSeedTeams: () => request('/teams/seed', { method: 'POST' }),
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
  bsSetSelection: (fixtureId, players) =>
    request(`/selection/${fixtureId}`, { method: 'PUT', body: JSON.stringify({ players }) }),
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
  commsImportContacts: (text) =>
    request('/club-admin/comms/contacts/import', { method: 'POST', body: JSON.stringify({ text }) }),
  commsSyncFromClub: () =>
    request('/club-admin/comms/contacts/sync-from-club', { method: 'POST' }),
  commsAudiencePreview: (audience) =>
    request('/club-admin/comms/audience/preview', { method: 'POST', body: JSON.stringify(audience) }),

  commsListCampaigns: () => request('/club-admin/comms/campaigns'),
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
  commsPreviewCampaign: (id, index = 0) => request(`/club-admin/comms/campaigns/${id}/preview?index=${index}`),

  commsGetSettings: () => request('/club-admin/comms/settings'),
  commsSetSettings: (data) =>
    request('/club-admin/comms/settings', { method: 'PUT', body: JSON.stringify(data) }),
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
