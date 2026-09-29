import { useEffect, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'
import LoadingSpinner from '../../../components/LoadingSpinner'

// Football's own ladders: games every 50, goals at 50 then every 100
// (services/afl/milestone_rules.py). The figure is the whole career (synced,
// imported and hand-entered), the same one the player's profile shows, so the
// list and the profile can't disagree about who is close.
const WINDOWS = [30, 60, 90, 180, 365]
const label = t => (t === 'games' ? 'games' : 'goals')

function PlayerLink({ slug, id, name }) {
  return slug ? <Link to={`/${slug}/players/${id}`} className="hover:underline">{name}</Link> : name
}

export default function AflAdminMilestones() {
  const { settings } = useOutletContext() || {}
  const [days, setDays] = useState(60)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    setData(null)
    aflApi.adminMilestones(days).then(setData).catch(e => { setError(e.message); setData({ upcoming: [], reached: [] }) })
  }, [days])

  const slug = settings?.slug
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">Milestones</h1>
        <p className="text-sm text-pb-dim mt-1">Games and goals milestones coming up, and the ones just reached.</p>
      </div>
      {error && <p className="text-sm text-[var(--pb-negative)]">{error}</p>}
      {data === null ? <LoadingSpinner /> : (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="pb-card p-4">
            <SectionTitle right={<span className="font-mono text-[10px] text-pb-faint">{data.upcoming.length}</span>}>Coming up</SectionTitle>
            {data.upcoming.length === 0 ? <p className="text-sm text-pb-faint">Nobody is within reach of a milestone right now.</p> : (
              <ul className="divide-y divide-[var(--pb-hairline)]">
                {data.upcoming.map(m => (
                  <li key={`${m.player_id}-${m.type}`} className="py-2 flex items-baseline justify-between gap-3" data-testid="milestone-upcoming">
                    <span className="text-sm min-w-0 truncate"><PlayerLink slug={slug} id={m.player_id} name={m.name} /></span>
                    <span className="text-sm text-pb-dim shrink-0">
                      <span className="font-semibold text-pb-text">{m.needed}</span> to {m.target} {label(m.type)}
                      <span className="text-pb-faint"> ({m.current})</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="pb-card p-4">
            <SectionTitle right={
              <select value={days} onChange={e => setDays(Number(e.target.value))}
                className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 text-xs">
                {WINDOWS.map(d => <option key={d} value={d}>Last {d} days</option>)}
              </select>
            }>Just reached</SectionTitle>
            {data.reached.length === 0 ? <p className="text-sm text-pb-faint">No milestones reached in this window.</p> : (
              <ul className="divide-y divide-[var(--pb-hairline)]">
                {data.reached.map(m => (
                  <li key={`${m.player_id}-${m.type}-${m.target}`} className="py-2 flex items-baseline justify-between gap-3" data-testid="milestone-reached">
                    <span className="text-sm min-w-0 truncate"><PlayerLink slug={slug} id={m.player_id} name={m.name} /></span>
                    <span className="text-sm shrink-0"><span className="font-semibold">{m.target} {label(m.type)}</span>
                      {m.reached_by && <span className="text-pb-faint"> · {new Date(m.reached_by).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <p className="text-xs text-pb-faint mt-3">Reached is worked out from synced games, the only ones with a date. An imported season counts towards a career but never reads as a recent milestone.</p>
          </div>
        </div>
      )}
    </div>
  )
}
