import { Link } from 'react-router-dom'
import { useScoutAuth } from '../contexts/ScoutAuthContext'

const QUICK_LINKS = [
  { to: '/betterscout/app/discover', label: 'Discover players', desc: 'Search any Australian club’s roster and stats.' },
  { to: '/betterscout/app/watchlists', label: 'Watchlists', desc: 'Kanban boards for shortlisting and tracking.' },
  { to: '/betterscout/app/players', label: 'My players', desc: 'Everyone this org is tracking.' },
  { to: '/betterscout/app/compare', label: 'Compare', desc: 'Side-by-side career stats for two or more players.' },
]

export default function ScoutDashboard() {
  const { user } = useScoutAuth()
  const usage = user?.usage

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Welcome to BetterScout</h1>
        <p className="text-pb-dim">
          Signed in as <span className="text-pb-text">{user?.display_name || user?.username}</span> at{' '}
          <span className="text-pb-text">{user?.scout_org_name}</span>.
        </p>
      </div>

      {usage && <UsageMeter usage={usage} />}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {QUICK_LINKS.map((l) => (
          <Link key={l.to} to={l.to} className="pb-card p-4 hover:border-[var(--pb-accent)]">
            <div className="font-medium">{l.label}</div>
            <div className="text-sm text-pb-dim mt-0.5">{l.desc}</div>
          </Link>
        ))}
      </div>
    </div>
  )
}

function UsageMeter({ usage }) {
  const { tier_label, player_count, player_cap, at_cap } = usage
  const pct = player_cap ? Math.min(100, Math.round((player_count / player_cap) * 100)) : 0

  return (
    <div className="pb-card p-4">
      <div className="flex items-center justify-between text-sm mb-2">
        <span className="text-pb-dim">
          {tier_label} plan{' '}
          {player_cap ? `· ${player_count} / ${player_cap} players tracked` : `· ${player_count} players tracked (unlimited)`}
        </span>
        {at_cap && <span className="text-xs px-2 py-0.5 rounded-full bg-[var(--pb-negative)]/20 text-[var(--pb-negative)]">At limit</span>}
      </div>
      {player_cap != null && (
        <div className="h-1.5 rounded-full bg-pb-surface2 overflow-hidden">
          <div
            className="h-full rounded-full"
            style={{ width: `${pct}%`, backgroundColor: at_cap ? 'var(--pb-negative)' : 'var(--pb-accent)' }}
          />
        </div>
      )}
    </div>
  )
}
