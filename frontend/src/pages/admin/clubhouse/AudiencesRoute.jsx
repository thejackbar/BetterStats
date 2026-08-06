import { lazy, Suspense } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../../../contexts/AuthContext'

const ClubhouseAudiences = lazy(() => import('./ClubhouseAudiences'))

// The audience routes, with one guard on them.
//
// ClubhouseAudiences is the CLUB builder: its rule vocabulary is squads, player
// roles, runs and wickets, money owed. None of that exists on BetterCricket's
// outreach org, so a super admin who lands here in internal mode (a bookmark,
// browser back, a typed URL — the sidebar already points elsewhere) would build
// an audience against fields with nothing behind them and get an empty count
// with no explanation. Send them to the directory builder instead.
//
// The guard lives out here rather than inside ClubhouseAudiences on purpose.
// That screen imports CLUB_FIELD_DEFS and nothing else, and keeping it free of
// any mode awareness is what stops the two field sets ever collapsing into one
// screen with a flag. See docs/design_handoff_betterclubhouse/PROJECT_RULES.md.
export default function AudiencesRoute() {
  const { user } = useAuth()
  if (user?.can_switch_clubs && user?.is_marketing_org) {
    return <Navigate to="/admin/super/directory-audiences" replace />
  }
  return (
    <Suspense fallback={null}>
      <ClubhouseAudiences />
    </Suspense>
  )
}
