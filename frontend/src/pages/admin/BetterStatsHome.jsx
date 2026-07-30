import { useParams } from 'react-router-dom'
import BetterStatsLayout, { GROUPS } from '../../components/admin/BetterStatsLayout'
import ModuleHub from '../../components/admin/ModuleHub'
import ModuleHero from '../../components/admin/ModuleHero'
import { moduleBrand } from '../../lib/moduleBrand'

const BRAND = moduleBrand('stats')

// BetterStats surface home. /admin/betterstats shows the group cards;
// /admin/betterstats/:group shows that group's tools. Same component, one route
// with an optional param. Laid out the same way as BetterAdmin/BetterSocials'
// home pages (ModuleHero + a max-w-3xl card grid), even though BetterStats'
// cards are tool groups within one module rather than separate products.
export default function BetterStatsHome() {
  const { group } = useParams()
  return (
    <BetterStatsLayout title="BetterStats">
      <div className="max-w-3xl">
        {!group && (
          <ModuleHero
            name="BetterStats"
            logo={BRAND.logo}
            blurb="Your club's data engine. Bring matches and players in, keep them tidy, and build the records and yearbooks that sit on top."
          />
        )}
        <ModuleHub groups={GROUPS} basePath="/admin/betterstats" groupKey={group} />
      </div>
    </BetterStatsLayout>
  )
}
