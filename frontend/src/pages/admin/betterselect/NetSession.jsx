// BetterSelect → Net Manager (live runner). The pitch-side screen the net
// manager drives: check players in, queue them, and run a batting timer that
// rotates a group of N batters through the nets with staged audible alerts.
//
// THE SESSION LIVES ON THE SERVER, not in this browser. The same admin account
// is routinely open on a phone by the nets and a laptop in the clubroom, and
// both have to see and drive the one session — so every tap here is a small
// write (check someone in, re-order, rotate, start the clock), and every open
// screen polls for the version it last saw. A version that has moved brings the
// whole state back and this screen adopts it.
//
// The clock is a server deadline, not a local stopwatch: each device counts
// down to the same moment, correcting for its own clock against the server time
// that comes back with every poll. Alert beeps fire per device — everyone
// standing near a screen should hear them.
import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { PbSpinner } from '../../../lib/presskit'
import { Icon, Btn, Avatar, RoleChips, Search, Empty, NumText, usePref } from './ui'
import { useDragOrder } from './dragOrder'

const POLL_MS = 2500
const TONE_COLOR = { info: 'var(--pb-accent)', amber: 'var(--pb-amber)', red: 'var(--pb-red)' }
const clock = (t) => { const s = Math.max(0, Math.round(t)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}` }
const fmtDate = (d) => { try { return new Date(d + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'short' }) } catch { return d || '' } }

export default function NetSession() {
  const { id } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const { hasCapability } = useAuth()
  const canEdit = hasCapability(CAP.MANAGE_SELECTIONS)

  const [live, setLive] = useState(null)       // null = loading, false = not found
  const [roster, setRoster] = useState([])
  // The club's check-in link, if they've turned it on, so the coach can put it
  // on the second device without going hunting for it. Taking the check-in and
  // running the timer on one screen is what a club reported back.
  const [checkinUrl, setCheckinUrl] = useState(null)
  const [checkInOpen, setCheckInOpen] = useState(false)
  const [banner, setBanner] = useState(null)   // most recent alert, this device
  const [activeTone, setActiveTone] = useState(null)
  // Who has just scanned themselves in, for the pop-up. Names only — this is a
  // notice, not a second copy of the queue.
  const [arrivals, setArrivals] = useState([])
  const [audioReady, setAudioReady] = useState(false)
  const [ending, setEnding] = useState(false)
  const [tick, setTick] = useState(() => Date.now())
  // The attendee whose priority tick is being answered. Ticking priority asks
  // a question — move them up, or just flag it — rather than silently doing
  // one of the two. See PriorityModal.
  const [priorityFor, setPriorityFor] = useState(null)
  // The row-button key: on until this coach turns it off, per person and per
  // browser, so one coach putting it away doesn't take it from the next.
  const [showKey, setShowKey] = usePref('nets_row_key', true)

  const liveRef = useRef(null)
  // How far this device's clock sits behind the server's, in ms. Kept fresh by
  // every poll — a phone that is a minute fast must still stop the batter's
  // turn at the same moment as the laptop.
  const skewRef = useRef(0)
  // Writes and polls must not overlap: a poll that started before a write
  // landed would otherwise come back with the older state and undo it on screen.
  const inflightRef = useRef(0)
  const audioRef = useRef(null)
  const firedRef = useRef({ seq: -1, fired: new Set() })
  const expiredRef = useRef(-1)
  // Every attendee id this screen has already drawn. A screen opening halfway
  // through a session must NOT announce the twenty people who were already
  // there, so the first payload seeds this set silently and only what arrives
  // afterwards is an arrival.
  const seenRef = useRef(null)

  const adopt = useCallback((payload) => {
    if (!payload) return
    if (payload.server_time) {
      const t = new Date(payload.server_time).getTime()
      if (!Number.isNaN(t)) skewRef.current = t - Date.now()
    }
    if (payload.unchanged) return
    liveRef.current = payload
    setLive(payload)
  }, [])

  // ── Load ────────────────────────────────────────────────────────────────
  useEffect(() => {
    let alive = true
    Promise.all([
      api.nmGetSession(id),
      api.nmRoster().then((r) => r.players || []).catch(() => []),
      api.nmGetCheckInLink().catch(() => null),
    ]).then(([s, rs, link]) => {
      if (!alive) return
      setRoster(rs)
      // `path` comes back from the server rather than being built here, so this
      // shortcut and the QR on the Check-in tab can never point at different
      // URLs for the same club.
      if (link && link.enabled && link.path) setCheckinUrl(window.location.origin + link.path)
      adopt(s)
    }).catch((e) => { if (alive) { toast.error(e.message); setLive(false) } })
    return () => { alive = false }
  }, [id, toast, adopt])

  // ── Poll for what the other devices have done ───────────────────────────
  useEffect(() => {
    if (!id) return
    let alive = true
    const poll = async () => {
      if (!alive || inflightRef.current > 0 || document.hidden || !liveRef.current) return
      try { adopt(await api.nmLive(id, liveRef.current.version)) } catch { /* keep showing what we have */ }
    }
    const iv = setInterval(poll, POLL_MS)
    // Coming back to a screen that was in a pocket should catch up at once
    // rather than after the next interval.
    const onVisible = () => { if (!document.hidden) poll() }
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('focus', onVisible)
    return () => {
      alive = false
      clearInterval(iv)
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('focus', onVisible)
    }
  }, [id, adopt])

  // Run a write, then adopt what the server hands back so the device that acted
  // is instantly right instead of waiting for its next poll.
  const act = useCallback(async (fn) => {
    inflightRef.current += 1
    try {
      adopt(await fn())
    } catch (e) {
      toast.error(e.message)
      try { adopt(await api.nmLive(id)) } catch { /* leave the screen as it is */ }
    } finally {
      inflightRef.current -= 1
    }
  }, [adopt, toast, id])

  // ── Audio ─────────────────────────────────────────────────────────────────
  const settings = live && live.settings
  const soundOn = !!(settings && settings.sound)
  const unlockAudio = useCallback(() => {
    if (!soundOn) return
    try {
      if (!audioRef.current) audioRef.current = new (window.AudioContext || window.webkitAudioContext)()
      if (audioRef.current.state === 'suspended') audioRef.current.resume()
      setAudioReady(audioRef.current.state === 'running')
    } catch { /* no audio */ }
  }, [soundOn])

  const beep = useCallback((tone) => {
    if (!soundOn || !audioRef.current) return
    const ctx = audioRef.current
    const [freq, n] = { info: [660, 1], amber: [560, 2], red: [440, 3] }[tone] || [660, 1]
    for (let k = 0; k < n; k++) {
      const t = ctx.currentTime + k * 0.2
      const o = ctx.createOscillator(); const g = ctx.createGain()
      o.type = 'sine'; o.frequency.value = freq
      o.connect(g); g.connect(ctx.destination)
      g.gain.setValueAtTime(0.0001, t)
      g.gain.exponentialRampToValueAtTime(0.35, t + 0.02)
      g.gain.exponentialRampToValueAtTime(0.0001, t + 0.16)
      o.start(t); o.stop(t + 0.18)
    }
  }, [soundOn])

  // ── Somebody just scanned themselves in ───────────────────────────────────
  // The poll already brings self check-ins down within a couple of seconds;
  // this is what makes the iPad on the fence SAY so rather than quietly
  // growing its list. Only `source === 'self'` announces — a name the manager
  // just tapped on this very screen must not pop up at them.
  const liveAttendees = live && live.attendees
  useEffect(() => {
    if (!liveAttendees) return
    const ids = liveAttendees.map((a) => a.id)
    if (seenRef.current === null) { seenRef.current = new Set(ids); return }  // first paint: seed, stay quiet
    const fresh = liveAttendees.filter((a) => !seenRef.current.has(a.id) && a.source === 'self')
    ids.forEach((x) => seenRef.current.add(x))
    if (!fresh.length) return

    setArrivals((prev) => [...prev, ...fresh.map((a) => ({ id: a.id, name: a.name, isNew: a.is_guest }))])
    beep('info')
    // Android honours this; iOS Safari ignores it entirely, which is why the
    // pop-up and the chime carry the alert rather than the buzz.
    try { navigator.vibrate?.([90, 60, 90]) } catch { /* not supported */ }
  }, [liveAttendees, beep])

  // Clear the pop-up on its own — nobody is going to dismiss this by hand
  // mid-session, and a notice that stays up forever stops being a notice.
  useEffect(() => {
    if (!arrivals.length) return
    const t = setTimeout(() => setArrivals([]), 9000)
    return () => clearTimeout(t)
  }, [arrivals])

  // ── The clock ─────────────────────────────────────────────────────────────
  const timer = live && live.timer
  const running = !!(timer && timer.running)
  useEffect(() => {
    if (!running) return
    const iv = setInterval(() => setTick(Date.now()), 200)
    return () => clearInterval(iv)
  }, [running, timer && timer.ends_at])

  const remaining = useMemo(() => {
    if (!timer) return 0
    if (timer.running && timer.ends_at) {
      const ends = new Date(timer.ends_at).getTime()
      if (Number.isNaN(ends)) return timer.remaining_seconds || 0
      return Math.max(0, (ends - (tick + skewRef.current)) / 1000)
    }
    return timer.remaining_seconds || 0
  }, [timer, tick])

  // Alerts, fired on this device. A screen opened part-way through a turn
  // silently arms every alert that has already gone, so it doesn't play the
  // whole session's beeps at once on load.
  useEffect(() => {
    if (!timer || !settings) return
    const alerts = settings.alerts || []
    if (firedRef.current.seq !== timer.turn_seq) {
      firedRef.current = { seq: timer.turn_seq, fired: new Set() }
      alerts.forEach((a, i) => { if (remaining <= a.seconds_remaining) firedRef.current.fired.add(i) })
      setBanner(null); setActiveTone(null)
      return
    }
    if (!timer.running) return
    alerts.forEach((a, i) => {
      if (!firedRef.current.fired.has(i) && remaining <= a.seconds_remaining) {
        firedRef.current.fired.add(i)
        setBanner(a); setActiveTone(a.tone); beep(a.tone)
      }
    })
  }, [remaining, timer, settings, beep])

  // The clock reaching zero is written down once, by whichever device notices
  // first; the server stops it (and rotates, if auto-roll is on) so every other
  // device picks the change up on its next poll rather than racing to do it.
  useEffect(() => {
    if (!timer || !timer.running || remaining > 0) return
    if (expiredRef.current === timer.turn_seq) return
    expiredRef.current = timer.turn_seq
    beep('red')
    setBanner({ label: 'Time — rotate to the next group', tone: 'red' })
    setActiveTone('red')
    if (canEdit) act(() => api.nmTimer(id, 'expire'))
  }, [remaining, timer, canEdit, act, id, beep])

  // ── Derived lists ─────────────────────────────────────────────────────────
  // Three lists, and the split matters: someone sitting out is HERE (their
  // attendance counts) but not in the rotation, because leaving them in it
  // leaves a net standing empty when their name comes up. Same rule the server
  // applies in _waiting, so the queue can't disagree with what rotating does.
  const attendees = (live && live.attendees) || []
  const waiting = useMemo(() => attendees.filter((a) => !a.batted && a.bats !== false), [attendees])
  const sittingOut = useMemo(() => attendees.filter((a) => !a.batted && a.bats === false), [attendees])
  const done = useMemo(() => attendees.filter((a) => a.batted), [attendees])
  const nets = (settings && settings.nets) || 1
  // The turn is finished but nobody has rotated yet, so the top group have had
  // their knock even though nothing has recorded it. `bumpToNext` needs to know:
  // dropping a priority player above them here would have the next rotation
  // mark that player as batted when they never went in.
  const turnOver = !running && remaining <= 0 && waiting.length > 0
  const netsBusy = running || turnOver
  // The night is over: no clock, no check-in, and the QR code lands nowhere.
  // Read off the server rather than a local flag, so a coach who ends it on the
  // phone by the nets sees the laptop in the clubroom follow on its next poll.
  const ended = !!(live && live.status === 'done')
  const inSession = useMemo(() => {
    const s = new Set()
    attendees.forEach((a) => { if (a.player_id) s.add(a.player_id) })
    return s
  }, [attendees])

  // ── Queue ops ─────────────────────────────────────────────────────────────
  const addPlayer = (p) => {
    const existing = attendees.find((a) => a.player_id === p.id)
    if (existing) { act(() => api.nmRemoveAttendee(id, existing.id)); return }
    act(() => api.nmAddAttendee(id, { player_id: p.id }))
  }
  const addGuest = (name) => {
    const n = (name || '').trim()
    if (!n) return
    act(() => api.nmAddAttendee(id, { guest_name: n }))
  }
  const reorder = (ids) => act(() => api.nmReorderQueue(id, ids))
  // Keyboard's answer to the drag handle: a grip with focus takes the arrow
  // keys. Dragging is a pointer gesture and a screen reader has no pointer, so
  // without this the order would be unreachable for anyone not using one.
  const move = (attId, dir) => {
    const ids = waiting.map((a) => a.id)
    const i = ids.indexOf(attId)
    const j = i + dir
    if (i < 0 || j < 0 || j >= ids.length) return
    ;[ids[i], ids[j]] = [ids[j], ids[i]]
    reorder(ids)
  }
  // "BAT NEXT" IS THE FRONT OF THE LINE FOR THE NEXT TURN, WHICH IS NOT THE
  // FRONT OF THE LIST. While a turn is under way the top `nets` names are in
  // the nets, and dropping somebody above them would swap out a batter
  // mid-knock — and worse, the next rotation would mark the new arrival as
  // having batted when they never went in. So they go in behind whoever is
  // currently in. With the nets idle there is nobody to go behind, and the
  // front of the list is the front of the line.
  const bumpToNext = (attId) => {
    const rows = ((liveRef.current && liveRef.current.attendees) || [])
      .filter((a) => !a.batted && a.bats !== false)
      .map((a) => a.id)
    const hold = netsBusy ? rows.slice(0, nets).filter((x) => x !== attId) : []
    const rest = rows.filter((x) => x !== attId && !hold.includes(x))
    return reorder([...hold, attId, ...rest])
  }
  const setBatted = (attId, batted) => act(() => api.nmPatchAttendee(id, attId, { batted }))
  // Told to get their gear on. Transient by design — the server clears it when
  // they walk into a net, so the strip on the fence always answers "who is next
  // in" rather than slowly becoming everyone the coach has ever spoken to.
  const setPaddingUp = (attId, on) => act(() => api.nmPatchAttendee(id, attId, { padding_up: on }))
  // Un-ticking is just an un-tick. Ticking asks the question.
  const togglePriority = (p) => {
    if (p.priority) { act(() => api.nmPatchAttendee(id, p.id, { priority: false })); return }
    setPriorityFor(p)
  }
  const savePriority = async ({ reason, batNext }) => {
    const target = priorityFor
    setPriorityFor(null)
    if (!target) return
    await act(() => api.nmPatchAttendee(id, target.id, { priority: true, note: reason }))
    if (batNext) await bumpToNext(target.id)
  }
  // Moving someone in or out of the rotation. Coming back in puts them at the
  // back of the queue, which is the server's call, not this screen's.
  const setBats = (attId, bats) => act(() => api.nmPatchAttendee(id, attId, { bats }))
  const removeAttendee = (attId) => act(() => api.nmRemoveAttendee(id, attId))

  const start = () => { unlockAudio(); act(() => api.nmTimer(id, 'start')) }
  const pause = () => act(() => api.nmTimer(id, 'pause'))
  const resetTimer = () => act(() => api.nmTimer(id, 'reset'))
  const rotate = () => { unlockAudio(); act(() => api.nmRotate(id, true, timer && timer.turn_seq)) }

  const patchSettings = (partial) => act(() => api.nmUpdateSession(id, { settings: { ...settings, ...partial } }))

  // ── The batting order, and dragging it ────────────────────────────────────
  // A DRAG HOLDS THE POLL OFF for as long as it lasts, on the same in-flight
  // counter a write uses. Without it a poll landing mid-drag adopts the
  // server's older order and the row is pulled out from under the finger.
  const waitingIds = useMemo(() => waiting.map((a) => a.id), [waiting])
  const dragActive = useCallback((on) => { inflightRef.current += on ? 1 : -1 }, [])
  const drag = useDragOrder({
    ids: waitingIds,
    onCommit: reorder,
    enabled: canEdit && !ended,
    onActive: dragActive,
  })
  const byId = useMemo(() => new Map(waiting.map((a) => [a.id, a])), [waiting])
  // The preview wins while a drag is in flight, so the whole screen — the
  // names under the clock included — moves with the finger rather than only
  // the list.
  const battingOrder = useMemo(() => (
    drag.order ? drag.order.map((x) => byId.get(x)).filter(Boolean) : waiting
  ), [drag.order, byId, waiting])
  // The queue IS the batting order: the first `nets` names are in the nets and
  // the rest are the line behind them. One list, so dragging somebody into a
  // batting spot is the same gesture as moving them up the queue — which is
  // the thing that was slow.
  const onNow = useMemo(() => battingOrder.slice(0, nets), [battingOrder, nets])
  // Only somebody still WAITING can be padding up: the flag is about the turn
  // to come, so it says nothing about a person already in a net.
  const paddingUp = useMemo(() => battingOrder.slice(nets).filter((a) => a.padding_up), [battingOrder, nets])

  // ── Ending the night ──────────────────────────────────────────────────────
  // Confirmed, because it closes the QR code as well as stopping the clock —
  // somebody arriving late would scan in to nothing, and the coach should know
  // that before tapping it rather than after. Nothing is lost either way: the
  // attendance stays, and Reopen puts it straight back.
  const endSession = async () => {
    const left = waiting.length
    const msg = left > 0
      ? `End the session? ${left} ${left === 1 ? 'person is' : 'people are'} still in the queue. The clock stops and nobody can check in, including from the QR code.`
      : 'End the session? The clock stops and nobody can check in, including from the QR code.'
    if (!window.confirm(msg)) return
    setEnding(true)
    try {
      await act(() => api.nmUpdateSession(id, { status: 'done' }))
      toast.success('Session ended')
    } finally { setEnding(false) }
  }

  const reopenSession = async () => {
    setEnding(true)
    try {
      await act(() => api.nmUpdateSession(id, { status: 'active' }))
      toast.success('Session reopened — check-in is back on')
    } finally { setEnding(false) }
  }

  if (live === null) return <BetterSelectLayout title="Net session"><PbSpinner message="Loading session…" /></BetterSelectLayout>
  if (live === false) {
    return (
      <BetterSelectLayout title="Net session">
        <div className="pb-card px-5 py-10 text-center">
          <Empty>Session not found.</Empty>
          <div className="mt-3"><Btn variant="ghost" sm icon="back" onClick={() => navigate('/admin/betterselect/nets')}>Back to sessions</Btn></div>
        </div>
      </BetterSelectLayout>
    )
  }

  const timerColor = activeTone ? TONE_COLOR[activeTone] : 'var(--pb-text)'
  const pct = settings.duration_seconds ? Math.max(0, Math.min(100, (remaining / settings.duration_seconds) * 100)) : 0

  return (
    <BetterSelectLayout
      title="Net session"
      actions={<Btn variant="ghost" sm icon="back" onClick={() => navigate('/admin/betterselect/nets')}>Sessions</Btn>}
    >
      {/* Somebody scanned themselves in. Fixed and high on the screen so it
          reads from across the nets, not tucked into a corner. */}
      {arrivals.length > 0 && (
        <div className="fixed inset-x-0 top-3 z-[120] flex justify-center px-3 pointer-events-none">
          <div
            className="pointer-events-auto rounded-2xl px-5 py-4 shadow-lg max-w-md w-full text-center animate-[fadeIn_120ms_ease-out]"
            style={{
              background: 'color-mix(in srgb, var(--pb-positive) 16%, var(--pb-surface))',
              border: '1px solid color-mix(in srgb, var(--pb-positive) 45%, transparent)',
            }}
            role="status"
            aria-live="polite"
            onClick={() => setArrivals([])}
          >
            <div className="font-mono text-[10px] uppercase tracking-wide2" style={{ color: 'var(--pb-positive)' }}>
              Checked in
            </div>
            <div className="font-display font-bold text-[19px] mt-1 leading-tight">
              {arrivals.map((a) => a.name).join(', ')}
            </div>
            {arrivals.some((a) => a.isNew) && (
              <div className="text-[12.5px] text-pb-faint mt-1.5">
                New to the club — their details are waiting on the Check-in tab.
              </div>
            )}
          </div>
        </div>
      )}

      <div className="flex flex-col gap-4">
        {/* A browser won't play a sound until someone has touched the page, so
            an iPad propped on the fence stays silent unless it is asked. Say
            so rather than letting the club think the chime is broken. */}
        {soundOn && !audioReady && (
          <button
            onClick={unlockAudio}
            className="pb-card px-4 py-2.5 text-left text-[12.5px] flex items-center gap-2"
            style={{ borderColor: 'color-mix(in srgb, var(--pb-amber) 40%, transparent)', color: 'var(--pb-amber)' }}
          >
            <Icon name="bolt" size={14} />
            Tap once to turn on sound for check-ins and timer alerts.
          </button>
        )}

        {/* Session header */}
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <div className="font-display font-bold text-[20px] leading-tight">{live.label || 'Net session'}</div>
            <div className="text-[13px] text-pb-faint">
              {fmtDate(live.session_date)} · {attendees.length} checked in · {done.length} batted
              {sittingOut.length > 0 && ` · ${sittingOut.length} not batting`}
            </div>
          </div>
          {/* Wraps, rather than pushing the page sideways. The row gained a
              fourth control and measured 418px against a 390px screen — the
              outer flex-wrap can't save a group that won't wrap itself. */}
          <div className="flex flex-wrap items-center justify-end gap-2">
            <LiveDot ended={ended} />
            {/* The second device. Opening it here rather than making a coach
                find it in Settings is the whole point — it's needed at 6pm.
                Pointless once the session is over: the link would land on
                "no nets on right now". */}
            {checkinUrl && !ended && (
              <Btn variant="ghost" sm icon="teams" href={checkinUrl} target="_blank"
                title="Open the self check-in screen — put this on a spare phone or iPad by the door">Check-in screen</Btn>
            )}
            <Btn variant="ghost" sm icon="download" href={api.nmSessionCsvUrl(id)} title="Download the attendance list for this session">List</Btn>
            {canEdit && !ended && (
              <>
                <Btn variant="primary" icon="plus" onClick={() => { unlockAudio(); setCheckInOpen(true) }}>Check in players</Btn>
                <Btn variant="ghost" sm icon="check" onClick={endSession} disabled={ending}
                  title="Finish the night — stops the clock and closes check-in">
                  {ending ? 'Ending…' : 'End session'}
                </Btn>
              </>
            )}
            {canEdit && ended && (
              <Btn variant="ghost" sm onClick={reopenSession} disabled={ending}
                title="Put the session back on if it was ended by mistake">
                {ending ? 'Reopening…' : 'Reopen'}
              </Btn>
            )}
          </div>
        </div>

        {/* Timer hero */}
        <div className="pb-card overflow-hidden" style={{ borderColor: activeTone ? `color-mix(in srgb, ${timerColor} 45%, transparent)` : undefined }}>
          <div className="px-6 py-6 flex flex-col items-center text-center"
            style={{ background: activeTone ? `linear-gradient(180deg, color-mix(in srgb, ${timerColor} 10%, transparent), transparent)` : undefined }}>
            <div className="font-mono text-[11px] uppercase tracking-wide3 text-pb-faint mb-1">
              {onNow.length ? `On now · net${nets > 1 ? 's 1–' + nets : ' 1'}` : 'Ready'}
            </div>
            <div className="font-display font-bold tabular-nums leading-none" style={{ fontSize: 'clamp(56px, 14vw, 110px)', color: timerColor, transition: 'color .3s' }}>
              {clock(remaining)}
            </div>
            <div className="w-full max-w-[420px] h-1.5 rounded-full bg-pb-surface2 overflow-hidden mt-4">
              <div className="h-full rounded-full" style={{ width: `${pct}%`, background: timerColor, transition: 'width .25s linear, background .3s' }} />
            </div>
            {banner && (
              <div className="mt-3 inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full font-display font-semibold text-[13.5px]"
                style={{ background: `color-mix(in srgb, ${TONE_COLOR[banner.tone] || TONE_COLOR.info} 14%, transparent)`, color: TONE_COLOR[banner.tone] || TONE_COLOR.info }}>
                <Icon name="bolt" size={14} /> {banner.label}
              </div>
            )}
            {turnOver && <div className="mt-3 text-[13px] text-pb-faint">Turn over — hit <b className="text-pb-text">Next group</b> to rotate.</div>}

            {/* Who is in, and who has been told to get ready. Both belong here
                rather than further down the page: this is the block a player
                standing at the nets reads off the iPad on the fence, and the
                whole reason for flagging anybody is that it can be read from
                there. Names are big and the label is beside them, so neither
                line needs the colour to be understood. */}
            {!ended && (
              <div className="w-full max-w-[560px] mt-5 flex flex-col gap-1.5" data-nets-hero>
                <HeroLine
                  slot="nets"
                  label={nets > 1 ? 'In the nets' : 'In the net'}
                  people={onNow}
                  color="var(--pb-accent)"
                  empty="Nobody in yet"
                />
                <HeroLine
                  slot="padding"
                  label="Padding up"
                  people={paddingUp}
                  color="var(--pb-positive)"
                  empty={canEdit ? 'Nobody flagged — tap the pad on the batting order' : 'Nobody flagged yet'}
                />
              </div>
            )}

            {/* Controls. An ended session shows what happened instead of a
                Start button that would quietly put the night back on. */}
            {ended ? (
              <div className="mt-5 text-[13px] text-pb-faint">
                Session ended · {done.length} batted of {attendees.length} here.
                {canEdit && <> Use <b className="text-pb-text">Reopen</b> above if that was a mistake.</>}
              </div>
            ) : canEdit && (
              <div className="flex flex-wrap items-center justify-center gap-2.5 mt-5">
                {!running
                  ? <Btn variant="primary" icon="play" onClick={start} disabled={remaining <= 0 && settings.duration_seconds <= 0}>Start</Btn>
                  : <Btn variant="soft" icon="pause" onClick={pause}>Pause</Btn>}
                <Btn variant="ghost" icon="reset" onClick={resetTimer}>Reset</Btn>
                <Btn variant="ghost" icon="next" onClick={rotate} disabled={!onNow.length}>Next group</Btn>
              </div>
            )}
          </div>

          {/* Quick session settings */}
          {canEdit && (
            <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2 px-5 py-3 border-t pb-hairline text-[12.5px] text-pb-faint">
              <label className="inline-flex items-center gap-1.5">Nets
                <NumText value={nets} min={1} max={8} ariaLabel="Nets" onCommit={(v) => patchSettings({ nets: v })}
                  className="w-12 bg-pb-surface2 border border-pb-hairline rounded px-1.5 h-7 text-center text-pb-text focus:outline-none focus:border-pb-accent" />
              </label>
              <label className="inline-flex items-center gap-1.5">Minutes
                <NumText value={Math.round(settings.duration_seconds / 60)} min={1} max={60} ariaLabel="Minutes"
                  onCommit={(v) => patchSettings({ duration_seconds: v * 60 })}
                  className="w-12 bg-pb-surface2 border border-pb-hairline rounded px-1.5 h-7 text-center text-pb-text focus:outline-none focus:border-pb-accent" />
              </label>
              <button onClick={() => patchSettings({ auto_roll: !settings.auto_roll })} className={`inline-flex items-center gap-1.5 ${settings.auto_roll ? 'text-pb-accent' : ''}`}>
                <Icon name={settings.auto_roll ? 'check' : 'reset'} size={14} /> Auto-roll {settings.auto_roll ? 'on' : 'off'}
              </button>
              <button onClick={() => { unlockAudio(); patchSettings({ sound: !settings.sound }) }} className={`inline-flex items-center gap-1.5 ${settings.sound ? 'text-pb-accent' : ''}`}>
                <Icon name={settings.sound ? 'sound' : 'mute'} size={15} /> Sound {settings.sound ? 'on' : 'off'}
              </button>
            </div>
          )}
        </div>

        {/* The batting order + Done */}
        <div className="grid lg:grid-cols-[1fr_320px] gap-4 items-start">
          {/* ONE LIST FROM THE NETS DOWN, and that is what makes the drag
              worth having: getting the right player into a batting spot is
              now the same gesture as moving them up the queue, rather than a
              separate act performed on a separate card. The rows in the nets
              carry their own tint and a NET n badge so the boundary is still
              obvious. */}
          <div className="pb-card px-4 py-3.5" data-batting-order>
            <div className="flex items-center justify-between gap-2 mb-1.5 flex-wrap">
              <span className="font-display font-bold text-[15px]">Batting order</span>
              <div className="flex items-center gap-3">
                {canEdit && (
                  <button onClick={() => setShowKey((k) => !k)}
                    className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest hover:text-pb-accent">
                    {showKey ? 'Hide key' : 'Key'}
                  </button>
                )}
                <span className="font-mono text-[11px] text-pb-faint">
                  {onNow.length}/{nets} in · {Math.max(0, battingOrder.length - nets)} waiting
                </span>
              </div>
            </div>

            {/* What the row buttons do. Shown by default because these glyphs
                are the club's own vocabulary rather than anything universal —
                and hideable, because a coach who has run a few sessions knows
                them and would rather have the rows. */}
            {canEdit && showKey && <RowKey />}

            {battingOrder.length === 0 ? (
              <Empty className="py-3">Nobody in the order yet. Check players in, then hit Start.</Empty>
            ) : (
              <div className="flex flex-col">
                {battingOrder.map((p, i) => (
                  <OrderRow
                    key={p.id}
                    p={p}
                    i={i}
                    inNet={i < nets}
                    canEdit={canEdit}
                    dragging={drag.dragId === p.id}
                    anyDragging={drag.dragging}
                    innerRef={drag.register(p.id)}
                    handleProps={drag.handleProps(p.id)}
                    onMove={(dir) => move(p.id, dir)}
                    onBatNext={() => bumpToNext(p.id)}
                    onPadUp={() => setPaddingUp(p.id, !p.padding_up)}
                    onPriority={() => togglePriority(p)}
                    onBatted={() => setBatted(p.id, true)}
                    onSitOut={() => setBats(p.id, false)}
                    onRemove={() => removeAttendee(p.id)}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Batted, then Not batting — both out of the queue, for different
              reasons, and both kept off the Up next list so it stays as short
              as what is actually still to come. */}
          <div className="flex flex-col gap-4">
            <div className="pb-card px-4 py-3.5">
              <div className="flex items-center justify-between mb-1.5">
                <span className="font-display font-bold text-[15px]">Batted</span>
                <span className="font-mono text-[11px] text-pb-accent">{done.length} done</span>
              </div>
              {done.length === 0 ? <Empty className="py-3">No completed turns yet.</Empty> : (
                <div className="flex flex-col">
                  {done.map((p) => (
                    <div key={p.id} className="flex items-center gap-2.5 py-2 border-b pb-hairline last:border-0">
                      <Avatar player={{ ...p, id: p.player_id }} size={26} />
                      <span className="flex-1 min-w-0 text-[13px] text-pb-dim truncate">{p.name}</span>
                      <Icon name="check" size={15} className="text-pb-accent" />
                      {canEdit && <button onClick={() => setBatted(p.id, false)} title="Back to queue" className="p-1 text-pb-faint hover:text-pb-text"><Icon name="reset" size={14} /></button>}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Here, but out of the rotation. Still on the screen rather than
                tucked away — they turned up, and the coach needs to know who is
                about to bowl or field even though the queue skips them. */}
            {sittingOut.length > 0 && (
              <div className="pb-card px-4 py-3.5">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="font-display font-bold text-[15px]">Not batting</span>
                  <span className="font-mono text-[11px] text-pb-amber">{sittingOut.length} here</span>
                </div>
                <div className="flex flex-col">
                  {sittingOut.map((p) => (
                    <div key={p.id} className="flex items-center gap-2.5 py-2 border-b pb-hairline last:border-0">
                      <Avatar player={{ ...p, id: p.player_id }} size={26} />
                      <div className="flex-1 min-w-0">
                        <div className="text-[13px] text-pb-dim truncate">{p.name}</div>
                        {p.note && <div className="text-[11px] text-pb-faint truncate">{p.note}</div>}
                      </div>
                      {canEdit && (
                        <div className="flex items-center gap-0.5 text-pb-faint">
                          <button onClick={() => setBats(p.id, true)} title="Put back in the queue" className="p-1 hover:text-pb-accent"><Icon name="batNext" size={16} /></button>
                          <button onClick={() => removeAttendee(p.id)} title="Remove" className="p-1 hover:text-pb-red"><Icon name="close" size={15} /></button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {checkInOpen && (
        <CheckInModal roster={roster} inSession={inSession} onAdd={addPlayer} onGuest={addGuest} onClose={() => setCheckInOpen(false)} />
      )}

      {priorityFor && (
        <PriorityModal person={priorityFor} netsBusy={netsBusy} onClose={() => setPriorityFor(null)} onSave={savePriority} />
      )}
    </BetterSelectLayout>
  )
}

/* ── Who is in, and who is next ───────────────────────────────────────────────
 * The two lines a player reads off the iPad on the fence from twenty metres
 * away. The LABEL is beside the names rather than the colour carrying the
 * difference on its own: this app's own green and amber separate by ΔE 7.2
 * under protanopia, so a state told only in colour is a state some people on
 * the sidelines can't read. */
function HeroLine({ slot, label, people, color, empty }) {
  const has = people.length > 0
  return (
    <div data-hero-line={slot} className="flex items-baseline gap-2.5 justify-center flex-wrap">
      <span className="font-mono text-[10px] uppercase tracking-wide3 shrink-0" style={{ color: has ? color : 'var(--pb-faintest)' }}>
        {label}
      </span>
      {has ? (
        <span className="font-display font-bold text-[17px] leading-snug" style={{ color }}>
          {people.map((p) => p.name).join(' · ')}
        </span>
      ) : (
        <span className="text-[12.5px] text-pb-faintest">{empty}</span>
      )}
    </div>
  )
}

/* ── One name in the batting order ────────────────────────────────────────────
 * Every state is spelled out as a word as well as tinted, for the reason
 * HeroLine gives — and because a row can legitimately be two of them at once
 * (a priority player who has been told to pad up), which no single colour can
 * say. The left edge takes whichever is most immediate: in a net, then padding
 * up, then priority.
 *
 * The action group WRAPS onto its own line rather than squeezing the name,
 * because this screen is run from a tablet held in portrait as often as a
 * laptop and seven 34px targets plus a name do not fit on one 390px line. */
function OrderRow({
  p, i, inNet, canEdit, dragging, anyDragging, innerRef, handleProps,
  onMove, onBatNext, onPadUp, onPriority, onBatted, onSitOut, onRemove,
}) {
  const edge = inNet ? 'var(--pb-accent)' : p.padding_up ? 'var(--pb-positive)' : p.priority ? 'var(--pb-amber)' : null
  return (
    <div
      ref={innerRef}
      data-att={p.id}
      className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 py-2 pl-2 border-b pb-hairline last:border-0"
      style={{
        borderLeft: `3px solid ${edge || 'transparent'}`,
        background: dragging
          ? 'color-mix(in srgb, var(--pb-accent) 12%, var(--pb-surface2))'
          : inNet ? 'color-mix(in srgb, var(--pb-accent) 6%, transparent)' : undefined,
        // Lifted while held, so the row under the finger is obvious without a
        // second element chasing it around the page.
        boxShadow: dragging ? '0 6px 18px rgba(0,0,0,.28)' : undefined,
        borderRadius: dragging ? 8 : undefined,
        // Off during a drag: the rows are moving under the pointer, and a
        // transition makes the list feel like it is lagging behind the finger.
        transition: anyDragging ? 'none' : 'background .15s',
      }}
    >
      {canEdit && (
        <button
          {...handleProps}
          onKeyDown={(e) => {
            if (e.key === 'ArrowUp') { e.preventDefault(); onMove(-1) }
            else if (e.key === 'ArrowDown') { e.preventDefault(); onMove(1) }
          }}
          title="Drag to move — or use the arrow keys"
          aria-label={`Move ${p.name} in the batting order`}
          data-grip
          className="shrink-0 w-8 h-9 flex items-center justify-center rounded text-pb-dim hover:text-pb-text focus:outline-none focus:text-pb-accent cursor-grab"
        >
          <Icon name="grip" size={17} />
        </button>
      )}
      {/* --pb-dim, never --pb-faintest: this app's palest token computes to
          1.64:1 against the surface, and a batting position is read off an
          iPad on a fence from several metres away. */}
      <span className="font-mono text-[11px] w-5 shrink-0 text-right" style={{ color: inNet ? 'var(--pb-accent)' : 'var(--pb-dim)' }}>{i + 1}</span>
      <Avatar player={{ ...p, id: p.player_id }} size={30} />
      <div className="flex-1 min-w-[140px]">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="font-display font-medium text-[13.5px] truncate max-w-full">{p.name}</span>
          {p.is_guest && <span className="font-mono text-[9px] text-pb-faint">GUEST</span>}
          {inNet && <Tag color="var(--pb-accent)">NET {i + 1}</Tag>}
          {p.padding_up && !inNet && <Tag color="var(--pb-positive)">PADDING UP</Tag>}
          {p.priority && <Tag color="var(--pb-amber)">PRIORITY</Tag>}
        </div>
        {p.note && <div className="text-[11px] text-pb-faint truncate">{p.note}</div>}
      </div>
      {canEdit && (
        <div className="flex items-center gap-0.5 text-pb-faint ml-auto">
          <RowBtn on={p.padding_up} color="var(--pb-positive)" icon="padUp" onClick={onPadUp}
            title={p.padding_up ? 'Not padding up after all' : 'Padding up — tell everyone they’re next in'} />
          <RowBtn on={p.priority} color="var(--pb-amber)" icon="flag" onClick={onPriority}
            title={p.priority ? 'Clear priority' : 'Priority — needs to bat early tonight'} />
          <RowBtn icon="batNext" onClick={onBatNext} title="Bat next" />
          <RowBtn icon="batDone" onClick={onBatted} title="Mark as batted" />
          <RowBtn icon="batNotOut" color="var(--pb-amber)" onClick={onSitOut} title="Not batting — here tonight, but out of the rotation" />
          <RowBtn icon="close" color="var(--pb-red)" onClick={onRemove} title="Remove" />
        </div>
      )}
    </div>
  )
}

/* A row action. 34px square rather than the 24 a bare `p-1` gives, because
 * every one of these is tapped with a thumb on a tablet in the dark. */
function RowBtn({ icon, title, onClick, on = false, color }) {
  return (
    <button
      onClick={onClick}
      title={title}
      aria-label={title}
      aria-pressed={color && on ? true : undefined}
      className="w-[34px] h-[34px] flex items-center justify-center rounded-lg shrink-0"
      style={on ? { color, background: `color-mix(in srgb, ${color} 16%, transparent)` } : undefined}
    >
      <Icon name={icon} size={icon === 'close' ? 15 : 16} />
    </button>
  )
}

function Tag({ color, children }) {
  return (
    <span className="font-mono text-[9px] uppercase tracking-wide2 px-1.5 py-[1px] rounded shrink-0"
      style={{ color, background: `color-mix(in srgb, ${color} 14%, transparent)` }}>
      {children}
    </span>
  )
}

/* ── What the row buttons mean ────────────────────────────────────────────────
 * The order's controls are small glyphs on a crowded row, and three of them are
 * bats doing different things. Spelling them out once above the list beats a
 * coach discovering them by tapping — and it costs a line, which is why it can
 * be put away. */
const ROW_KEY = [
  { icon: 'grip', label: 'Drag to move' },
  { icon: 'padUp', label: 'Padding up' },
  { icon: 'flag', label: 'Priority' },
  { icon: 'batNext', label: 'Bat next' },
  { icon: 'batDone', label: 'Mark as batted' },
  { icon: 'batNotOut', label: 'Not batting' },
  { icon: 'close', label: 'Remove' },
]
function RowKey() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 mb-2.5 px-2.5 py-2 rounded-lg bg-pb-surface2/50">
      {ROW_KEY.map((k) => (
        <span key={k.icon} className="inline-flex items-center gap-1.5 text-[11.5px] text-pb-faint">
          <Icon name={k.icon} size={15} />
          {k.label}
        </span>
      ))}
    </div>
  )
}

/* ── Ticking priority asks a question ─────────────────────────────────────────
 * "Needs to bat early" and "put them there" are two different acts, and the
 * flag deliberately does not do the second on its own. A tick that silently
 * re-sorted the order would undo the order the coach had just dragged into
 * place, and with three captains flagged on a selection night nobody could say
 * who was actually first. So the coach chooses, every time: move them up now,
 * or mark it and deal with it when the current turn ends.
 *
 * The reason goes into the attendee's existing note — the field that already
 * holds what somebody said on the way in, which is exactly the same sentence.
 * It opens pre-filled with whatever is already there so a "bowling only" typed
 * at check-in can't be quietly written over. */
function PriorityModal({ person, netsBusy, onClose, onSave }) {
  const [reason, setReason] = useState(person.note || '')
  return (
    <div onClick={onClose} className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 bg-black/60 backdrop-blur-sm">
      <div onClick={(e) => e.stopPropagation()} className="w-full sm:w-[420px] bg-pb-surface sm:rounded-2xl rounded-t-2xl border border-pb-hairline2 overflow-hidden shadow-2xl">
        <div className="flex items-start gap-3 px-4 py-3.5 border-b pb-hairline">
          <div className="flex-1">
            <div className="font-mono text-[10px] uppercase tracking-wide3" style={{ color: 'var(--pb-amber)' }}>Priority</div>
            <div className="font-display font-bold text-[16px]">{person.name}</div>
          </div>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text p-1"><Icon name="close" size={18} /></button>
        </div>
        <div className="px-4 py-3.5 flex flex-col gap-3">
          <label className="flex flex-col gap-1.5">
            <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Why (optional)</span>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={120}
              autoFocus
              placeholder="Leaving at 7 / captain, selection night"
              className="bg-pb-surface2 border border-pb-hairline rounded-lg px-3 h-[38px] text-sm focus:outline-none focus:border-pb-accent"
            />
          </label>
          <div className="flex flex-col gap-2">
            <Btn variant="primary" icon="batNext" onClick={() => onSave({ reason, batNext: true })}>
              Bat next
            </Btn>
            <Btn variant="soft" icon="flag" onClick={() => onSave({ reason, batNext: false })}>
              Just flag them
            </Btn>
          </div>
          <p className="text-[12px] text-pb-faint leading-snug">
            <b className="text-pb-dim">Bat next</b> moves them to the front of the line
            {netsBusy ? ', behind whoever is in the nets right now.' : '.'}{' '}
            <b className="text-pb-dim">Just flag them</b> leaves the order alone and marks the row, so
            you can move them up when it suits.
          </p>
        </div>
      </div>
    </div>
  )
}

/* ── Live indicator ───────────────────────────────────────────────────────────
 * Says out loud that this screen is one of possibly several on the session, so
 * a coach seeing the queue change under them knows why. */
function LiveDot({ ended = false }) {
  if (ended) {
    return (
      <span className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest"
        title="This session is finished. Nobody can check in to it, including from the QR code.">
        <span className="w-1.5 h-1.5 rounded-full bg-pb-faintest" /> Ended
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide2 text-pb-faint"
      title="This session updates live on every device it's open on">
      <span className="w-1.5 h-1.5 rounded-full bg-pb-accent animate-pulse" /> Live
    </span>
  )
}

/* ── Check-in modal ───────────────────────────────────────────────────────────
 * Every name the club holds is reachable from here, and that is the point.
 *
 * This list used to be the same pool the availability screens use, which drops
 * anyone who hasn't played inside the club's dormancy window — so a player who
 * reads as active on Admin → Players simply wasn't here, with nothing on screen
 * saying why, and the only way to record them was as a guest under their own
 * name. Reported from a club's Thursday nets.
 *
 * The current squad still comes first, because that's who turns up week to
 * week. Everyone else sits under their own heading, and searching reaches the
 * whole club — so the answer to "why can't I find him" is never "you can't". */
function CheckInModal({ roster, inSession, onAdd, onGuest, onClose }) {
  const [q, setQ] = useState('')
  const [guest, setGuest] = useState('')
  const [showAll, setShowAll] = useState(false)

  const { squad, others } = useMemo(() => {
    const t = q.trim().toLowerCase()
    const hit = (p) => !t || (p.name || '').toLowerCase().includes(t)
    const inSquad = (p) => !p.dormant && !p.inactive
    return {
      squad: roster.filter((p) => hit(p) && inSquad(p)),
      others: roster.filter((p) => hit(p) && !inSquad(p)),
    }
  }, [roster, q])

  // A search is someone looking for a specific person, so it always reaches
  // past the squad; with no search, the rest are one tap away.
  const searching = q.trim().length > 0
  const showOthers = searching || showAll

  return (
    <div onClick={onClose} className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 bg-black/60 backdrop-blur-sm">
      <div onClick={(e) => e.stopPropagation()} className="w-full sm:w-[460px] max-h-[88vh] bg-pb-surface sm:rounded-2xl rounded-t-2xl border border-pb-hairline2 overflow-hidden shadow-2xl flex flex-col">
        <div className="flex items-center gap-3 px-4 py-3.5 border-b pb-hairline">
          <div className="flex-1">
            <div className="font-mono text-[10px] uppercase tracking-wide3 text-pb-accent">Check in</div>
            <div className="font-display font-bold text-[16px]">Add players to the nets</div>
          </div>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text p-1"><Icon name="close" size={18} /></button>
        </div>
        <div className="px-4 py-3 border-b pb-hairline">
          <Search value={q} onChange={setQ} placeholder="Search every player at the club…" />
        </div>
        <div className="flex-1 overflow-y-auto px-2 py-1">
          {squad.length === 0 && (!showOthers || others.length === 0) ? (
            <Empty className="px-3 py-6 text-center">
              {searching ? 'Nobody by that name — add them as a guest below.' : 'No players on the roster yet.'}
            </Empty>
          ) : (
            <>
              {squad.map((p) => <RosterRow key={p.id} p={p} on={inSession.has(p.id)} onAdd={onAdd} />)}

              {!showOthers && others.length > 0 && (
                <button onClick={() => setShowAll(true)}
                  className="w-full px-2.5 py-2.5 mt-1 text-left text-[12.5px] text-pb-faint hover:text-pb-accent">
                  + Show {others.length} more player{others.length === 1 ? '' : 's'} (not played recently, or marked inactive)
                </button>
              )}

              {showOthers && others.length > 0 && (
                <>
                  <div className="px-2.5 pt-3 pb-1 font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest">
                    Not in the current squad
                  </div>
                  {others.map((p) => <RosterRow key={p.id} p={p} on={inSession.has(p.id)} onAdd={onAdd} />)}
                </>
              )}
            </>
          )}
        </div>
        <div className="px-4 py-3 border-t pb-hairline flex items-center gap-2">
          <input value={guest} onChange={(e) => setGuest(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { onGuest(guest); setGuest('') } }}
            placeholder="Add a guest (trialist / junior)…"
            className="flex-1 bg-pb-surface2 border border-pb-hairline rounded-lg px-3 h-[38px] text-sm focus:outline-none focus:border-pb-accent" />
          <Btn variant="soft" sm icon="plus" onClick={() => { onGuest(guest); setGuest('') }} disabled={!guest.trim()}>Guest</Btn>
        </div>
      </div>
    </div>
  )
}

/* One name on the check-in list. A player outside the current squad is tagged
 * with why rather than hidden — a coach can then tell "he's had a season off"
 * from "wrong person". */
function RosterRow({ p, on, onAdd }) {
  const tag = p.inactive ? 'INACTIVE' : p.dormant ? 'NOT PLAYED RECENTLY' : null
  return (
    <button onClick={() => onAdd(p)} className="w-full flex items-center gap-3 px-2.5 py-2 rounded-lg hover:bg-pb-surface2/60 text-left">
      <Avatar player={p} size={32} noLink />
      <div className="flex-1 min-w-0">
        <div className="font-display font-medium text-[13.5px] truncate">
          {p.name}
          {tag && <span className="font-mono text-[9px] text-pb-faintest ml-1.5">{tag}</span>}
        </div>
        <RoleChips roles={(p.skill_positions || []).slice(0, 3)} muted />
      </div>
      <span className={`inline-flex items-center justify-center w-7 h-7 rounded-full shrink-0 ${on ? 'bg-pb-accent text-[#08110b]' : 'border border-pb-hairline2 text-pb-faint'}`}>
        <Icon name={on ? 'check' : 'plus'} size={15} />
      </span>
    </button>
  )
}
