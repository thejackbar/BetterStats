import { VOTE_STATES } from './votesTokens'

export default function VoteStateBadge({ state }) {
  const m = VOTE_STATES[state] || VOTE_STATES.upcoming
  return (
    <span className="font-mono text-[10px] font-bold tracking-wide px-2 py-0.5 rounded-full shrink-0"
      style={{ background: `color-mix(in srgb, ${m.cssVar} 15%, transparent)`, color: m.cssVar }}>
      {m.label}
    </span>
  )
}
