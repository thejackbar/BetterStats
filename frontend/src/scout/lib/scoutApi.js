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
  getOverview: () => request('/scout/overview'),
  searchClubs: (q) => request(`/scout/clubs/search?q=${encodeURIComponent(q)}`),
  getClubRoster: (orgGuid, clubName) =>
    request(`/scout/clubs/${orgGuid}/roster${clubName ? `?club_name=${encodeURIComponent(clubName)}` : ''}`),
  refreshClubRoster: (orgGuid, clubName) =>
    request(`/scout/clubs/${orgGuid}/roster/refresh${clubName ? `?club_name=${encodeURIComponent(clubName)}` : ''}`, { method: 'POST' }),
  addPlayer: (orgGuid, playerId, clubName, watchlistId) =>
    request('/scout/players/add', { method: 'POST', body: JSON.stringify({ org_guid: orgGuid, player_id: playerId, club_name: clubName, watchlist_id: watchlistId }) }),
  addManualPlayer: (name, clubName, notes, watchlistId) =>
    request('/scout/players/manual', { method: 'POST', body: JSON.stringify({ name, club_name: clubName, notes, watchlist_id: watchlistId }) }),
  listPlayers: () => request('/scout/players'),
  getPlayer: (id, q) => request(`/scout/players/${id}${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  refreshPlayer: (id) => request(`/scout/players/${id}/refresh`, { method: 'POST' }),
  removePlayerEverywhere: (id) => request(`/scout/players/${id}/tracking`, { method: 'DELETE' }),

  // Cross-club linking — a player who plays for several clubs.
  getOtherClubCandidates: (id) => request(`/scout/players/${id}/other-clubs`),
  rescanOtherClubs: (id) => request(`/scout/players/${id}/other-clubs/scan`, { method: 'POST' }),
  searchOtherClub: (id, { orgGuid, clubName }) =>
    request(`/scout/players/${id}/other-clubs/search-club`, { method: 'POST', body: JSON.stringify({ org_guid: orgGuid, club_name: clubName }) }),
  linkPlayerClub: (id, { orgGuid, playerId, isPrimary }) =>
    request(`/scout/players/${id}/clubs/link`, { method: 'POST', body: JSON.stringify({ org_guid: orgGuid, player_id: playerId, is_primary: !!isPrimary }) }),
  unlinkPlayerClub: (id, clubRowId) => request(`/scout/players/${id}/clubs/${clubRowId}`, { method: 'DELETE' }),
  listNotes: (id) => request(`/scout/players/${id}/notes`),
  createNote: (id, body, kind) => request(`/scout/players/${id}/notes`, { method: 'POST', body: JSON.stringify({ body, kind }) }),
  updateNote: (noteId, fields) => request(`/scout/players/notes/${noteId}`, { method: 'PATCH', body: JSON.stringify(fields) }),
  deleteNote: (noteId) => request(`/scout/players/notes/${noteId}`, { method: 'DELETE' }),
  uploadPlayerPhoto: async (id, file) => {
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch(API_BASE + `/scout/players/${id}/photo`, { method: 'POST', credentials: 'include', body: fd })
    if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || 'Upload failed') }
    return res.json()
  },
  deletePlayerPhoto: (id) => request(`/scout/players/${id}/photo`, { method: 'DELETE' }),

  listWatchlists: () => request('/scout/watchlists'),
  createWatchlist: (name) => request('/scout/watchlists', { method: 'POST', body: JSON.stringify({ name }) }),
  renameWatchlist: (watchlistId, name) => request(`/scout/watchlists/${watchlistId}`, { method: 'PATCH', body: JSON.stringify({ name }) }),
  getBoard: (watchlistId) => request(`/scout/watchlists/${watchlistId}/board`),
  createColumn: (watchlistId, name) =>
    request(`/scout/watchlists/${watchlistId}/columns`, { method: 'POST', body: JSON.stringify({ name }) }),
  renameColumn: (columnId, name) =>
    request(`/scout/watchlists/columns/${columnId}`, { method: 'PATCH', body: JSON.stringify({ name }) }),
  deleteColumn: (columnId) => request(`/scout/watchlists/columns/${columnId}`, { method: 'DELETE' }),
  reorderColumns: (watchlistId, columnIds) =>
    request(`/scout/watchlists/${watchlistId}/columns/reorder`, { method: 'POST', body: JSON.stringify({ column_ids: columnIds }) }),
  moveCard: (cardId, columnId, position) =>
    request(`/scout/watchlists/cards/${cardId}/move`, { method: 'POST', body: JSON.stringify({ column_id: columnId, position }) }),
  updateCard: (cardId, fields) =>
    request(`/scout/watchlists/cards/${cardId}`, { method: 'PATCH', body: JSON.stringify(fields) }),
  removeCard: (cardId) => request(`/scout/watchlists/cards/${cardId}`, { method: 'DELETE' }),

  createShareLink: (cardId) => request(`/scout/watchlists/cards/${cardId}/share`, { method: 'POST' }),
  revokeShareLink: (cardId) => request(`/scout/watchlists/cards/${cardId}/share`, { method: 'DELETE' }),
  // Public — no scout session needed, but the shared request() helper works
  // fine either way (it just sends credentials:'include', harmless with no
  // cookie present).
  getSharedCard: (token) => request(`/public/scout/share/${token}`),

  // Compare
  getComparison: (playerIds) => request(`/scout/compare?players=${playerIds.map(encodeURIComponent).join(',')}`),
  shareComparison: (playerIds) => request('/scout/compare/share', { method: 'POST', body: JSON.stringify({ player_ids: playerIds }) }),
  getSharedComparison: (token) => request(`/public/scout/compare/${token}`),

  // Player search + hot form feed — platform-wide, across every cached club
  // roster (see services/scout_feed.py's docstring for the exact scope).
  searchFeed: (q) => request(`/scout/feed/search?q=${encodeURIComponent(q)}`),
  getHotForm: () => request('/scout/feed/hot-form'),

  // Global search — clubs + players in one dropdown (see services/scout_search.py).
  unifiedSearch: (q) => request(`/scout/search?q=${encodeURIComponent(q)}`),

  // Milestones
  getMilestones: (seasons) => request(`/scout/milestones${seasons ? `?seasons=${seasons}` : ''}`),
  markMilestoneSeen: (scoutedPlayerId, milestoneType, milestoneValue) =>
    request('/scout/milestones/seen', { method: 'POST', body: JSON.stringify({ scouted_player_id: scoutedPlayerId, milestone_type: milestoneType, milestone_value: milestoneValue }) }),
  markAllMilestonesSeen: () => request('/scout/milestones/seen-all', { method: 'POST' }),

  // Settings
  getSettings: () => request('/scout/settings'),
  updateSettings: (fields) => request('/scout/settings', { method: 'PATCH', body: JSON.stringify(fields) }),
  getBilling: () => request('/scout/settings/billing'),
  listPeople: () => request('/scout/people'),
  invitePerson: (email, role) => request('/scout/people/invite', { method: 'POST', body: JSON.stringify({ email, role }) }),
  revokeInvite: (inviteId) => request(`/scout/people/invites/${inviteId}`, { method: 'DELETE' }),
  listShareLinksOrg: () => request('/scout/settings/share-links'),
  revokeAllShareLinks: () => request('/scout/settings/share-links/revoke-all', { method: 'POST' }),
  closeOrg: () => request('/scout/settings/close-org', { method: 'POST' }),
  previewInvite: (token) => request(`/public/scout/invite/${token}`),
  acceptInvite: (token, username, password, displayName) =>
    request(`/public/scout/invite/${token}/accept`, { method: 'POST', body: JSON.stringify({ username, password, display_name: displayName }) }),
}
