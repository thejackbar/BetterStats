import { FantasyFrame, ManagersCard, ManualScoresCard, useFantasySeason } from './shared'

// Registered players — the people who signed up on the public link. View the
// team each one picked, put right a team that lost a player, edit their details,
// reset a PIN, or remove a duplicate. Managers are club-scoped (not per season),
// so this page works without one; typed-in scores need the season.
export default function FantasyPlayers() {
  const { season, msg, err, flash, fail } = useFantasySeason()
  return (
    <FantasyFrame title="Registered players" needSeason={false} msg={msg} err={err}>
      <div className="space-y-6">
        <ManagersCard flash={flash} fail={fail} />
        {season && <ManualScoresCard season={season} flash={flash} fail={fail} />}
      </div>
    </FantasyFrame>
  )
}
