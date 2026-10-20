import { FantasyFrame, ScoringCard, GradeScopeCard, useFantasySeason } from './shared'

// Scoring system — which competitions and grades count, the points table and the
// off-role / captain multipliers. Its own side-menu page.
export default function FantasyScoring() {
  const { season, loading, msg, err, flash, fail, reload } = useFantasySeason()
  return (
    <FantasyFrame title="Scoring system" season={season} loading={loading} msg={msg} err={err}>
      {season && (
        <div className="space-y-6">
          <GradeScopeCard season={season} flash={flash} fail={fail} onSaved={reload} />
          <ScoringCard season={season} flash={flash} fail={fail} onSaved={reload} />
        </div>
      )}
    </FantasyFrame>
  )
}
