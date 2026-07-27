import { useParams } from 'react-router-dom'
import BetterStatsLayout, { GROUPS } from '../../components/admin/BetterStatsLayout'
import ModuleHub from '../../components/admin/ModuleHub'

// BetterStats surface home. /admin/betterstats shows the group cards;
// /admin/betterstats/:group shows that group's tools. Same component, one route
// with an optional param.
export default function BetterStatsHome() {
  const { group } = useParams()
  return (
    <BetterStatsLayout title="BetterStats">
      {!group && (
        <p className="text-pb-faint text-sm mb-6 max-w-2xl">
          Your club's data engine. Bring matches and players in, keep them tidy, and build the
          records and yearbooks that sit on top.
        </p>
      )}
      <ModuleHub groups={GROUPS} basePath="/admin/betterstats" groupKey={group} />
    </BetterStatsLayout>
  )
}
