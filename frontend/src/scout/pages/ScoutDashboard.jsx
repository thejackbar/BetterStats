import { useScoutAuth } from '../contexts/ScoutAuthContext'

// Foundational-phase placeholder — watchlists, player search and the shared
// data cache are a later phase. This just proves the tenant/auth/shell slice
// works end to end.
export default function ScoutDashboard() {
  const { user } = useScoutAuth()

  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-bold">Welcome to BetterScout</h1>
      <p className="text-pb-dim">
        Signed in as <span className="text-pb-text">{user?.display_name || user?.username}</span> at{' '}
        <span className="text-pb-text">{user?.scout_org_name}</span>.
      </p>
      <p className="text-sm text-pb-faint pt-4">Watchlists are coming in a later phase.</p>
    </div>
  )
}
