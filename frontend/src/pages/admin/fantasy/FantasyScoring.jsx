import { FantasyFrame, ScoringCard, useFantasySeason } from './shared'

// Scoring system — the points table and the off-role / captain multipliers.
// Its own side-menu page.
export default function FantasyScoring() {
  const { season, loading, msg, err, flash, fail, reload } = useFantasySeason()
  return (
    <FantasyFrame title="Scoring system" season={season} loading={loading} msg={msg} err={err}>
      {season && <ScoringCard season={season} flash={flash} fail={fail} onSaved={reload} />}
    </FantasyFrame>
  )
}
