// BetterSelect — net session self check-in (public, no login).
//
// The iPad by the door, reached from one per-club link (/nets/:token) pinned as
// a QR on the clubroom wall. A club told us that taking the check-in and running
// the batting timer on one screen doesn't work: the coach is watching a clock
// and a queue while people keep arriving wanting to be ticked off. This is the
// other half of that — players tap their own name on the way in and the coach's
// screen fills up on its own.
//
// TWO THINGS SHAPE THE WHOLE DESIGN, and both come from it being a SHARED
// device rather than somebody's phone:
//
//   * It always goes back to the list. Fifteen people use it in five minutes,
//     so a screen left sitting on one player's confirmation is a screen the
//     next person can't use. Every path returns to the names.
//   * It remembers nobody. There is no session cookie (the availability link's
//     one would be exactly wrong here), so every tap stands on its own.
//
// Big targets, one column, no small print — it gets used at arm's length in a
// clubroom by someone still holding their kit bag.
import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../lib/api'

// How long a confirmation stays up before the screen resets for the next person.
const RESET_MS = 4000
// The coach checks people in too, and marks them as having batted. Re-reading
// keeps the two screens telling the same story without anyone refreshing.
const POLL_MS = 12000

function initialsOf(name) {
  return (name || '?').split(' ').filter(Boolean).map((w) => w[0]).join('').slice(0, 2).toUpperCase()
}

function ClubHeader({ club, session }) {
  return (
    <div className="flex items-center gap-3 mb-5">
      {club?.logo_url
        ? <img src={club.logo_url} alt="" className="w-12 h-12 rounded-xl object-contain bg-pb-surface2 p-1 shrink-0" />
        : <span className="w-12 h-12 rounded-xl flex items-center justify-center font-display font-bold shrink-0"
            style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}>{initialsOf(club?.name)}</span>}
      <div className="min-w-0">
        <div className="font-display font-bold text-lg leading-tight truncate">{club?.name || 'Nets'}</div>
        <div className="font-mono text-[11px] tracking-wide2 text-pb-faint mt-0.5 truncate">
          {session ? (session.label || 'NET SESSION').toUpperCase() : 'NET CHECK-IN'}
        </div>
      </div>
    </div>
  )
}

function Face({ player, size = 44 }) {
  const s = { width: size, height: size }
  if (player.photo_url) {
    return <img src={player.photo_url} alt="" className="rounded-full object-cover shrink-0 bg-pb-surface2" style={s} />
  }
  return (
    <span className="rounded-full flex items-center justify-center font-display font-bold shrink-0 bg-pb-surface2 text-pb-faint"
      style={{ ...s, fontSize: size * 0.36 }}>{initialsOf(player.name)}</span>
  )
}

