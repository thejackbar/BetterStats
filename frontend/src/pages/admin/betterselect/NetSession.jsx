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
import { Icon, Btn, Avatar, RoleChips, Search, Empty, NumText } from './ui'

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
  const [checkInOpen, setCheckInOpen] = useState(false)
  const [banner, setBanner] = useState(null)   // most recent alert, this device
  const [activeTone, setActiveTone] = useState(null)
  // Who has just scanned themselves in, for the pop-up. Names only — this is a
  // notice, not a second copy of the queue.
  const [arrivals, setArrivals] = useState([])
  const [audioReady, setAudioReady] = useState(false)
  const [tick, setTick] = useState(() => Date.now())

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
    ]).then(([s, rs]) => {
      if (!alive) return
      setRoster(rs)
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
  const attendees = (live && live.attendees) || []
  const waiting = useMemo(() => attendees.filter((a) => !a.batted), [attendees])
  const done = useMemo(() => attendees.filter((a) => a.batted), [attendees])
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
  const move = (attId, dir) => {
    const ids = waiting.map((a) => a.id)
    const i = ids.indexOf(attId)
    const j = i + dir
    if (i < 0 || j < 0 || j >= ids.length) return
    ;[ids[i], ids[j]] = [ids[j], ids[i]]
    reorder(ids)
  }
  const bumpToFront = (attId) => reorder([attId, ...waiting.map((a) => a.id).filter((x) => x !== attId)])
  const setBatted = (attId, batted) => act(() => api.nmPatchAttendee(id, attId, { batted }))
  const removeAttendee = (attId) => act(() => api.nmRemoveAttendee(id, attId))

  const start = () => { unlockAudio(); act(() => api.nmTimer(id, 'start')) }
  const pause = () => act(() => api.nmTimer(id, 'pause'))
  const resetTimer = () => act(() => api.nmTimer(id, 'reset'))
  const rotate = () => { unlockAudio(); act(() => api.nmRotate(id, true, timer && timer.turn_seq)) }

  const patchSettings = (partial) => act(() => api.nmUpdateSession(id, { settings: { ...settings, ...partial } }))

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

  const nets = settings.nets
  const onNow = waiting.slice(0, nets)
  const upNext = waiting.slice(nets)
  const timerColor = activeTone ? TONE_COLOR[activeTone] : 'var(--pb-text)'
  const pct = settings.duration_seconds ? Math.max(0, Math.min(100, (remaining / settings.duration_seconds) * 100)) : 0
  const turnOver = !running && remaining <= 0 && onNow.length > 0

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
            <div className="text-[13px] text-pb-faint">{fmtDate(live.session_date)} · {attendees.length} checked in · {done.length} batted</div>
          </div>
          <div className="flex items-center gap-2">
            <LiveDot />
            <Btn variant="ghost" sm icon="download" href={api.nmSessionCsvUrl(id)} title="Download the attendance list for this session">List</Btn>
            {canEdit && <Btn variant="primary" icon="plus" onClick={() => { unlockAudio(); setCheckInOpen(true) }}>Check in players</Btn>}
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

            {/* Controls */}
            {canEdit && (
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

        {/* On now */}
        <div>
          <div className="flex items-center gap-2 mb-2"><span className="font-display font-bold text-[15px]">On now</span><span className="font-mono text-[11px] text-pb-faint">{onNow.length}/{nets} nets</span></div>
          {onNow.length === 0 ? (
            <div className="pb-card px-4 py-8 text-center"><Empty>No one batting yet. Check players in, then hit Start.</Empty></div>
          ) : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {onNow.map((p, i) => (
                <div key={p.id} className="pb-card px-3.5 py-3 flex items-center gap-3" style={{ borderColor: 'color-mix(in srgb, var(--pb-accent) 30%, transparent)' }}>
                  <span className="font-mono text-[11px] text-pb-accent w-5 shrink-0">N{i + 1}</span>
                  <Avatar player={{ ...p, id: p.player_id }} size={38} />
                  <div className="flex-1 min-w-0">
                    <div className="font-display font-semibold text-[14px] truncate">{p.name}{p.is_guest && <span className="font-mono text-[9px] text-pb-faint ml-1">GUEST</span>}</div>
                    <RoleChips roles={(p.skill_positions || []).slice(0, 3)} muted />
                  </div>
                  {canEdit && <Btn variant="ghost" sm icon="check" onClick={() => setBatted(p.id, true)} title="Mark done / next in">Out</Btn>}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Up next + Done */}
        <div className="grid lg:grid-cols-[1fr_320px] gap-4 items-start">
          <div className="pb-card px-4 py-3.5">
            <div className="flex items-center justify-between mb-1.5">
              <span className="font-display font-bold text-[15px]">Up next</span>
              <span className="font-mono text-[11px] text-pb-faint">{upNext.length} waiting</span>
            </div>
            {upNext.length === 0 ? <Empty className="py-3">Queue is empty.</Empty> : (
              <div className="flex flex-col">
                {upNext.map((p, i) => (
                  <div key={p.id} className="flex items-center gap-2.5 py-2 border-b pb-hairline last:border-0">
                    <span className="font-mono text-[11px] text-pb-faintest w-5 shrink-0">{i + 1}</span>
                    <Avatar player={{ ...p, id: p.player_id }} size={30} />
                    <div className="flex-1 min-w-0">
                      <div className="font-display font-medium text-[13.5px] truncate">{p.name}{p.is_guest && <span className="font-mono text-[9px] text-pb-faint ml-1">GUEST</span>}</div>
                    </div>
                    {canEdit && (
                      <div className="flex items-center gap-0.5 text-pb-faint">
                        <button onClick={() => bumpToFront(p.id)} title="Bat next" className="p-1 hover:text-pb-accent"><Icon name="bolt" size={15} /></button>
                        <button onClick={() => move(p.id, -1)} title="Up" className="p-1 hover:text-pb-text"><Icon name="chevron" size={15} className="-rotate-90" /></button>
                        <button onClick={() => move(p.id, 1)} title="Down" className="p-1 hover:text-pb-text"><Icon name="chevron" size={15} className="rotate-90" /></button>
                        <button onClick={() => removeAttendee(p.id)} title="Remove" className="p-1 hover:text-pb-red"><Icon name="close" size={15} /></button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="pb-card px-4 py-3.5">
            <div className="flex items-center justify-between mb-1.5">
              <span className="font-display font-bold text-[15px]">Done</span>
              <span className="font-mono text-[11px] text-pb-accent">{done.length} batted</span>
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
        </div>
      </div>

      {checkInOpen && (
        <CheckInModal roster={roster} inSession={inSession} onAdd={addPlayer} onGuest={addGuest} onClose={() => setCheckInOpen(false)} />
      )}
    </BetterSelectLayout>
  )
}

/* ── Live indicator ───────────────────────────────────────────────────────────
 * Says out loud that this screen is one of possibly several on the session, so
 * a coach seeing the queue change under them knows why. */
function LiveDot() {
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide2 text-pb-faint"
      title="This session updates live on every device it's open on">
      <span className="w-1.5 h-1.5 rounded-full bg-pb-accent animate-pulse" /> Live
    </span>
  )
}

/* ── Check-in modal ───────────────────────────────────────────────────────── */
function CheckInModal({ roster, inSession, onAdd, onGuest, onClose }) {
  const [q, setQ] = useState('')
  const [guest, setGuest] = useState('')
  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase()
    return roster.filter((p) => !t || (p.name || '').toLowerCase().includes(t))
  }, [roster, q])

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
          <Search value={q} onChange={setQ} placeholder="Search the roster…" />
        </div>
        <div className="flex-1 overflow-y-auto px-2 py-1">
          {filtered.length === 0 ? <Empty className="px-3 py-6 text-center">No matching players.</Empty> : filtered.map((p) => {
            const on = inSession.has(p.id)
            return (
              <button key={p.id} onClick={() => onAdd(p)} className="w-full flex items-center gap-3 px-2.5 py-2 rounded-lg hover:bg-pb-surface2/60 text-left">
                <Avatar player={p} size={32} noLink />
                <div className="flex-1 min-w-0">
                  <div className="font-display font-medium text-[13.5px] truncate">{p.name}</div>
                  <RoleChips roles={(p.skill_positions || []).slice(0, 3)} muted />
                </div>
                <span className={`inline-flex items-center justify-center w-7 h-7 rounded-full shrink-0 ${on ? 'bg-pb-accent text-[#08110b]' : 'border border-pb-hairline2 text-pb-faint'}`}>
                  <Icon name={on ? 'check' : 'plus'} size={15} />
                </span>
              </button>
            )
          })}
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
