// BetterSelect → Net Manager, time-slot mode. A session set to "automatic" runs
// as a GRID instead of a queue and a timer: each net is a column, each row a time
// slot, and a player is placed in a cell of their squad's net as they check in.
//
// The server owns the plan and the placement (services/net_slots.py, the
// /nets/sessions/:id/plan and /slots routes). This screen draws what the server
// derived and sends small writes: move a name, mark it done, set someone out.
// Clock times and "now" come from the plan's absolute start time, so a phone set
// to the wrong timezone still shows the same row as the laptop.
//
// Moving a name: drag the grip with a pointer, or tap a name to pick it up and
// tap a cell to drop it. Both are here because iOS Safari fires no HTML5 drag
// events and a finger on a scrolling grid needs a way that is not a drag.
import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import { Icon, Btn, Avatar, Chip, Empty, NumText } from './ui'

// '16:45' -> '4:45'. The club's own sheet writes times this way, no am/pm.
export const fmtSlot = (hhmm) => {
  if (!hhmm) return ''
  const [h, m] = hhmm.split(':').map(Number)
  return `${h % 12 || 12}:${String(m).padStart(2, '0')}`
}

const fmtClock = (sec) => {
  const t = Math.max(0, Math.ceil(sec))
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), r = t % 60
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}` : `${m}:${String(r).padStart(2, '0')}`
}

// Where the night is, from the plan's absolute start and the server's slot
// offsets: before the first slot, inside slot N with this long left, or over.
// Slots are not all the same length once a coach has moved a time, so this walks
// the cumulative offsets rather than dividing.
export function slotClock(grid, nowMs) {
  if (!grid || !grid.start_at || !grid.offsets || grid.offsets.length < 2) return null
  const start = new Date(grid.start_at).getTime()
  if (Number.isNaN(start)) return null
  const mins = (nowMs - start) / 60000
  const off = grid.offsets
  if (mins < 0) return { state: 'before', slot: -1, untilStart: -mins * 60 }
  if (mins >= off[off.length - 1]) return { state: 'over', slot: off.length - 1 }
  let i = 0
  while (i < off.length - 2 && off[i + 1] <= mins) i += 1
  return { state: 'running', slot: i, remaining: (off[i + 1] - mins) * 60, total: (off[i + 1] - off[i]) * 60 }
}

// The shading. Each state is a tint AND a word, never a tint alone: IN NOW is the
// accent, PAD UP the green the batting queue already uses for it, NEXT a faint
// accent, and a slot that has gone is dimmed.
const STATES = {
  now: { word: 'In now', color: 'var(--pb-accent)', pct: 26 },
  pad: { word: 'Pad up', color: 'var(--pb-positive)', pct: 24 },
  next: { word: 'Next', color: 'var(--pb-accent)', pct: 9 },
}
const tint = (st) => (STATES[st] ? `color-mix(in srgb, ${STATES[st].color} ${STATES[st].pct}%, transparent)` : undefined)

const newNetId = () => `n${Date.now().toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`

/* ── The plan editor ─────────────────────────────────────────────────────── */
export function PlanModal({ plan, squads, onSave, onClose, saving }) {
  const [first, setFirst] = useState(plan.first_time || '')
  const [mins, setMins] = useState(plan.slot_minutes || 7)
  const [finish, setFinish] = useState(plan.finish_time || '')
  const [second, setSecond] = useState(!!plan.second_go)
  const [padUp, setPadUp] = useState(plan.pad_up_seconds ?? 120)
  const [nets, setNets] = useState(() => (plan.nets && plan.nets.length
    ? plan.nets.map((n) => ({ ...n, squad_team_ids: [...(n.squad_team_ids || [])] }))
    : [
      { id: newNetId(), name: 'Net 1', squad_team_ids: [], catch_all: false },
      { id: newNetId(), name: 'Net 2', squad_team_ids: [], catch_all: true },
    ]))

  const setNet = (id, patch) => setNets((cur) => cur.map((n) => (n.id === id ? { ...n, ...patch } : n)))
  // A squad feeds one net: ticking it here takes it off whichever net had it.
  const toggleSquad = (netId, sid) => setNets((cur) => cur.map((n) => {
    if (n.id !== netId) return { ...n, squad_team_ids: n.squad_team_ids.filter((x) => x !== sid) }
    return { ...n, squad_team_ids: n.squad_team_ids.includes(sid) ? n.squad_team_ids.filter((x) => x !== sid) : [...n.squad_team_ids, sid] }
  }))
  const setCatchAll = (netId) => setNets((cur) => cur.map((n) => ({ ...n, catch_all: n.id === netId ? !n.catch_all : false })))
  const addNet = () => setNets((cur) => (cur.length >= 8 ? cur : [...cur, { id: newNetId(), name: `Net ${cur.length + 1}`, squad_team_ids: [], catch_all: false }]))
  const removeNet = (id) => setNets((cur) => cur.filter((n) => n.id !== id))
  const ownerOf = (sid) => nets.find((n) => n.squad_team_ids.includes(sid))

  const problem = !first ? 'Set the time the first net starts.'
    : !nets.length ? 'Add at least one net.'
      : (finish && finish <= first) ? 'The finish has to be after the first net.' : null

  const save = () => {
    if (problem) return
    onSave({
      first_time: first,
      slot_minutes: mins,
      finish_time: finish || null,
      second_go: second,
      pad_up_seconds: padUp,
      // Minutes east of UTC where this was set. The server has no club timezone
      // and needs one to know which slots have already started.
      tz_offset_minutes: -new Date().getTimezoneOffset(),
      nets,
    })
  }

  const field = 'bg-pb-surface2 border border-pb-hairline rounded-lg px-3 h-[38px] text-sm text-pb-text focus:outline-none focus:border-pb-accent'
  const lbl = 'block font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest mb-1'

  return (
    <div onClick={onClose} className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 bg-black/60 backdrop-blur-sm">
      <div onClick={(e) => e.stopPropagation()} data-plan-modal
        className="w-full sm:w-[620px] max-h-[92vh] bg-pb-surface sm:rounded-2xl rounded-t-2xl border border-pb-hairline2 overflow-hidden shadow-2xl flex flex-col">
        <div className="flex items-center gap-3 px-4 py-3.5 border-b pb-hairline">
          <div className="flex-1 min-w-0">
            <div className="font-mono text-[10px] uppercase tracking-wide3 text-pb-accent">Time slots</div>
            <div className="font-display font-bold text-[16px]">Set up the nets</div>
          </div>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text p-1" aria-label="Close"><Icon name="close" size={18} /></button>
        </div>

        <div className="overflow-y-auto px-4 py-4 flex flex-col gap-5">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="min-w-0"><label className={lbl}>First net</label>
              <input type="time" value={first} onChange={(e) => setFirst(e.target.value)} aria-label="First net time" className={`${field} w-full`} /></div>
            <div className="min-w-0"><label className={lbl}>Minutes each</label>
              <NumText value={mins} min={1} max={60} ariaLabel="Minutes each" onCommit={setMins} className={`${field} w-full text-center`} /></div>
            <div className="min-w-0"><label className={lbl}>Nets finish</label>
              <input type="time" value={finish} onChange={(e) => setFinish(e.target.value)} aria-label="Nets finish time" className={`${field} w-full`} /></div>
            <div className="min-w-0"><label className={lbl}>Spare slots</label>
              <button type="button" onClick={() => setSecond((v) => !v)} aria-pressed={second}
                className={`${field} w-full text-left ${second ? 'text-pb-accent border-pb-accent/50' : 'text-pb-dim'}`}>
                {second ? 'Second go on' : 'Second go off'}
              </button></div>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-[120px]"><label className={lbl}>Pad up warning</label>
              <NumText value={padUp} min={0} max={1800} ariaLabel="Pad up warning in seconds" onCommit={setPadUp} className={`${field} w-full text-center`} /></div>
            <div className="text-[12px] text-pb-faint flex-1">
              Seconds before each change that the next batters are told to pad up, with an alarm. 0 turns it off.
            </div>
          </div>
          <div className="text-[12px] text-pb-faint -mt-3">
            Leave the finish blank and the grid just keeps going. With a finish time, anyone who does not fit is flagged. With second go on, free slots at the bottom of a net repeat its order.
          </div>

          <div className="flex flex-col gap-3">
            {nets.map((n, i) => (
              <div key={n.id} className="rounded-xl border border-pb-hairline p-3" data-plan-net>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[11px] text-pb-faint w-5">{i + 1}</span>
                  <input value={n.name} onChange={(e) => setNet(n.id, { name: e.target.value })} aria-label={`Net ${i + 1} name`}
                    className={`${field} flex-1 min-w-0`} />
                  <button onClick={() => removeNet(n.id)} className="p-1.5 text-pb-faint hover:text-pb-red" title="Remove this net" aria-label={`Remove net ${i + 1}`}><Icon name="trash" size={15} /></button>
                </div>
                <div className="flex flex-wrap gap-1.5 mt-2.5">
                  {squads.map((sq) => {
                    const owner = ownerOf(sq.id)
                    const here = owner && owner.id === n.id
                    return (
                      <Chip key={sq.id} label={sq.label} active={!!here}
                        title={owner && !here ? `Currently in ${owner.name}. Ticking it moves it here.` : undefined}
                        className={owner && !here ? 'opacity-50' : ''}
                        onClick={() => toggleSquad(n.id, sq.id)} />
                    )
                  })}
                  <Chip label="Everyone else" active={!!n.catch_all} onClick={() => setCatchAll(n.id)}
                    title="Takes anyone whose squad has no net, and guests" />
                </div>
              </div>
            ))}
            {nets.length < 8 && <div><Btn variant="ghost" sm icon="plus" onClick={addNet}>Add a net</Btn></div>}
            {nets.length > 0 && !nets.some((n) => n.catch_all) && (
              <div className="text-[12px]" style={{ color: 'var(--pb-amber)' }}>
                No net is set to take everyone else. Players whose squad has no net, and guests, will show as not in a net until you place them by hand.
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 px-4 py-3 border-t pb-hairline">
          <div className="flex-1 text-[12.5px]" style={{ color: 'var(--pb-amber)' }}>{problem}</div>
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
          <Btn variant="primary" onClick={save} disabled={!!problem || saving}>{saving ? 'Saving…' : 'Save'}</Btn>
        </div>
      </div>
    </div>
  )
}

/* ── One name in a cell ──────────────────────────────────────────────────── */
function NameChip({ a, repeat, picked, canEdit, onPick, onGrip }) {
  return (
    <div className={`flex items-center gap-1.5 min-w-0 rounded-lg px-1.5 py-1 border ${
      picked ? 'border-pb-accent bg-pb-accent/15' : 'border-transparent'} ${repeat ? 'opacity-55' : ''}`}
    data-name-chip={a.id}>
      {canEdit && !repeat && (
        <span onPointerDown={(e) => onGrip(e, a)} title="Drag to another slot or net" aria-hidden="true"
          className="text-pb-faint cursor-grab shrink-0 flex items-center" style={{ touchAction: 'none' }}>
          <Icon name="grip" size={14} />
        </span>
      )}
      <Avatar player={{ ...a, id: a.player_id }} size={22} noLink />
      <button type="button" onClick={() => onPick(a, repeat)} disabled={!canEdit && !repeat}
        className={`flex-1 min-w-0 text-left truncate text-[13px] ${a.batted ? 'line-through text-pb-faint' : 'text-pb-text'}`}>
        {a.name}
      </button>
      {repeat && <span className="font-mono text-[9px] uppercase tracking-wide2 text-pb-faint shrink-0">2nd go</span>}
      {!repeat && a.is_guest && <span className="font-mono text-[9px] uppercase tracking-wide2 text-pb-faint shrink-0">guest</span>}
    </div>
  )
}

/* ── The grid ────────────────────────────────────────────────────────────── */
export default function NetGrid({ live, canEdit, ended, squads, act, id, holdPoll, skewRef, beep, soundOn, onToggleSound }) {
  const toast = useToast()
  const grid = live.grid
  const plan = live.slot_plan
  const [planOpen, setPlanOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [picked, setPicked] = useState(null)        // attendee id tapped up, waiting for a cell
  const [drag, setDrag] = useState(null)            // {id, name, x, y, over}
  const [tick, setTick] = useState(() => Date.now())
  const dragRef = useRef(null)

  const byId = useMemo(() => new Map((live.attendees || []).map((a) => [a.id, a])), [live.attendees])
  const sitting = useMemo(() => (live.attendees || []).filter((a) => a.bats === false), [live.attendees])
  const noNet = useMemo(() => (grid ? grid.no_net : []).map((x) => byId.get(x)).filter(Boolean), [grid, byId])

  // The clock. Ticks every second (the timer and the alarms read it), derived
  // from the plan's absolute start corrected by the server skew every poll measures.
  const configured = !!(grid && grid.configured)
  useEffect(() => {
    if (!configured) return undefined
    const iv = setInterval(() => setTick(Date.now()), 1000)
    return () => clearInterval(iv)
  }, [configured])
  const clock = useMemo(() => slotClock(grid, tick + (skewRef ? skewRef.current : 0)), [grid, tick, skewRef])
  const nowSlot = clock ? (clock.state === 'running' ? clock.slot : clock.state === 'before' ? -1 : null) : null
  const padUp = (grid && grid.pad_up_seconds) || 0
  // Inside the pad-up window of the change that is coming: before the first slot
  // that is the time left to the start, and inside a slot the time left in it.
  const padWindow = !!clock && padUp > 0 && (clock.state === 'running' ? clock.remaining <= padUp : clock.state === 'before' ? clock.untilStart <= padUp : false)
  const stateOfRow = (i) => {
    if (nowSlot == null) return null
    if (i === nowSlot) return 'now'
    if (i === nowSlot + 1) return padWindow ? 'pad' : 'next'
    return i < nowSlot ? 'past' : null
  }
  const namesAt = (slot) => (grid && grid.nets ? grid.nets : []).map((n) => {
    const c = n.cells[slot]
    const a = c && c.attendee_id ? byId.get(c.attendee_id) : null
    return { id: n.id, net: n.name, who: a ? a.name : null, repeat: !!(c && c.repeat) }
  })
  const listed = (list) => list.filter((x) => x.who).map((x) => `${x.who} (${x.net})`).join(', ') || 'nobody'

  // The alarms, on this device (everyone standing near a screen should hear
  // them). Opening the screen part-way through a window arms it silently, so it
  // does not announce a change that went by before it was opened.
  const [banner, setBanner] = useState(null)
  const firedRef = useRef({ key: null, pad: false })
  useEffect(() => {
    if (!clock || ended || !configured) return
    const key = clock.state === 'running' ? clock.slot : clock.state
    const f = firedRef.current
    const next = clock.state === 'running' ? clock.slot + 1 : 0
    if (f.key !== key) {
      const first = f.key === null
      firedRef.current = { key, pad: first && padWindow }
      if (!first && clock.state === 'running') {
        setBanner({ label: 'Change over', tone: 'red', detail: `In now: ${listed(namesAt(clock.slot))}` })
        beep && beep('red')
      }
      return
    }
    if (!f.pad && padWindow && clock.state !== 'over') {
      f.pad = true
      setBanner({ label: 'Pad up', tone: 'green', detail: `Next: ${listed(namesAt(next))}` })
      beep && beep('amber')
    }
  }, [clock, padWindow, ended, configured]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!banner) return undefined
    const t = setTimeout(() => setBanner(null), 25000)
    return () => clearTimeout(t)
  }, [banner])


  const moveTo = useCallback((attId, netId, slot) => {
    setPicked(null)
    return act(() => api.nmMoveSlot(id, { attendee_id: attId, net_id: netId, slot_index: slot }))
  }, [act, id])

  // Dragging by the grip. A drag holds the poll off (holdPoll) for as long as it
  // lasts, or a poll landing mid-drag would put the old grid back under the
  // finger. Listeners are on the window so the pointer can leave the grip.
  const onGrip = (e, a) => {
    if (!canEdit || ended || (e.button !== undefined && e.button !== 0)) return
    dragRef.current = { id: a.id, name: a.name, sx: e.clientX, sy: e.clientY, moved: false }
  }
  useEffect(() => {
    const cellAt = (x, y) => {
      const el = document.elementFromPoint(x, y)
      const c = el && el.closest && el.closest('[data-cell]')
      return c ? { net: c.dataset.net, slot: Number(c.dataset.slot) } : null
    }
    const move = (e) => {
      const d = dragRef.current
      if (!d) return
      if (!d.moved) {
        if (Math.hypot(e.clientX - d.sx, e.clientY - d.sy) < 6) return
        d.moved = true
        holdPoll(true)
      }
      setDrag({ id: d.id, name: d.name, x: e.clientX, y: e.clientY, over: cellAt(e.clientX, e.clientY) })
    }
    const up = (e) => {
      const d = dragRef.current
      dragRef.current = null
      if (!d) return
      if (!d.moved) { setPicked((cur) => (cur === d.id ? null : d.id)); return }
      const over = cellAt(e.clientX, e.clientY)
      setDrag(null)
      holdPoll(false)
      if (over) moveTo(d.id, over.net, over.slot)
    }
    const cancel = () => {
      const d = dragRef.current
      dragRef.current = null
      if (d && d.moved) { setDrag(null); holdPoll(false) }
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', cancel)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', cancel)
    }
  }, [holdPoll, moveTo])

  // A time clicked on the left edge. Only the new time goes up: the server works
  // out which slot to lengthen, and every later time moves with it.
  const saveTime = (i, time) => act(() => api.nmSetSlotTime(id, { slot_index: i, time }))

  const savePlan = async (body) => {
    setSaving(true)
    try { await act(() => api.nmSetPlan(id, body)); setPlanOpen(false) }
    catch (e) { toast.error(e.message) } finally { setSaving(false) }
  }

  const tapName = (a, repeat) => {
    if (!canEdit || ended || repeat) return
    // With somebody already picked up, a tap on another name is a drop onto
    // that cell (a swap), which the cell's own click handles.
    if (picked && picked !== a.id) return
    setPicked((cur) => (cur === a.id ? null : a.id))
  }
  const tapCell = (netId, slot, occupant) => {
    if (!picked || !canEdit || ended) return
    if (occupant && occupant.id === picked) { setPicked(null); return }
    moveTo(picked, netId, slot)
  }

  const pickedPerson = picked ? byId.get(picked) : null
  const times = grid.times || []

  // ── Not set up yet ──────────────────────────────────────────────────────
  if (!grid.configured) {
    return (
      <div className="pb-card px-5 py-8 text-center" data-grid-unconfigured>
        <div className="font-display font-bold text-[17px]">Set up the nets</div>
        <div className="text-[13px] text-pb-faint mt-1 max-w-[440px] mx-auto">
          Pick when the first net starts, how long each slot is, and which squads use which net. People are placed as they check in.
        </div>
        {canEdit && !ended
          ? <div className="mt-4"><Btn variant="primary" icon="settings" onClick={() => setPlanOpen(true)}>Set up the nets</Btn></div>
          : <Empty className="mt-3">Whoever runs nets has not set the times yet.</Empty>}
        {planOpen && <PlanModal plan={plan} squads={squads} onSave={savePlan} onClose={() => setPlanOpen(false)} saving={saving} />}
      </div>
    )
  }

  const cols = `84px repeat(${grid.nets.length}, minmax(150px, 1fr))`

  const heroNow = clock && clock.state === 'running' ? namesAt(clock.slot) : []
  const nextSlot = clock ? (clock.state === 'running' ? clock.slot + 1 : clock.state === 'before' ? 0 : null) : null
  const heroNext = nextSlot != null && nextSlot < times.length ? namesAt(nextSlot) : []

  return (
    <div className="flex flex-col gap-3 min-w-0 select-none" data-net-grid>
      {clock && !ended && (
        <NowNext clock={clock} now={heroNow} next={heroNext} nextTime={nextSlot != null ? times[nextSlot] : null}
          padWindow={padWindow} padUp={padUp} banner={banner} />
      )}
      <div className="flex items-center flex-wrap gap-x-3 gap-y-1.5">
        <div className="font-display font-bold text-[15px]">Nets by time slot</div>
        <div className="font-mono text-[11px] text-pb-faint">
          First net {fmtSlot(grid.first_time)} · {grid.slot_minutes} min slots{(grid.custom_slots || []).length ? ` (${grid.custom_slots.length} changed)` : ''}{grid.finish_time ? ` · finish ${fmtSlot(grid.finish_time)}` : ''}
        </div>
        {canEdit && !ended && <div className="text-[11.5px] text-pb-faint w-full sm:w-auto" data-time-hint>Click a time to change it. Every later time moves with it.</div>}
        <div className="flex-1" />
        {onToggleSound && !ended && (
          <Btn variant="ghost" sm icon={soundOn ? 'sound' : 'mute'} onClick={onToggleSound} data-alarm-toggle
            title="Beeps on this and every other open screen for pad up and the change over">Alarms {soundOn ? 'on' : 'off'}</Btn>
        )}
        {canEdit && !ended && <Btn variant="ghost" sm icon="settings" onClick={() => setPlanOpen(true)}>Edit nets</Btn>}
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] text-pb-faint" data-grid-key>
        {['now', 'pad', 'next'].map((k) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <span className="w-3.5 h-3.5 rounded-sm border" style={{ background: tint(k), borderColor: STATES[k].color }} />
            <b className="font-mono text-[10px] uppercase tracking-wide2" style={{ color: STATES[k].color }}>{STATES[k].word}</b>
          </span>
        ))}
      </div>

      {grid.overflow_count > 0 && (
        <div className="rounded-lg px-3 py-2 text-[12.5px]" role="status" data-overflow-banner
          style={{ background: 'color-mix(in srgb, var(--pb-red) 12%, transparent)', color: 'var(--pb-red)' }}>
          {grid.overflow_count} {grid.overflow_count === 1 ? 'person does' : 'people do'} not fit before the finish time. They are listed under their net. Move a name, or extend the finish.
        </div>
      )}

      {pickedPerson && canEdit && !ended && (
        <div className="pb-card px-3.5 py-2.5 flex flex-wrap items-center gap-2" data-picked-bar
          style={{ borderColor: 'color-mix(in srgb, var(--pb-accent) 45%, transparent)' }}>
          <span className="text-[13px] min-w-0">Moving <b>{pickedPerson.name}</b>. Tap a slot to put them there.</span>
          <span className="flex-1" />
          <Btn variant="ghost" sm onClick={() => { setPicked(null); act(() => api.nmPatchAttendee(id, pickedPerson.id, { batted: !pickedPerson.batted })) }}>
            {pickedPerson.batted ? 'Not batted yet' : 'Mark batted'}
          </Btn>
          <Btn variant="ghost" sm onClick={() => { setPicked(null); act(() => api.nmPatchAttendee(id, pickedPerson.id, { bats: false })) }}>Not batting</Btn>
          <Btn variant="ghost" sm onClick={() => { setPicked(null); act(() => api.nmRemoveAttendee(id, pickedPerson.id)) }}>Remove</Btn>
          <Btn variant="ghost" sm onClick={() => setPicked(null)}>Cancel</Btn>
        </div>
      )}

      <div className="pb-card overflow-x-auto">
        <div style={{ display: 'grid', gridTemplateColumns: cols, minWidth: 84 + grid.nets.length * 150 }} role="table" aria-label="Nets by time slot">
          {/* Header */}
          <div className="sticky left-0 z-10 bg-pb-surface border-b pb-hairline px-2 py-2 font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest">Time</div>
          {grid.nets.map((n) => (
            <div key={n.id} className="border-b border-l pb-hairline px-2.5 py-2 min-w-0" data-net-head={n.id}>
              <div className="font-display font-bold text-[14px] truncate">{n.name}</div>
              <div className="text-[11px] text-pb-faint truncate">
                {[...n.squad_team_ids.map((t) => (squads.find((s) => s.id === t) || {}).label).filter(Boolean), n.catch_all ? 'everyone else' : null].filter(Boolean).join(', ') || 'no squad'}
                {' · '}{n.count}
              </div>
              {n.overflow.length > 0 && (
                <div className="mt-1 text-[11.5px]" style={{ color: 'var(--pb-red)' }} data-net-overflow={n.id}>
                  <b>Does not fit:</b> {n.overflow.map((x) => (byId.get(x) || {}).name).filter(Boolean).join(', ')}
                </div>
              )}
            </div>
          ))}

          {/* Rows */}
          {times.map((t, i) => {
            return (
              <Row key={i} i={i} t={t} state={stateOfRow(i)} grid={grid} byId={byId} picked={picked} drag={drag}
                canEdit={canEdit && !ended} onGrip={onGrip} onName={tapName} onCell={tapCell} onTime={saveTime}
                custom={(grid.custom_slots || []).includes(i - 1)} />
            )
          })}
        </div>
        {times.length === 0 && <Empty className="px-4 py-6 text-center">The nets finish before the first slot ends. Check the times.</Empty>}
      </div>

      {noNet.length > 0 && (
        <div className="pb-card px-4 py-3" data-no-net>
          <div className="flex items-center justify-between mb-1.5">
            <span className="font-display font-bold text-[14px]" style={{ color: 'var(--pb-amber)' }}>Not in a net</span>
            <span className="font-mono text-[11px] text-pb-faint">{noNet.length} here</span>
          </div>
          <div className="text-[12px] text-pb-faint mb-2">Their squad has no net and no net takes everyone else. Tap a name, then tap a slot.</div>
          <div className="flex flex-wrap gap-1.5">
            {noNet.map((a) => (
              <button key={a.id} type="button" onClick={() => tapName(a, false)} disabled={!canEdit || ended}
                className={`rounded-full border px-3 py-1 text-[12.5px] ${picked === a.id ? 'border-pb-accent text-pb-accent bg-pb-accent/10' : 'border-pb-hairline2 text-pb-dim'}`}>
                {a.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {sitting.length > 0 && (
        <div className="pb-card px-4 py-3" data-not-batting>
          <div className="flex items-center justify-between mb-1.5">
            <span className="font-display font-bold text-[14px]">Not batting</span>
            <span className="font-mono text-[11px] text-pb-amber">{sitting.length} here</span>
          </div>
          {sitting.map((a) => (
            <div key={a.id} className="flex items-center gap-2.5 py-1.5 border-b pb-hairline last:border-0">
              <Avatar player={{ ...a, id: a.player_id }} size={24} />
              <div className="flex-1 min-w-0">
                <div className="text-[13px] text-pb-dim truncate">{a.name}</div>
                {a.note && <div className="text-[11px] text-pb-faint truncate">{a.note}</div>}
              </div>
              {canEdit && !ended && (
                <Btn variant="ghost" sm onClick={() => act(() => api.nmPatchAttendee(id, a.id, { bats: true }))}>Put back in</Btn>
              )}
            </div>
          ))}
        </div>
      )}

      {drag && (
        <div className="fixed z-[130] pointer-events-none rounded-lg px-2.5 py-1.5 text-[13px] font-medium shadow-lg border"
          style={{ left: drag.x + 10, top: drag.y + 10, background: 'var(--pb-surface)', borderColor: 'var(--pb-accent)' }}>
          {drag.name}
        </div>
      )}

      {planOpen && <PlanModal plan={plan} squads={squads} onSave={savePlan} onClose={() => setPlanOpen(false)} saving={saving} />}
    </div>
  )
}

/* ── The strip at the top: who is in, who pads up or is next, and the clock ── */
function HeroLine({ state, word, time, list }) {
  const st = STATES[state]
  return (
    <div className="flex items-start gap-3 py-1.5" data-hero-line={state}>
      <div className="w-[84px] shrink-0">
        <span className="inline-block font-mono text-[10px] uppercase tracking-wide2 font-bold rounded px-1.5 py-0.5"
          style={{ background: tint(state), color: st.color }}>{word || st.word}</span>
        {time && <div className="font-mono text-[11px] text-pb-faint mt-0.5 tabular-nums">{fmtSlot(time)}</div>}
      </div>
      <div className="flex flex-wrap gap-1.5 min-w-0 flex-1">
        {list.map((x) => (
          <span key={x.id} className="inline-flex items-baseline gap-1.5 rounded-lg px-2.5 py-1 min-w-0 max-w-full"
            style={{ background: tint(state), border: `1px solid color-mix(in srgb, ${st.color} 35%, transparent)` }}>
            <span className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faint shrink-0">{x.net}</span>
            <b className={`text-[14px] truncate ${x.who ? '' : 'text-pb-faintest font-normal'}`}>{x.who || 'nobody'}</b>
            {x.repeat && x.who && <span className="font-mono text-[9px] uppercase text-pb-faint shrink-0">2nd go</span>}
          </span>
        ))}
      </div>
    </div>
  )
}

function NowNext({ clock, now, next, nextTime, padWindow, padUp, banner }) {
  const running = clock.state === 'running'
  const urgent = running && clock.remaining <= 30
  const color = urgent ? 'var(--pb-red)' : padWindow ? 'var(--pb-positive)' : 'var(--pb-text)'
  const pct = running ? Math.max(0, Math.min(100, (clock.remaining / clock.total) * 100)) : 0
  const label = running ? 'This slot ends in' : clock.state === 'before' ? 'Nets start in' : 'Nets finished'
  const bannerColor = banner ? (banner.tone === 'red' ? 'var(--pb-red)' : 'var(--pb-positive)') : null
  return (
    <div className="pb-card overflow-hidden" data-now-next data-clock-state={clock.state}
      style={{ borderColor: padWindow ? 'color-mix(in srgb, var(--pb-positive) 45%, transparent)' : undefined }}>
      <div className="px-4 py-3 grid gap-3 md:grid-cols-[1fr_auto] items-center">
        <div className="min-w-0">
          {running && <HeroLine state="now" list={now} />}
          {clock.state !== 'over' && next.length > 0 && (
            <HeroLine state={padWindow ? 'pad' : 'next'} time={nextTime} list={next}
              word={padWindow ? 'Pad up' : (clock.state === 'before' ? 'First up' : 'Next')} />
          )}
          {clock.state === 'over' && <div className="text-[14px] py-2">The last slot has finished.</div>}
          {running && next.length === 0 && <div className="text-[12.5px] text-pb-faint py-1">That is the last slot.</div>}
        </div>
        {clock.state !== 'over' && (
          <div className="text-center md:text-right md:min-w-[170px]" data-slot-timer>
            <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">{label}</div>
            <div className="font-display font-bold tabular-nums leading-none" style={{ fontSize: 'clamp(40px, 9vw, 64px)', color, transition: 'color .3s' }}>
              {fmtClock(running ? clock.remaining : clock.untilStart)}
            </div>
            {running && (
              <div className="h-1.5 rounded-full bg-pb-surface2 overflow-hidden mt-2.5">
                <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color, transition: 'width 1s linear, background .3s' }} />
              </div>
            )}
            {padUp > 0 && <div className="text-[11px] text-pb-faint mt-1.5">Pad up warning {fmtClock(padUp)} before each change</div>}
          </div>
        )}
      </div>
      {banner && (
        <div className="px-4 py-2 border-t text-[13.5px] flex items-center gap-2 flex-wrap" role="status" aria-live="polite" data-alarm-banner={banner.label}
          style={{ background: `color-mix(in srgb, ${bannerColor} 14%, transparent)`, borderColor: `color-mix(in srgb, ${bannerColor} 35%, transparent)` }}>
          <Icon name="bolt" size={14} />
          <b className="font-display" style={{ color: bannerColor }}>{banner.label}</b>
          <span className="text-pb-dim min-w-0">{banner.detail}</span>
        </div>
      )}
    </div>
  )
}

/* ── A time on the left edge, click to change it ──────────────────────────── */
// A custom time (one a coach has moved) is underlined, so a slot that is not the
// standard length is visible without opening anything.
function TimeEdit({ t, i, canEdit, custom, onSave }) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(t)
  useEffect(() => { if (!editing) setVal(t) }, [t, editing])
  if (!canEdit) return <span>{fmtSlot(t)}</span>
  if (editing) {
    const done = (commit) => {
      setEditing(false)
      if (commit && val && val !== t) onSave(i, val)
    }
    return (
      <input type="time" autoFocus value={val} aria-label={`Start time of row ${i + 1}`} data-time-input={i}
        onChange={(e) => setVal(e.target.value)} onBlur={() => done(true)}
        onKeyDown={(e) => { if (e.key === 'Enter') done(true); if (e.key === 'Escape') done(false) }}
        className="w-[76px] bg-pb-surface2 border border-pb-accent rounded px-0.5 py-0.5 text-[11px] text-pb-text" />
    )
  }
  return (
    <button type="button" onClick={() => setEditing(true)} data-time-edit={i}
      title="Change this start time. Every later time moves with it."
      className={`tabular-nums hover:text-pb-accent ${custom ? 'underline decoration-dotted underline-offset-2' : ''}`}>
      {fmtSlot(t)}
    </button>
  )
}

/* ── One row of the grid: a time and a cell per net ───────────────────────── */
function Row({ i, t, state, grid, byId, picked, drag, canEdit, onGrip, onName, onCell, onTime, custom }) {
  const past = state === 'past'
  const bg = tint(state)
  const edge = `3px solid ${STATES[state] ? STATES[state].color : 'transparent'}`
  return (
    <>
      {/* The tint sits on a solid backing so a sticky cell never shows names scrolling under it. */}
      <div className="sticky left-0 z-10 border-b pb-hairline bg-pb-surface" data-slot-time={i} data-row-state={state || ''}>
        <div className={`px-2 py-1.5 font-mono text-[12px] tabular-nums h-full ${STATES[state] ? 'font-bold' : 'text-pb-dim'}`}
          style={{ borderLeft: edge, background: bg, color: STATES[state] ? STATES[state].color : undefined }}>
          <TimeEdit t={t} i={i} canEdit={canEdit} custom={custom} onSave={onTime} />
          {STATES[state] && <div className="text-[9px] uppercase tracking-wide2 leading-none mt-0.5">{STATES[state].word}</div>}
        </div>
      </div>
      {grid.nets.map((n) => {
        const cell = n.cells[i] || { attendee_id: null, repeat: false }
        const a = cell.attendee_id ? byId.get(cell.attendee_id) : null
        const over = drag && drag.over && drag.over.net === n.id && drag.over.slot === i
        return (
          <div key={n.id} data-cell data-net={n.id} data-slot={i}
            onClick={() => onCell(n.id, i, a)}
            style={bg ? { background: bg } : undefined}
            className={`border-b border-l pb-hairline px-1 py-1 min-w-0 min-h-[38px] flex items-center ${past ? 'opacity-55' : ''} ${
              picked && canEdit && !cell.repeat ? 'cursor-pointer hover:bg-pb-accent/10' : ''} ${over ? 'bg-pb-accent/20 outline outline-1 outline-pb-accent' : ''}`}>
            {a
              ? <NameChip a={a} repeat={cell.repeat} picked={picked === a.id} canEdit={canEdit} onPick={onName} onGrip={onGrip} />
              : <span className="text-pb-faintest text-[11px] px-2 select-none">{picked && canEdit ? 'drop here' : ''}</span>}
          </div>
        )
      })}
    </>
  )
}
