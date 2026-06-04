// BetterSelect → Net Manager (live runner). The pitch-side screen the net
// manager drives on one device: check players in, queue them, and run a batting
// timer that rotates a group of N batters through the nets with staged audible
// alerts. All the live state (queue order, who's on, the countdown) is held in
// the browser — only the durable snapshot (who turned up, who batted) is synced
// back so the attendance reports and player profiles fill in.
import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { PbSpinner } from '../../../lib/presskit'
import { Icon, Btn, Avatar, RoleChips, Search, Empty } from './ui'

let _uid = 0
const uid = () => `g-${++_uid}-${Math.random().toString(36).slice(2, 6)}`
const TONE_COLOR = { info: 'var(--pb-accent)', amber: 'var(--pb-amber)', red: 'var(--pb-red)' }
const clock = (t) => { const s = Math.max(0, Math.round(t)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}` }
const fmtDate = (d) => { try { return new Date(d + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'short' }) } catch { return d || '' } }

const toItem = (a) => ({
  key: a.player_id || uid(),
  player_id: a.player_id || null,
  guest_name: a.guest_name || null,
  name: a.name,
  photo_url: a.photo_url || null,
  skill_positions: a.skill_positions || [],
})

export default function NetSession() {
  const { id } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const { hasCapability } = useAuth()
  const canEdit = hasCapability(CAP.MANAGE_SELECTIONS)

  const [session, setSession] = useState(null)
  const [roster, setRoster] = useState([])
  const [settings, setSettings] = useState(null)
  const [queue, setQueue] = useState([])     // ordered; first `nets` are "on now"
  const [batted, setBatted] = useState([])   // completed a turn this session

  // Timer
  const [remaining, setRemaining] = useState(0)
  const [running, setRunning] = useState(false)
  const [banner, setBanner] = useState(null)     // { label, tone } most-recent alert
  const [activeTone, setActiveTone] = useState(null)
  const [turnOver, setTurnOver] = useState(false)
  const [checkInOpen, setCheckInOpen] = useState(false)

  const deadlineRef = useRef(null)
  const firedRef = useRef(new Set())
  const settingsRef = useRef(settings)
  const queueRef = useRef(queue)
  const audioRef = useRef(null)
  useEffect(() => { settingsRef.current = settings }, [settings])
  useEffect(() => { queueRef.current = queue }, [queue])

  // ── Load ────────────────────────────────────────────────────────────────
  useEffect(() => {
    let alive = true
    Promise.all([
      api.nmGetSession(id),
      api.nmRoster().then((r) => r.players || []).catch(() => []),
    ]).then(([s, rs]) => {
      if (!alive) return
      setSession(s)
      setRoster(rs)
      setSettings(s.settings)
      setRemaining(s.settings.duration_seconds)
      const items = (s.attendees || []).map(toItem)
      setQueue(items.filter((_, i) => !s.attendees[i].batted))
      setBatted(items.filter((_, i) => s.attendees[i].batted))
    }).catch((e) => { toast.error(e.message); setSession(false) })
    return () => { alive = false }
  }, [id, toast])

  // ── Persist attendance snapshot (debounced) ───────────────────────────────
  const firstSave = useRef(true)
  useEffect(() => {
    if (firstSave.current) { firstSave.current = false; return }
    if (!canEdit) return
    const snap = [
      ...queue.map((q, i) => ({ player_id: q.player_id, guest_name: q.guest_name, batted: false, position: i })),
      ...batted.map((q, i) => ({ player_id: q.player_id, guest_name: q.guest_name, batted: true, position: queue.length + i })),
    ]
    const t = setTimeout(() => { api.nmSetAttendance(id, snap).catch(() => {}) }, 700)
    return () => clearTimeout(t)
  }, [queue, batted, id, canEdit])

  // ── Audio ─────────────────────────────────────────────────────────────────
  const unlockAudio = () => {
    if (!settingsRef.current?.sound) return
    try {
      if (!audioRef.current) audioRef.current = new (window.AudioContext || window.webkitAudioContext)()
      if (audioRef.current.state === 'suspended') audioRef.current.resume()
    } catch { /* no audio */ }
  }
  const beep = (tone) => {
    if (!settingsRef.current?.sound || !audioRef.current) return
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
  }

  // ── Timer engine ──────────────────────────────────────────────────────────
  const begin = useCallback((secs) => {
    unlockAudio()
    const s = secs != null ? secs : remaining
    if (s <= 0) return
    deadlineRef.current = Date.now() + s * 1000
    setRemaining(s)
    setTurnOver(false)
    setRunning(true)
  }, [remaining])

  const resetTimer = useCallback(() => {
    firedRef.current = new Set()
    setBanner(null); setActiveTone(null); setTurnOver(false)
    setRemaining(settingsRef.current?.duration_seconds || 0)
    setRunning(false)
  }, [])

  const rotate = useCallback((autostart) => {
    const q = queueRef.current
    const n = settingsRef.current?.nets || 1
    const group = q.slice(0, n)
    if (group.length) {
      setBatted((b) => [...b, ...group])
      setQueue(q.slice(n))
    }
    firedRef.current = new Set()
    setBanner(null); setActiveTone(null); setTurnOver(false)
    const dur = settingsRef.current?.duration_seconds || 0
    // Only keep the clock rolling if batters remain after this rotation.
    if (autostart && (q.length - n) > 0 && dur > 0) { begin(dur) }
    else { setRemaining(dur); setRunning(false) }
  }, [begin])

  const handleEnd = useCallback(() => {
    setRunning(false); setRemaining(0)
    beep('red')
    setBanner({ label: 'Time — rotate to the next group', tone: 'red' }); setActiveTone('red')
    if (settingsRef.current?.auto_roll) setTimeout(() => rotate(true), 400)
    else setTurnOver(true)
  }, [rotate])

  useEffect(() => {
    if (!running) return
    const iv = setInterval(() => {
      const rem = (deadlineRef.current - Date.now()) / 1000
      if (rem <= 0) { clearInterval(iv); handleEnd(); return }
      setRemaining(rem)
      const alerts = settingsRef.current?.alerts || []
      alerts.forEach((a, i) => {
        if (!firedRef.current.has(i) && rem <= a.seconds_remaining) {
          firedRef.current.add(i)
          setBanner(a); setActiveTone(a.tone); beep(a.tone)
        }
      })
    }, 200)
    return () => clearInterval(iv)
  }, [running, handleEnd])

  // ── Queue ops ─────────────────────────────────────────────────────────────
  const inSession = useMemo(() => {
    const s = new Set()
    queue.forEach((q) => q.player_id && s.add(q.player_id))
    batted.forEach((q) => q.player_id && s.add(q.player_id))
    return s
  }, [queue, batted])

  const addPlayer = (p) => {
    if (p.id && inSession.has(p.id)) { setQueue((q) => q.filter((x) => x.player_id !== p.id)); return }
    setQueue((q) => [...q, toItem({ player_id: p.id, name: p.name, photo_url: p.photo_url, skill_positions: p.skill_positions })])
  }
  const addGuest = (name) => {
    const n = name.trim(); if (!n) return
    setQueue((q) => [...q, { key: uid(), player_id: null, guest_name: n, name: n, photo_url: null, skill_positions: [] }])
  }
  const removeFromQueue = (key) => setQueue((q) => q.filter((x) => x.key !== key))
  const move = (key, dir) => setQueue((q) => {
    const i = q.findIndex((x) => x.key === key); if (i < 0) return q
    const j = i + dir; if (j < 0 || j >= q.length) return q
    const cp = q.slice();[cp[i], cp[j]] = [cp[j], cp[i]]; return cp
  })
  const bumpToFront = (key) => setQueue((q) => { const it = q.find((x) => x.key === key); return it ? [it, ...q.filter((x) => x.key !== key)] : q })
  const retire = (key) => setQueue((q) => {
    const it = q.find((x) => x.key === key); if (!it) return q
    setBatted((b) => [...b, it]); return q.filter((x) => x.key !== key)
  })
  const unbat = (key) => setBatted((b) => { const it = b.find((x) => x.key === key); if (it) setQueue((q) => [...q, it]); return b.filter((x) => x.key !== key) })

  // ── Live settings tweaks (persisted to the session) ───────────────────────
  const patchSettings = (partial) => {
    setSettings((cur) => {
      const next = { ...cur, ...partial }
      api.nmUpdateSession(id, { settings: next }).catch(() => {})
      if (partial.duration_seconds != null && !running) setRemaining(partial.duration_seconds)
      return next
    })
  }

  if (session === null || !settings) return <BetterSelectLayout title="Net session"><PbSpinner message="Loading session…" /></BetterSelectLayout>
  if (session === false) return <BetterSelectLayout title="Net session"><div className="pb-card px-5 py-10 text-center"><Empty>Session not found.</Empty><div className="mt-3"><Btn variant="ghost" sm icon="back" onClick={() => navigate('/admin/betterselect/nets')}>Back to sessions</Btn></div></div></BetterSelectLayout>

  const nets = settings.nets
  const onNow = queue.slice(0, nets)
  const upNext = queue.slice(nets)
  const timerColor = activeTone ? TONE_COLOR[activeTone] : 'var(--pb-text)'
  const pct = settings.duration_seconds ? Math.max(0, Math.min(100, (remaining / settings.duration_seconds) * 100)) : 0

  return (
    <BetterSelectLayout
      title="Net session"
      actions={<Btn variant="ghost" sm icon="back" onClick={() => navigate('/admin/betterselect/nets')}>Sessions</Btn>}
    >
      <div className="flex flex-col gap-4">
        {/* Session header */}
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <div className="font-display font-bold text-[20px] leading-tight">{session.label || 'Net session'}</div>
            <div className="text-[13px] text-pb-faint">{fmtDate(session.session_date)} · {queue.length + batted.length} checked in · {batted.length} batted</div>
          </div>
          {canEdit && <Btn variant="primary" icon="plus" onClick={() => setCheckInOpen(true)}>Check in players</Btn>}
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
            {turnOver && !running && <div className="mt-3 text-[13px] text-pb-faint">Turn over — hit <b className="text-pb-text">Next group</b> to rotate.</div>}

            {/* Controls */}
            {canEdit && (
              <div className="flex flex-wrap items-center justify-center gap-2.5 mt-5">
                {!running
                  ? <Btn variant="primary" icon="play" onClick={() => begin()} disabled={remaining <= 0}>Start</Btn>
                  : <Btn variant="soft" icon="pause" onClick={() => setRunning(false)}>Pause</Btn>}
                <Btn variant="ghost" icon="reset" onClick={resetTimer}>Reset</Btn>
                <Btn variant="ghost" icon="next" onClick={() => rotate(true)} disabled={!onNow.length}>Next group</Btn>
              </div>
            )}
          </div>

          {/* Quick session settings */}
          {canEdit && (
            <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2 px-5 py-3 border-t pb-hairline text-[12.5px] text-pb-faint">
              <label className="inline-flex items-center gap-1.5">Nets
                <input type="number" min="1" max="8" value={nets} onChange={(e) => patchSettings({ nets: Math.max(1, Math.min(8, Number(e.target.value) || 1)) })}
                  className="w-12 bg-pb-surface2 border border-pb-hairline rounded px-1.5 h-7 text-center text-pb-text focus:outline-none focus:border-pb-accent" />
              </label>
              <label className="inline-flex items-center gap-1.5">Minutes
                <input type="number" min="1" max="60" value={Math.round(settings.duration_seconds / 60)} onChange={(e) => patchSettings({ duration_seconds: Math.max(30, (Number(e.target.value) || 1) * 60) })}
                  className="w-12 bg-pb-surface2 border border-pb-hairline rounded px-1.5 h-7 text-center text-pb-text focus:outline-none focus:border-pb-accent" />
              </label>
              <button onClick={() => patchSettings({ auto_roll: !settings.auto_roll })} className={`inline-flex items-center gap-1.5 ${settings.auto_roll ? 'text-pb-accent' : ''}`}>
                <Icon name={settings.auto_roll ? 'check' : 'reset'} size={14} /> Auto-roll {settings.auto_roll ? 'on' : 'off'}
              </button>
              <button onClick={() => patchSettings({ sound: !settings.sound })} className={`inline-flex items-center gap-1.5 ${settings.sound ? 'text-pb-accent' : ''}`}>
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
                <div key={p.key} className="pb-card px-3.5 py-3 flex items-center gap-3" style={{ borderColor: 'color-mix(in srgb, var(--pb-accent) 30%, transparent)' }}>
                  <span className="font-mono text-[11px] text-pb-accent w-5 shrink-0">N{i + 1}</span>
                  <Avatar player={p} size={38} />
                  <div className="flex-1 min-w-0">
                    <div className="font-display font-semibold text-[14px] truncate">{p.name}{p.player_id ? '' : ' '}{!p.player_id && <span className="font-mono text-[9px] text-pb-faint ml-1">GUEST</span>}</div>
                    <RoleChips roles={(p.skill_positions || []).slice(0, 3)} muted />
                  </div>
                  {canEdit && <Btn variant="ghost" sm icon="check" onClick={() => retire(p.key)} title="Mark done / next in">Out</Btn>}
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
                  <div key={p.key} className="flex items-center gap-2.5 py-2 border-b pb-hairline last:border-0">
                    <span className="font-mono text-[11px] text-pb-faintest w-5 shrink-0">{i + 1}</span>
                    <Avatar player={p} size={30} />
                    <div className="flex-1 min-w-0">
                      <div className="font-display font-medium text-[13.5px] truncate">{p.name}{!p.player_id && <span className="font-mono text-[9px] text-pb-faint ml-1">GUEST</span>}</div>
                    </div>
                    {canEdit && (
                      <div className="flex items-center gap-0.5 text-pb-faint">
                        <button onClick={() => bumpToFront(p.key)} title="Bat next" className="p-1 hover:text-pb-accent"><Icon name="bolt" size={15} /></button>
                        <button onClick={() => move(p.key, -1)} title="Up" className="p-1 hover:text-pb-text"><Icon name="chevron" size={15} className="-rotate-90" /></button>
                        <button onClick={() => move(p.key, 1)} title="Down" className="p-1 hover:text-pb-text"><Icon name="chevron" size={15} className="rotate-90" /></button>
                        <button onClick={() => removeFromQueue(p.key)} title="Remove" className="p-1 hover:text-pb-red"><Icon name="close" size={15} /></button>
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
              <span className="font-mono text-[11px] text-pb-accent">{batted.length} batted</span>
            </div>
            {batted.length === 0 ? <Empty className="py-3">No completed turns yet.</Empty> : (
              <div className="flex flex-col">
                {batted.map((p) => (
                  <div key={p.key} className="flex items-center gap-2.5 py-2 border-b pb-hairline last:border-0">
                    <Avatar player={p} size={26} />
                    <span className="flex-1 min-w-0 text-[13px] text-pb-dim truncate">{p.name}</span>
                    <Icon name="check" size={15} className="text-pb-accent" />
                    {canEdit && <button onClick={() => unbat(p.key)} title="Back to queue" className="p-1 text-pb-faint hover:text-pb-text"><Icon name="reset" size={14} /></button>}
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
