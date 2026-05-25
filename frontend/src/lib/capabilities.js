// Capability constants — keep in sync with backend/app/auth/capabilities.py

export const CAP = {
  MANAGE_SETTINGS: 'manage_settings',
  MANAGE_PLAYERS: 'manage_players',
  MANAGE_MERGES: 'manage_merges',
  MANAGE_YEARBOOKS: 'manage_yearbooks',
  MANAGE_AWARDS: 'manage_awards',
  MANAGE_SPONSORS: 'manage_sponsors',
  MANAGE_SOCIAL: 'manage_social',
  MANAGE_MILESTONES: 'manage_milestones',
  RUN_SYNC: 'run_sync',
  RUN_HARD_REFRESH: 'run_hard_refresh',
  MANAGE_USERS: 'manage_users',
}

// Display metadata for the user-management UI checkboxes.
export const CAPABILITY_INFO = [
  { key: CAP.MANAGE_SETTINGS, label: 'Manage settings', hint: 'Club name, colours, logo' },
  { key: CAP.MANAGE_PLAYERS, label: 'Manage players', hint: 'Edit player profiles + photos' },
  { key: CAP.MANAGE_MERGES, label: 'Merge data', hint: 'Merge players, grades and seasons' },
  { key: CAP.MANAGE_YEARBOOKS, label: 'Manage yearbooks', hint: 'Yearbooks, sections, honour board' },
  { key: CAP.MANAGE_AWARDS, label: 'Manage awards', hint: 'Awards + achievements + award types' },
  { key: CAP.MANAGE_SPONSORS, label: 'Manage sponsors', hint: 'Sponsor list + logos' },
  { key: CAP.MANAGE_SOCIAL, label: 'Manage social posts', hint: 'Social Post tool' },
  { key: CAP.MANAGE_MILESTONES, label: 'Manage milestones', hint: 'Milestone definitions + manual entry' },
  { key: CAP.RUN_SYNC, label: 'Run data sync', hint: 'Sync Now + Fix Missing Totals' },
  { key: CAP.RUN_HARD_REFRESH, label: 'Run hard refresh', hint: 'Destructive — wipes + re-syncs everything (1h+)' },
  { key: CAP.MANAGE_USERS, label: 'Manage users', hint: 'Invite club members + assign capabilities' },
]
