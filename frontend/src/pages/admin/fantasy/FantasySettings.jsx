import { FantasyFrame, SettingsCard, useFantasySeason } from './shared'

// Team make-up & budget — squad role quota, budget, best-N, transfers, chips
// and the pricing window. Its own side-menu page.
export default function FantasySettings() {
  const { season, loading, msg, err, flash, fail, reload } = useFantasySeason()
  return (
    <FantasyFrame title="Team make-up & budget" season={season} loading={loading} msg={msg} err={err}>
      {season && <SettingsCard season={season} flash={flash} fail={fail} onSaved={reload} />}
    </FantasyFrame>
  )
}
