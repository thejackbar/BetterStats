import { useState, useEffect } from 'react'
import { CAP } from '../../lib/capabilities'
import { api } from '../../lib/api'
import ModuleLayout from './ModuleLayout'

// BetterClubManager — the club back office as its own Core surface: committee,
// volunteers, families, member portal, qualifications, events, facilities and
// the club diary. (Provisional name; these tools will grow under this banner.)
// Pulled out of the shared admin sidebar alongside BetterStats.
export const NAV = [
  { to: '/admin/betterclub', label: 'Overview', icon: 'overview', cap: null, exact: true },

  { heading: 'People' },
  { to: '/admin/committee', label: 'Committee', icon: 'teams', cap: CAP.MANAGE_COMMITTEE },
  { to: '/admin/volunteers', label: 'Volunteers', icon: 'player', cap: CAP.MANAGE_VOLUNTEERS },
  { to: '/admin/families', label: 'Families', icon: 'teams', cap: CAP.MANAGE_FAMILIES },
  { to: '/admin/qualifications', label: 'Qualifications', icon: 'check', cap: CAP.MANAGE_QUALIFICATIONS },
  // Member Portal is inserted here only when its platform flag is on (below).

  { heading: 'Club' },
  { to: '/admin/events', label: 'Events', icon: 'timer', cap: CAP.MANAGE_COMMITTEE },
  { to: '/admin/assets', label: 'Assets & Facilities', icon: 'settings', cap: CAP.MANAGE_ASSETS },
  { to: '/admin/club-diary', label: 'Club Diary', icon: 'list', cap: CAP.MANAGE_CLUB_DIARY },
]

export const MEMBER_PORTAL_ITEM = { to: '/admin/member-portal', label: 'Member Portal', icon: 'share', cap: CAP.MANAGE_FEES }

export default function BetterClubManagerLayout({ children, title, actions }) {
  // Member Portal is gated by a platform flag (per club / globally), same as it
  // was in the main admin sidebar — hidden until a super admin switches it on.
  const [memberPortalVisible, setMemberPortalVisible] = useState(false)
  useEffect(() => {
    let alive = true
    api.memberPortalStatus()
      .then(s => { if (alive) setMemberPortalVisible(!!s?.enabled) })
      .catch(() => {})
    return () => { alive = false }
  }, [])

  // Slot Member Portal in after Qualifications (end of the People group) when on.
  const nav = memberPortalVisible
    ? (() => {
        const i = NAV.findIndex(n => n.heading === 'Club')
        return [...NAV.slice(0, i), MEMBER_PORTAL_ITEM, ...NAV.slice(i)]
      })()
    : NAV

  return (
    <ModuleLayout moduleName="ClubManager" nav={nav} title={title} actions={actions}>
      {children}
    </ModuleLayout>
  )
}
