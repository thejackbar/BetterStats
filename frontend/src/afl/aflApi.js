// BetterStats AFL API client — the AFL silo's endpoints only. Auth + club
// resolution reuse the shared client (`api` from lib/api.js): the AFL backend
// serves the same /auth/* and /clubs/{slug} shapes.
const BASE = import.meta.env.VITE_API_URL || '/api'

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
}

// Score formatting: AFL scores read "14.8 (92)" — goals.behinds (points).
export const scoreLine = (goals, behinds, score) =>
  (goals == null && score == null) ? '—'
    : `${goals ?? 0}.${behinds ?? 0} (${score ?? (goals ?? 0) * 6 + (behinds ?? 0)})`
