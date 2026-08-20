import { lazy, Suspense } from 'react'
import { useAuth } from '../../../contexts/AuthContext'

const ClubhouseSegments = lazy(() => import('./ClubhouseSegments'))
const InternalSegments = lazy(() => import('./InternalSegments'))

// /admin/comms/segments — the one Segments URL, and the one place the two field
// sets are chosen between.
//
// A club officer gets the club builder, whose rules are squads, player roles,
// runs and wickets, money owed. A super admin acting as BetterCricket's own
// outreach org gets the directory builder, whose rules are what a prospect club
// has done. Same shell, same endpoints, same buttons; different vocabulary.
//
// This used to send internal mode to /admin/super/directory-audiences instead,
// which took you out of BetterAdmin mid-task and into the plain admin
// chrome. The screen came into the module rather than the menu item leaving it.
//
// The pick is made HERE, once, and never inside either screen. That is the
// scope rule in one line: each screen imports exactly one field set, so there
// is no code path in which the club builder can be talked into offering the
// prospect fields. Both halves are lazy, so a club session never fetches the
// directory chunk at all. See
// docs/design_handoff_betterclubhouse/PROJECT_RULES.md.
export default function SegmentsRoute() {
  const { user } = useAuth()
  const internal = !!(user?.can_switch_clubs && user?.is_marketing_org)
  return (
    <Suspense fallback={null}>
      {internal ? <InternalSegments /> : <ClubhouseSegments />}
    </Suspense>
  )
}
