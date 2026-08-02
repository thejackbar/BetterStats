import { CAP } from '../../lib/capabilities'
import ModuleLayout from './ModuleLayout'

// BetterStats — the Core data engine as its own module surface. The tools are
// organised into GROUPS: the surface home shows one card per group, each group
// card opens a page listing its tools, and the sidebar flattens the same groups
// into headed sections for quick access. One source of truth, three views.
// URLs of the tools themselves are unchanged — only the surrounding chrome moved.
export const GROUPS = [
  {
    key: 'data',
    label: 'Club Data',
    icon: 'fixtures',
    desc: 'Your matches, players and seasons, plus bringing player contacts in.',
    items: [
      { to: '/admin/games', label: 'Matches', icon: 'fixtures', cap: null, desc: 'Every game and its scorecard.' },
      { to: '/admin/players', label: 'Players', icon: 'player', cap: CAP.MANAGE_PLAYERS, exact: true, desc: "The club's player register and profiles." },
      { to: '/admin/players/import', label: 'Import Players', icon: 'plus', cap: CAP.MANAGE_PLAYERS, desc: 'Bring players in from PlayHQ with their emails, phone numbers and contact details.' },
      { to: '/admin/seasons', label: 'Seasons', icon: 'ladders', cap: null, desc: 'Seasons, grades and their setup.' },
    ],
  },
  {
    key: 'ingest',
    label: 'Data Import',
    icon: 'plus',
    desc: 'Pull in, upload and hand-enter your match data and records.',
    items: [
      { to: '/admin/sync', label: 'Data Sync', icon: 'reset', cap: CAP.RUN_SYNC, desc: 'Pull the latest games and stats from Cricket Australia.' },
      { to: '/admin/import', label: 'Import Stats', icon: 'sheet', cap: CAP.MANAGE_MANUAL_ENTRIES, desc: 'Load historical stats from a file.' },
      { to: '/admin/upload-scorecard', label: 'Upload Scorecard', icon: 'sheet', cap: CAP.MANAGE_MANUAL_ENTRIES, desc: 'Read an old paper scorecard from a photo.' },
      { to: '/admin/manual-entries', label: 'Manual Entries', icon: 'list', cap: CAP.MANAGE_MANUAL_ENTRIES, desc: "Hand-enter a game we can't sync." },
      { to: '/admin/milestones', label: 'Milestones', icon: 'check', cap: CAP.MANAGE_MILESTONES, desc: 'Review and manage player milestones.' },
      { to: '/admin/partnerships', label: 'Partnership Records', icon: 'teams', cap: CAP.MANAGE_AWARDS, desc: 'Check and fix partnership records.' },
    ],
  },
  {
    key: 'tidy',
    label: 'Clean Your Data',
    icon: 'grip',
    desc: 'Merge duplicate players and grades.',
    items: [
      { to: '/admin/merge', label: 'Merge Players', icon: 'teams', cap: CAP.MANAGE_MERGES, desc: 'Combine duplicate player records into one.' },
      { to: '/admin/grades', label: 'Merge Grades', icon: 'grip', cap: CAP.MANAGE_MERGES, desc: 'Combine grades that are really the same competition.' },
    ],
  },
  {
    key: 'records',
    label: 'Records & content',
    icon: 'check',
    desc: 'Awards, yearbooks and the extras on your site.',
    items: [
      { to: '/admin/awards', label: 'Awards', icon: 'check', cap: CAP.MANAGE_AWARDS, desc: 'Record club awards and honours.' },
      { to: '/admin/award-definitions', label: 'Award Types', icon: 'settings', cap: CAP.MANAGE_AWARDS, desc: 'Set up the award categories your club uses.' },
      { to: '/admin/yearbook', label: 'Yearbooks', icon: 'sheet', cap: CAP.MANAGE_YEARBOOKS, desc: 'Write and publish season yearbooks.' },
      { to: '/admin/reports', label: 'Saved Reports', icon: 'ladders', cap: CAP.MANAGE_REPORTS, desc: 'Your saved stat reports.' },
      { to: '/admin/sponsors', label: 'Sponsors', icon: 'share', cap: CAP.MANAGE_SPONSORS, desc: 'Manage the sponsors shown on your site.' },
      { to: '/admin/club-room', label: 'Club Room Mode', icon: 'tv', cap: CAP.MANAGE_CLUB_ROOM, desc: 'Set up a TV slideshow of sponsors, fixtures, lineups and more.' },
    ],
  },
]

// The sidebar flattens the groups: Overview, then a heading + its tools per group.
export const NAV = [
  // Non-exact so Overview stays highlighted on the group pages
  // (/admin/betterstats/:group) too — no tool route is nested under this path.
  { to: '/admin/betterstats', label: 'Overview', icon: 'overview', cap: null },
  ...GROUPS.flatMap(g => [
    { heading: g.label },
    ...g.items.map(({ to, label, icon, cap, exact }) => ({ to, label, icon, cap, exact })),
  ]),
]

export default function BetterStatsLayout({ children, title, actions }) {
  return (
    <ModuleLayout moduleName="Stats" nav={NAV} title={title} actions={actions}>
      {children}
    </ModuleLayout>
  )
}
