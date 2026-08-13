import { CAP } from '../../lib/capabilities'
import BetterClubhouseLayout from './BetterClubhouseLayout'

// BetterClubManager — the club back office as its own Core surface (provisional
// name). Same GROUPS model as BetterStats: home shows one card per group, each
// group card opens a page of tools, the sidebar flattens the groups. Member
// Portal is inserted into the People group only when its platform flag is on.
export const GROUPS = [
  {
    key: 'people',
    label: 'People',
    icon: 'teams',
    desc: 'Your committee, volunteers and members.',
    items: [
      { to: '/admin/committee', label: 'Committee', icon: 'teams', cap: CAP.MANAGE_COMMITTEE, desc: 'Committee roles and members.' },
      { to: '/admin/volunteers', label: 'Volunteers', icon: 'player', cap: CAP.MANAGE_VOLUNTEERS, desc: 'Volunteer roster and roles.' },
      { to: '/admin/roles', label: 'Roles', icon: 'check', cap: CAP.MANAGE_VOLUNTEERS, desc: 'The club role catalogue.' },
      { to: '/admin/activities', label: 'Activities', icon: 'list', cap: CAP.MANAGE_VOLUNTEERS, desc: 'What volunteer hours are spent on.' },
      { to: '/admin/qualifications', label: 'Qualifications', icon: 'check', cap: CAP.MANAGE_QUALIFICATIONS, desc: 'Track coaching and first-aid tickets.' },
    ],
  },
  {
    key: 'club',
    label: 'Club',
    icon: 'settings',
    desc: 'Events, facilities and the running club diary.',
    items: [
      { to: '/admin/events', label: 'Events', icon: 'timer', cap: CAP.MANAGE_COMMITTEE, desc: 'Club events and the calendar.' },
      { to: '/admin/assets', label: 'Assets & Facilities', icon: 'settings', cap: CAP.MANAGE_ASSETS, desc: 'Grounds, nets and club gear.' },
      { to: '/admin/club-diary', label: 'Club Diary', icon: 'list', cap: CAP.MANAGE_CLUB_DIARY, desc: 'The running club diary.' },
    ],
  },
]

export const MEMBER_PORTAL_ITEM = {
  to: '/admin/member-portal', label: 'Member Portal', icon: 'share', cap: CAP.MANAGE_FEES,
  desc: 'The self-service portal for members.',
}

// Slot Member Portal into the People group when its platform flag is on.
export function withPortal(enabled) {
  if (!enabled) return GROUPS
  return GROUPS.map(g => g.key === 'people' ? { ...g, items: [...g.items, MEMBER_PORTAL_ITEM] } : g)
}

// Flatten groups into the sidebar nav (Overview, then heading + tools per group).
export function navFromGroups(groups) {
  return [
    // Non-exact so Overview stays highlighted on the group pages too.
    { to: '/admin/betterclub', label: 'Overview', icon: 'overview', cap: null },
    ...groups.flatMap(g => [
      { heading: g.label },
      ...g.items.map(({ to, label, icon, cap, exact }) => ({ to, label, icon, cap, exact })),
    ]),
  ]
}

// BetterClubManager stopped being its own surface when it merged into
// BetterClubhouse — these tools are the People and Club sections of that one
// sidebar. This wrapper stays only so the pages that still import it keep
// compiling; the shell they get is the merged one.
export default function BetterClubManagerLayout(props) {
  return <BetterClubhouseLayout {...props} />
}
