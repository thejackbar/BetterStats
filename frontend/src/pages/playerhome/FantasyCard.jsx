// BetterFantasyCricket on the player's own page: when the next round locks, where
// their fantasy team sits, and the way in. Read only. The picks, captain and
// transfers stay behind the Fantasy login (the server never sends them here), so
// "Open Fantasy" is where they go to change anything.
import { Muted, Section, Stat } from './ui'

export function fmtLock(iso) {
  try {
    return new Date(iso).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })
  } catch { return iso }
}

// "Sat 8:30 am", for a headline tile.
export function fmtLockShort(iso) {
  try {
    return new Date(iso).toLocaleString(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' })
  } catch { return iso }
}

// "in 2 days 3 hours", "in 5 hours", "in 20 minutes", "any moment".
export function untilLock(iso, now = Date.now()) {
  const ms = new Date(iso).getTime() - now
  if (!Number.isFinite(ms)) return ''
  if (ms <= 0) return 'any moment'
  const mins = Math.floor(ms / 60000)
  const days = Math.floor(mins / 1440)
  const hours = Math.floor((mins % 1440) / 60)
  const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`
  if (days >= 1) return hours ? `in ${plural(days, 'day')} ${plural(hours, 'hour')}` : `in ${plural(days, 'day')}`
  if (hours >= 1) return `in ${plural(hours, 'hour')}`
  return `in ${plural(Math.max(mins, 1), 'minute')}`
}

export function ordinal(n) {
  const v = n % 100
  if (v >= 11 && v <= 13) return `${n}th`
  return `${n}${({ 1: 'st', 2: 'nd', 3: 'rd' })[n % 10] || 'th'}`
}

const roundName = (r) => r.name || `Round ${r.number}`

// The first round that has not locked yet, else the one that is running.
export function nextDeadline(deadlines) {
  const list = deadlines || []
  return list.find((d) => !d.locked && d.lock_at) || list.find((d) => d.locked) || null
}

function Deadline({ d }) {
  if (!d) return <Muted data-fantasy-no-deadline>No rounds are scheduled yet.</Muted>
  if (d.locked) {
    return (
      <div data-fantasy-deadline="locked">
        <div className="font-display font-bold text-[18px]">{roundName(d)} is locked</div>
        <div className="text-[12.5px] text-pb-faint mt-0.5">Teams are frozen until it is scored. Points update as scorecards come in.</div>
      </div>
    )
  }
  return (
    <div data-fantasy-deadline="open">
      <div className="text-[12.5px] text-pb-faint">{roundName(d)} locks</div>
      <div className="font-display font-bold text-[18px] leading-tight">{fmtLock(d.lock_at)}</div>
      <div className="text-[12.5px] mt-0.5" style={{ color: 'var(--pb-amber)' }}>{untilLock(d.lock_at)}</div>
    </div>
  )
}

function Team({ team, deadline }) {
  if (!team) {
    return (
      <p className="text-[12.5px] text-pb-faint mt-3" data-fantasy-no-team>
        Open Fantasy to see your team and make your picks.
      </p>
    )
  }
  if (!team.built) {
    return (
      <p className="text-[12.5px] mt-3" data-fantasy-not-built style={{ color: 'var(--pb-amber)' }}>
        You have not picked a team yet.{deadline && !deadline.locked ? ` Do it before ${roundName(deadline)} locks.` : ''}
      </p>
    )
  }
  return (
    <div className="mt-3" data-fantasy-team>
      <div className="font-display font-bold text-[16px] truncate">{team.team_name}</div>
      <div className="grid grid-cols-3 gap-2 mt-2">
        <Stat label={team.of ? `Rank of ${team.of}` : 'Rank'} value={team.rank ? ordinal(team.rank) : '-'} />
        <Stat label="Points" value={team.points} />
        <Stat label={team.last_round ? `Round ${team.last_round.number}` : 'Last round'} value={team.last_round ? team.last_round.points : '-'} />
      </div>
      {team.this_round_points != null && (
        <div className="text-[12.5px] text-pb-dim mt-2" data-fantasy-live>This round so far: {team.this_round_points} points</div>
      )}
      <div className="text-[12px] text-pb-faint mt-1">
        {team.free_transfers} free transfer{team.free_transfers === 1 ? '' : 's'}
      </div>
    </div>
  )
}

export default function FantasyCard({ data }) {
  const f = data.fantasy
  if (!f) return null
  const deadline = nextDeadline(f.deadlines)
  const later = (f.deadlines || []).filter((d) => d !== deadline && !d.locked && d.lock_at).slice(0, 2)
  const ap = f.as_player
  return (
    <Section title={f.name || 'Fantasy'}>
      <div data-fantasy>
        <Deadline d={deadline} />
        {later.length > 0 && (
          <div className="mt-2 flex flex-col gap-0.5" data-fantasy-later>
            {later.map((d) => (
              <div key={d.number} className="flex items-baseline justify-between gap-3 text-[12.5px] text-pb-faint">
                <span>{roundName(d)}</span><span>{fmtLock(d.lock_at)}</span>
              </div>
            ))}
          </div>
        )}
        <Team team={f.team} deadline={deadline} />
        {ap && (
          <div className="text-[12.5px] text-pb-dim mt-3" data-fantasy-as-player>
            You as a pick: {ap.points} points, ${Number(ap.price).toFixed(1)}, in {ap.owned_count} team{ap.owned_count === 1 ? '' : 's'}.
          </div>
        )}
        <a href={f.link} data-fantasy-link className="block text-center mt-3 py-2.5 rounded-lg text-sm font-semibold"
          style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}>
          {f.team && f.team.built ? 'Open Fantasy' : f.season?.registration_open ? 'Play Fantasy' : 'Open Fantasy'}
        </a>
        <div className="text-[11.5px] text-pb-faintest mt-2">Your picks and transfers stay behind your Fantasy sign in.</div>
      </div>
    </Section>
  )
}