export default function PublicNetCheckIn() {
  const { token } = useParams()
  const [state, setState] = useState(null)      // null = loading, false = dead link
  const [q, setQ] = useState('')
  const [showAll, setShowAll] = useState(false)
  const [chosen, setChosen] = useState(null)    // the player mid-check-in
  const [pin, setPin] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [flash, setFlash] = useState(null)      // {name, bats} — the "you're in" card
  const pinRef = useRef(null)
  const resetRef = useRef(null)

  const club = state && state.club
  const session = state && state.session
  const accent = club?.accent_color || club?.primary_color || null

  const load = useCallback(async () => {
    try {
      setState(await api.netCheckinLanding(token))
    } catch {
      setState((cur) => (cur ? cur : false))    // a blip mid-session keeps the names on screen
    }
  }, [token])

  useEffect(() => { load() }, [load])

  // Re-read on a slow loop and whenever the screen is woken, so a name the coach
  // ticked off shows as already in rather than inviting a second tap.
  useEffect(() => {
    const iv = setInterval(() => { if (!document.hidden && !chosen) load() }, POLL_MS)
    const onVisible = () => { if (!document.hidden) load() }
    document.addEventListener('visibilitychange', onVisible)
    return () => { clearInterval(iv); document.removeEventListener('visibilitychange', onVisible) }
  }, [load, chosen])

  useEffect(() => () => clearTimeout(resetRef.current), [])
  useEffect(() => { if (chosen && state?.require_pin && pinRef.current) pinRef.current.focus() }, [chosen, state])

  // Back to the list, ready for whoever is next.
  const reset = useCallback(() => {
    clearTimeout(resetRef.current)
    setChosen(null); setPin(''); setNote(''); setError(''); setFlash(null); setQ(''); setShowAll(false)
  }, [])

  const players = (state && state.players) || []
  const { squad, others } = useMemo(() => {
    const t = q.trim().toLowerCase()
    const hit = (p) => !t || (p.name || '').toLowerCase().includes(t)
    return {
      squad: players.filter((p) => hit(p) && p.in_squad),
      others: players.filter((p) => hit(p) && !p.in_squad),
    }
  }, [players, q])
  const searching = q.trim().length > 0
  const showOthers = searching || showAll

  const submit = async (bats) => {
    if (!chosen) return
    setBusy(true); setError('')
    try {
      const next = await api.netCheckinSubmit(token, {
        player_id: chosen.id, pin, bats, note: note.trim() || null,
      })
      setState(next)
      setFlash({ name: chosen.name, bats })
      setChosen(null); setPin(''); setNote('')
      resetRef.current = setTimeout(reset, RESET_MS)
    } catch (e) {
      setError(e.message || 'That didn’t work — try again, or ask your coach.')
    } finally { setBusy(false) }
  }

  const undo = async (player) => {
    setBusy(true); setError('')
    try {
      setState(await api.netCheckinUndo(token, { player_id: player.id, pin }))
      reset()
    } catch (e) {
      setError(e.message || 'Couldn’t undo that — ask your coach.')
    } finally { setBusy(false) }
  }

  if (state === null) {
    return <div className="min-h-screen bg-pb-bg text-pb-text flex items-center justify-center text-pb-faint text-sm">Loading…</div>
  }

  if (state === false) {
    return (
      <div className="min-h-screen bg-pb-bg text-pb-text flex items-center justify-center px-6">
        <div className="text-center max-w-sm">
          <div className="font-display font-bold text-xl mb-2">This check-in link isn’t active</div>
          <p className="text-sm text-pb-faint">Ask your club for the current link, or get your coach to check you in.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text" style={accent ? { '--pb-accent': accent } : undefined}>
      <div className="max-w-lg mx-auto px-4 py-6 sm:py-10">
        <ClubHeader club={club} session={session} />

        {/* No session open. Said plainly rather than letting people tap names
            into nothing — the coach opens the session from BetterSelect. */}
        {!session ? (
          <div className="pb-card px-5 py-10 text-center">
            <div className="font-display font-bold text-[17px] mb-1.5">No nets open yet</div>
            <p className="text-sm text-pb-faint mb-5">
              Your coach opens tonight’s session in BetterSelect. Once they have, your name will be here to tap.
            </p>
            <button onClick={load} className="font-display font-semibold text-sm px-4 py-2.5 rounded-xl"
              style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}>Check again</button>
          </div>
        ) : flash ? (
          /* Checked in. Deliberately loud and short-lived — it is read from a
             couple of steps away, and the next person needs the screen back. */
          <div className="pb-card px-5 py-10 text-center">
            <div className="w-16 h-16 rounded-full mx-auto mb-4 flex items-center justify-center text-3xl"
              style={{ background: 'color-mix(in srgb, var(--pb-positive) 16%, transparent)', color: 'var(--pb-positive)' }}>✓</div>
            <div className="font-display font-bold text-2xl leading-tight">You’re in, {flash.name.split(' ')[0]}</div>
            <p className="text-sm text-pb-faint mt-2">
              {flash.bats ? 'You’re in the batting queue.' : 'Marked as here, not batting tonight.'}
            </p>
            <div className="flex items-center justify-center gap-3 mt-6">
              <button onClick={reset} className="font-display font-semibold text-sm px-5 py-2.5 rounded-xl"
                style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}>Next person</button>
            </div>
          </div>
        ) : chosen ? (
          /* One player, mid-check-in. */
          <div className="pb-card px-5 py-6">
            <div className="flex items-center gap-3 mb-5">
              <Face player={chosen} size={52} />
              <div className="min-w-0">
                <div className="font-display font-bold text-lg truncate">{chosen.name}</div>
                {chosen.checked_in && <div className="text-[12.5px] text-pb-faint">Already checked in tonight</div>}
              </div>
            </div>

            {error && (
              <div className="rounded-lg px-3.5 py-2.5 mb-4 text-sm"
                style={{ background: 'color-mix(in srgb, var(--pb-red) 12%, transparent)', color: 'var(--pb-red)' }}>{error}</div>
            )}

            {state.require_pin && (
              <div className="mb-4">
                <label className="block font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1.5">
                  Last 4 digits of your mobile
                </label>
                <input ref={pinRef} value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 4))}
                  inputMode="numeric" autoComplete="off" placeholder="0000"
                  className="w-full text-center tracking-[0.6em] text-2xl font-mono bg-pb-surface2 border pb-hairline rounded-xl px-4 py-3.5 focus:outline-none focus:border-pb-accent" />
              </div>
            )}

            {chosen.checked_in ? (
              <div className="flex flex-col gap-2.5">
                <button onClick={() => undo(chosen)} disabled={busy}
                  className="w-full font-display font-semibold py-3.5 rounded-xl border pb-hairline2 text-pb-text disabled:opacity-60">
                  {busy ? 'Working…' : 'That wasn’t me — take me off'}
                </button>
                <button onClick={reset} className="w-full text-sm text-pb-faint py-2">Back to the list</button>
              </div>
            ) : (
              <>
                <input value={note} onChange={(e) => setNote(e.target.value.slice(0, 120))}
                  placeholder="Anything the coach should know? (optional)"
                  className="w-full bg-pb-surface2 border pb-hairline rounded-xl px-3.5 py-3 text-sm mb-4 focus:outline-none focus:border-pb-accent" />
                <div className="flex flex-col gap-2.5">
                  <button onClick={() => submit(true)} disabled={busy}
                    className="w-full font-display font-bold text-[17px] py-4 rounded-xl disabled:opacity-60"
                    style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}>
                    {busy ? 'Checking you in…' : 'I’m here — put me down to bat'}
                  </button>
                  {/* Present but out of the rotation. Someone who turns up with a
                      sore shoulder is still at training; leaving them in the
                      queue leaves a net standing empty when their turn comes. */}
                  <button onClick={() => submit(false)} disabled={busy}
                    className="w-full font-display font-semibold py-3.5 rounded-xl border pb-hairline2 text-pb-text disabled:opacity-60">
                    Here, but not batting
                  </button>
                  <button onClick={reset} className="w-full text-sm text-pb-faint py-2">Back to the list</button>
                </div>
              </>
            )}
          </div>
        ) : (
          /* The list of names. */
          <>
            <div className="flex items-baseline justify-between mb-3">
              <div className="font-display font-bold text-[17px]">Tap your name</div>
              <div className="font-mono text-[11px] text-pb-faint">{session.checked_in_count} here</div>
            </div>

            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search for your name…"
              className="w-full bg-pb-surface2 border pb-hairline rounded-xl px-4 py-3 text-base mb-3 focus:outline-none focus:border-pb-accent" />

            {error && (
              <div className="rounded-lg px-3.5 py-2.5 mb-3 text-sm"
                style={{ background: 'color-mix(in srgb, var(--pb-red) 12%, transparent)', color: 'var(--pb-red)' }}>{error}</div>
            )}

            <div className="flex flex-col gap-2">
              {squad.map((p) => <NameRow key={p.id} p={p} onPick={() => { setChosen(p); setError('') }} />)}

              {/* Everyone else the club holds. A player between seasons, or one
                  parked over winter, still walks through the door. */}
              {!showOthers && others.length > 0 && (
                <button onClick={() => setShowAll(true)} className="text-left text-[13px] text-pb-faint py-3 px-1">
                  + Show {others.length} more name{others.length === 1 ? '' : 's'}
                </button>
              )}
              {showOthers && others.length > 0 && (
                <>
                  <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest px-1 pt-2">Everyone else</div>
                  {others.map((p) => <NameRow key={p.id} p={p} onPick={() => { setChosen(p); setError('') }} />)}
                </>
              )}
              {squad.length === 0 && (!showOthers || others.length === 0) && (
                <div className="text-center text-sm text-pb-faint py-8">
                  {searching ? 'No name like that — ask your coach to add you.' : 'Nobody on the roster yet.'}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

/* One tappable name. The whole row is the target — it gets used one-handed. */
function NameRow({ p, onPick }) {
  return (
    <button onClick={onPick}
      className="w-full flex items-center gap-3 px-3 py-3 rounded-xl border pb-hairline bg-pb-surface text-left active:opacity-80">
      <Face player={p} />
      <div className="flex-1 min-w-0">
        <div className="font-display font-semibold text-[15px] truncate">{p.name}</div>
        {p.checked_in && (
          <div className="font-mono text-[10px] uppercase tracking-wide2 mt-0.5"
            style={{ color: p.bats ? 'var(--pb-positive)' : 'var(--pb-amber)' }}>
            {p.bats ? 'Checked in' : 'Here · not batting'}
          </div>
        )}
      </div>
      {p.checked_in
        ? <span className="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
            style={{ background: 'color-mix(in srgb, var(--pb-positive) 16%, transparent)', color: 'var(--pb-positive)' }}>✓</span>
        : <span className="w-8 h-8 rounded-full border pb-hairline2 flex items-center justify-center shrink-0 text-pb-faint">+</span>}
    </button>
  )
}
