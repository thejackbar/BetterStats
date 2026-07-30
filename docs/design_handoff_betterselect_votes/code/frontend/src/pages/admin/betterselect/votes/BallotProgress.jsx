import { progressColour } from './votesTokens'

// "8/11" plus a bar. `expected` is the eligible-voter count for the fixture
// (backend: fixture.voters_expected); 0 means we don't know yet (no team list).
export default function BallotProgress({ count = 0, expected = 0, className = '' }) {
  const pct = expected ? Math.min(100, Math.round((count / expected) * 100)) : 0
  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <div className="flex-1 h-1.5 rounded-full bg-pb-surface2 overflow-hidden">
        <div className="h-full rounded-full transition-[width] duration-300"
          style={{ width: `${pct}%`, background: progressColour(count, expected) }} />
      </div>
      <span className="font-mono text-xs text-pb-text tabular-nums w-[52px] text-right">
        {expected ? `${count}/${expected}` : '—'}
      </span>
    </div>
  )
}
