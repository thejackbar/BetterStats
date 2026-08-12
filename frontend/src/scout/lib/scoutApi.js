// Thin fetch wrappers for BetterScout's own /scout/* endpoints — mirrors
// ScoutAuthContext.jsx's API_BASE computation rather than pulling in the
// whole club-shaped lib/api.js (BetterScout has no club/module concepts).
const API_BASE = import.meta.env.VITE_API_URL || (import.meta.env.BASE_URL + 'api')

async function request(path, options = {}) {
  const res = await fetch(API_BASE + path, {
    credentials: 'include',
    headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

export const scoutApi = {
  searchClubs: (q) => request(`/scout/clubs/search?q=${encodeURIComponent(q)}`),
  getClubRoster: (orgGuid, clubName) =>
    request(`/scout/clubs/${orgGuid}/roster${clubName ? `?club_name=${encodeURIComponent(clubName)}` : ''}`),
  refreshClubRoster: (orgGuid, clubName) =>
    request(`/scout/clubs/${orgGuid}/roster/refresh${clubName ? `?club_name=${encodeURIComponent(clubName)}` : ''}`, { method: 'POST' }),
  addPlayer: (orgGuid, playerId, clubName) =>
    request('/scout/players/add', { method: 'POST', body: JSON.stringify({ org_guid: orgGuid, player_id: playerId, club_name: clubName }) }),
  addManualPlayer: (name, clubName, notes) =>
    request('/scout/players/manual', { method: 'POST', body: JSON.stringify({ name, club_name: clubName, notes }) }),
  listPlayers: () => request('/scout/players'),
  getPlayer: (id) => request(`/scout/players/${id}`),
  refreshPlayer: (id) => request(`/scout/players/${id}/refresh`, { method: 'POST' }),
}
