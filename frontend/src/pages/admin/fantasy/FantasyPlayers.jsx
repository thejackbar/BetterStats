import { FantasyFrame, ManagersCard, useFantasySeason } from './shared'

// Registered players — the people who signed up on the public link. View the
// team each one picked, edit their details, reset a PIN, or remove a duplicate.
// Managers are club-scoped (not per season), so this page works without one.
export default function FantasyPlayers() {
  const { msg, err, flash, fail } = useFantasySeason()
  return (
    <FantasyFrame title="Registered players" needSeason={false} msg={msg} err={err}>
      <ManagersCard flash={flash} fail={fail} />
    </FantasyFrame>
  )
}
