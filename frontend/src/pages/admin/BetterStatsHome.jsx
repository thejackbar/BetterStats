import BetterStatsLayout, { NAV } from '../../components/admin/BetterStatsLayout'
import ModuleOverviewGrid from '../../components/admin/ModuleOverviewGrid'

// BetterStats surface home — the data engine's tools, grouped.
export default function BetterStatsHome() {
  return (
    <BetterStatsLayout title="BetterStats">
      <p className="text-pb-faint text-sm mb-6 max-w-2xl">
        Your club's data engine. Bring matches and players in, keep them tidy, and build the
        records and yearbooks that sit on top.
      </p>
      <ModuleOverviewGrid nav={NAV} />
    </BetterStatsLayout>
  )
}
