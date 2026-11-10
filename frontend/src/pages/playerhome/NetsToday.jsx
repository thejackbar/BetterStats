// The player's own nets card: check yourself in to a session that is on now,
// then see where you bat. A time-slot session says which net and what time (and
// how long until it, by this phone's own clock); a queue session says where you
// are in the batting order. The place comes from the server and changes when the
// coach moves someone, so the card re-reads every 30 seconds while it is on screen.
//
// Always mounted when the club serves the Training module, and draws nothing when
// there is no session on, so a net session started after the page opened turns up
// without a reload. Declared at module level, never inside a render function.
import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import { Section, fmtTime, fmtShort } from './ui'

const ord = (n) => {
  const v = n % 100
  if (v >= 11 && v <= 13) return `${n}th`
  return `${n}${({ 1: 'st', 2: 'nd', 3: 'rd' })[n % 10] || 'th'}`
}

// One line for the section header, from the same data the card reads. Empty when
// there is nothing true to say.
export function netsSummary(sessions) {
  const list = sessions || []
  const mine = list.find((s) => s.checked_in && s.place)
  if (mine) {
    const p = mine.place
    if (p.mode === 'auto') {
      if (p.net && p.time) return { text: `${p.net.name} at ${fmtTime(p.time)}`, tone: 'var(--pb-positive)' }
      return p.bats ? { text: 'Checked in to nets' } : { text: 'Not batting at nets' }
    }
    if (p.batted) return { text: 'Had your turn at nets' }
    if (p.in_nets_now) return { text: 'In the nets now', tone: 'var(--pb-positive)' }
    if (p.position) return { text: `${ord(p.position)} in the batting order`, tone: 'var(--pb-positive)' }
    return { text: 'Checked in to nets' }
  }
  return list.some((s) => s.can_check_in) ? { text: 'Nets on, check in', tone: 'var(--pb-amber)' } : {}
}

function until(startAt, slotMinutes, now) {
  if (!startAt) return ''
  const start = new Date(startAt).getTime()
  if (Number.isNaN(start)) return ''
  const mins = Math.round((start - now) / 60000)
  if (mins > 0) return mins >= 120 ? '' : `in ${mins} min`
  if (now < start + (slotMinutes || 7) * 60000) return 'on now'
  return 'your slot has finished'
}

function Place({ place, now }) {
  if (place.mode === 'auto') {
    if (!place.bats) return <div className="text-[13px]" data-place="not-batting">You are here and not batting.</div>
    if (!place.configured) return <div className="text-[13px]" data-place="not-set">You are checked in. The times are not set yet.</div>
    if (!place.net) return <div className="text-[13px]" data-place="no-net">You are checked in. Your coach will put you in a net.</div>
    if (!place.time) {
      return (
        <div className="text-[13px]" data-place="no-slot">
          You are checked in to {place.net.name}. There is no slot for you before the finish, so your coach will sort it out.
        </div>
      )
    }
    const rel = until(place.start_at, place.slot_minutes, now)
    return (
      <div data-place="slot">
        <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Your net</div>
        <div className="font-display font-bold text-[20px] leading-tight" data-place-net>{place.net.name}</div>
        <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mt-2">You bat at</div>
        <div className="font-display font-bold text-[28px] leading-none tabular-nums" data-place-time>
          {fmtTime(place.time)}
          {rel && <span className="ml-2 text-[13px] font-normal text-pb-faint" data-place-rel>{rel}</span>}
        </div>
        {(place.also || []).length > 0 && (
          <div className="text-[12.5px] text-pb-faint mt-1.5" data-place-also>
            Second go if there is time: {place.also.map(fmtTime).join(', ')}
          </div>
        )}
      </div>
    )
  }
  if (place.batted) return <div className="text-[13px]" data-place="done">You have had your turn.</div>
  if (!place.bats) return <div className="text-[13px]" data-place="not-batting">You are here and not batting.</div>
  if (place.in_nets_now) return <div className="font-display font-bold text-[18px]" data-place="now">You are in the nets now.</div>
  if (!place.position) return <div className="text-[13px]">You are checked in.</div>
  return (
    <div data-place="queue">
      <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Your place in the batting order</div>
      <div className="font-display font-bold text-[28px] leading-none" data-place-position>{ord(place.position)}</div>
      <div className="text-[12.5px] text-pb-faint mt-1">{place.ahead} {place.ahead === 1 ? 'person is' : 'people are'} ahead of you.</div>
    </div>
  )
}

export default function NetsToday({ token, initial, onSessions }) {
  const [sessions, setSessions] = useState(initial || [])
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState('')
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => { onSessions && onSessions(sessions) }, [sessions]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let alive = true
    const read = () => {
      if (document.hidden) return
      api.availPublicNets(token).then((r) => { if (alive) setSessions(r.sessions || []) }).catch(() => {})
    }
    const poll = setInterval(read, 30000)
    const clock = setInterval(() => setNow(Date.now()), 30000)
    document.addEventListener('visibilitychange', read)
    return () => { alive = false; clearInterval(poll); clearInterval(clock); document.removeEventListener('visibilitychange', read) }
  }, [token])

  const checkIn = async (id) => {
    setBusy(id); setError('')
    try {
      const r = await api.availPublicNetsCheckIn(token, id)
      setSessions(r.sessions || [])
    } catch (e) {
      setError(e.message || 'Could not check you in.')
    } finally { setBusy(null) }
  }

  if (!sessions.length) return null
  return (
    <Section title="Nets tonight">
      <div className="flex flex-col gap-3" data-nets-today>
        {sessions.map((s) => (
          <div key={s.id} className="rounded-xl border pb-hairline p-3" data-nets-session={s.id}>
            <div className="text-[12.5px] text-pb-faint mb-2">{s.label || 'Nets'} · {fmtShort(s.date)}</div>
            {s.checked_in && s.place
              ? <Place place={s.place} now={now} />
              : s.can_check_in
                ? (
                  <button type="button" onClick={() => checkIn(s.id)} disabled={busy === s.id} data-nets-checkin
                    className="w-full rounded-lg px-4 py-3 font-display font-bold text-[15px] disabled:opacity-60"
                    style={{ background: 'var(--pb-accent)', color: '#08110b' }}>
                    {busy === s.id ? 'Checking you in…' : 'I am here, check me in'}
                  </button>
                )
                : (
                  <div className="text-[13px] text-pb-faint" data-nets-closed>
                    {s.started ? 'The nets have started. Check in with whoever is running them.' : 'Nets are on. Check in with whoever is running them.'}
                  </div>
                )}
          </div>
        ))}
        {error && <div className="text-[12.5px]" style={{ color: 'var(--pb-red)' }} role="alert" data-nets-error>{error}</div>}
      </div>
    </Section>
  )
}
