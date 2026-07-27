import { CAP } from '../../lib/capabilities'
import ModuleLayout from './ModuleLayout'

// BetterStats — the Core data engine as its own module surface: matches,
// players, seasons, the ingestion/sync tools, data corrections and the
// records/content that sit on top. Pulled out of the shared admin sidebar so
// that sidebar is just the app chrome (dashboard, modules, account). URLs are
// unchanged — only the surrounding chrome moved.
export const NAV = [
  { to: '/admin/betterstats', label: 'Overview', icon: 'overview', cap: null, exact: true },

  { heading: 'Data' },
  { to: '/admin/games', label: 'Matches', icon: 'fixtures', cap: null },
  { to: '/admin/players', label: 'Players', icon: 'player', cap: CAP.MANAGE_PLAYERS, exact: true },
  { to: '/admin/seasons', label: 'Seasons', icon: 'ladders', cap: null },

  { heading: 'Bring data in' },
  { to: '/admin/sync', label: 'Data Sync', icon: 'reset', cap: CAP.RUN_SYNC },
  { to: '/admin/players/import', label: 'Import Players', icon: 'plus', cap: CAP.MANAGE_PLAYERS },
  { to: '/admin/import', label: 'Import Stats', icon: 'sheet', cap: CAP.MANAGE_MANUAL_ENTRIES },
  { to: '/admin/upload-scorecard', label: 'Upload Scorecard', icon: 'sheet', cap: CAP.MANAGE_MANUAL_ENTRIES },
  { to: '/admin/manual-entries', label: 'Manual Entries', icon: 'list', cap: CAP.MANAGE_MANUAL_ENTRIES },

  { heading: 'Tidy & fix' },
  { to: '/admin/merge', label: 'Merge Players', icon: 'teams', cap: CAP.MANAGE_MERGES },
  { to: '/admin/grades', label: 'Merge Grades', icon: 'grip', cap: CAP.MANAGE_MERGES },
  { to: '/admin/milestones', label: 'Milestones', icon: 'check', cap: CAP.MANAGE_MILESTONES },
  { to: '/admin/partnerships', label: 'Partnership Records', icon: 'teams', cap: CAP.MANAGE_AWARDS },

  { heading: 'Records & content' },
  { to: '/admin/awards', label: 'Awards', icon: 'check', cap: CAP.MANAGE_AWARDS },
  { to: '/admin/award-definitions', label: 'Award Types', icon: 'settings', cap: CAP.MANAGE_AWARDS },
  { to: '/admin/yearbook', label: 'Yearbooks', icon: 'sheet', cap: CAP.MANAGE_YEARBOOKS },
  { to: '/admin/reports', label: 'Saved Reports', icon: 'ladders', cap: CAP.MANAGE_REPORTS },
  { to: '/admin/sponsors', label: 'Sponsors', icon: 'share', cap: CAP.MANAGE_SPONSORS },
]

export default function BetterStatsLayout({ children, title, actions }) {
  return (
    <ModuleLayout moduleName="Stats" nav={NAV} title={title} actions={actions}>
      {children}
    </ModuleLayout>
  )
}
