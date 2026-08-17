import { useState, useEffect, useMemo, useCallback } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import { Modal, Field, TextInput, Select, Btn, Pill } from './ui'
import EventForm, { CalendarIcon, eventTypeLabel, alertLabel } from './EventForm'

export const EVENT_COLOR = '#8b7cf6'  // the calendar/date accent, matching the board card

// ─── date helpers (no library) — exported so SalesEventsView (the Sales
// Workspace's own, more narrowly-scoped Events tab) can build the identical
// calendar grid without a second copy of this arithmetic drifting from it. ──
export const startOfDay = (d) => { const x = new Date(d); x.setHours(0, 0, 0, 0); return x }
export const endOfDay = (d) => { const x = new Date(d); x.setHours(23, 59, 59, 999); return x }
export const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x }
export const addMonths = (d, n) => { const x = new Date(d); x.setMonth(x.getMonth() + n); return x }
// Monday-based week (AU convention).
export const startOfWeek = (d) => { const x = startOfDay(d); const dow = (x.getDay() + 6) % 7; return addDays(x, -dow) }
export const startOfMonth = (d) => { const x = startOfDay(d); x.setDate(1); return x }
export const sameDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
export const isToday = (d) => sameDay(new Date(d), new Date())
export const fmtTime = (iso) => new Date(iso).toLocaleTimeString('en-AU', { hour: 'numeric', minute: '2-digit' })
export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

// ─── standalone add/edit modal (also reused for a deal-less event) ───────────
function EventModal({ open, onClose, ownerOptions, event, seed, onSaved }) {
  const toast = useToast()
  const isEdit = !!event?.id
  const [clubQuery, setClubQuery] = useState('')
  const [selectedClub, setSelectedClub] = useState(null)  // {id, name}
  const [candidates, setCandidates] = useState([])
  const [contactOptions, setContactOptions] = useState([])
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    // Seed from the event being edited (its club is fixed at whatever it has).
    if (event) {
      setSelectedClub(event.marketing_club_id ? { id: event.marketing_club_id, name: event.marketing_club_name } : null)
      setClubQuery(event.marketing_club_name || '')
    } else {
      setSelectedClub(null); setClubQuery(''); setContactOptions([])
    }
  }, [open, event])

  // Load the chosen club's CRM people for the contact picker.
  useEffect(() => {
    if (!selectedClub?.id) { setContactOptions([]); return }
    let alive = true
    api.superCrmListPeople('', selectedClub.id)
      .then(r => { if (alive) setContactOptions((r.people || []).map(p => ({ id: p.id, name: p.full_name }))) })
      .catch(() => { if (alive) setContactOptions([]) })
    return () => { alive = false }
  }, [selectedClub])

  // Club search (Club Directory), same pattern as the New Deal modal.
  useEffect(() => {
    if (!open || selectedClub || clubQuery.trim().length < 2) { setCandidates([]); return }
    let alive = true
    const t = setTimeout(() => {
      api.mktQuickSearchClubs(clubQuery.trim(), 8)
        .then(r => { if (alive) setCandidates(r.clubs || []) })
        .catch(() => { if (alive) setCandidates([]) })
    }, 300)
    return () => { alive = false; clearTimeout(t) }
  }, [clubQuery, open, selectedClub])

  const submit = async (payload) => {
    setSaving(true)
    try {
      const body = { ...payload, marketing_club_id: selectedClub?.id || null }
      if (isEdit) await api.superCrmUpdateEvent(event.id, body)
      else await api.superCrmCreateEvent(body)
      onSaved()
      onClose()
    } catch (e) { toast.error(e.message || 'Could not save event') } finally { setSaving(false) }
  }

  if (!open) return null

  const clubPicker = (
    <Field label="Club (optional)" hint="Link the event to a Club Directory prospect, or leave blank.">
      <div className="relative">
        <TextInput value={clubQuery} placeholder="Search the Club Directory…"
          onChange={e => { setClubQuery(e.target.value); if (selectedClub && e.target.value !== selectedClub.name) setSelectedClub(null) }} />
        {selectedClub && (
          <button type="button" onClick={() => { setSelectedClub(null); setClubQuery('') }}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-pb-faint hover:text-pb-red text-[11px]">clear</button>
        )}
        {!selectedClub && candidates.length > 0 && (
          <div className="absolute z-10 mt-1 w-full pb-card divide-y divide-pb-hairline max-h-56 overflow-y-auto">
            {candidates.map(c => (
              <button type="button" key={c.id} onClick={() => { setSelectedClub({ id: c.id, name: c.name }); setClubQuery(c.name); setCandidates([]) }}
                className="block w-full text-left px-3 py-2 text-[12.5px] hover:bg-pb-surface2">
                {c.name}{c.state ? <span className="text-pb-faint"> · {c.state}</span> : null}
              </button>
            ))}
          </div>
        )}
      </div>
    </Field>
  )

  return (
    <Modal open={open} onClose={onClose} wide title={isEdit ? 'Edit event' : 'New event'}>
      <EventForm key={event?.id || (seed?.starts_at ? `seed-${seed.starts_at}` : 'new')}
        initial={event || seed || undefined} ownerOptions={ownerOptions} contactOptions={contactOptions}
        extraTop={clubPicker} onSubmit={submit} onCancel={onClose} saving={saving}
        submitLabel={isEdit ? 'Save changes' : 'Create event'} />
    </Modal>
  )
}

// ─── a single event card (list rows + calendar day/week panels) ──────────────
export function EventCard({ ev, onEdit, onDelete, compact }) {
  const alerts = [ev.first_alert, ev.second_alert].filter(Boolean).map(alertLabel)
  const today = isToday(ev.starts_at)
  return (
    <div className={`pb-card px-3 py-2 ${today ? 'border-l-2' : ''}`}
      style={today ? { borderLeftColor: EVENT_COLOR } : undefined}>
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 min-w-0">
          <CalendarIcon className="shrink-0" />
          <Pill tone="accent">{eventTypeLabel(ev.event_type)}</Pill>
          {ev.title && <span className="font-medium text-[12.5px] truncate">{ev.title}</span>}
          {today && <span className="text-[9.5px] font-mono uppercase tracking-wide px-1.5 py-0.5 rounded-full"
            style={{ color: EVENT_COLOR, background: 'rgba(139,124,246,0.12)' }}>Today</span>}
        </span>
        <span className="flex items-center gap-2 shrink-0">
          <button onClick={() => onEdit(ev)} className="text-pb-faint hover:text-pb-accent text-[11px]">Edit</button>
          <button onClick={() => onDelete(ev)} className="text-pb-faint hover:text-pb-red text-[11px]">Delete</button>
        </span>
      </div>
      <div className="text-[11.5px] mt-0.5" style={{ color: EVENT_COLOR }}>
        {new Date(ev.starts_at).toLocaleString('en-AU', { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })}
      </div>
      {!compact && (
        <div className="text-pb-faint text-[11px] flex flex-wrap gap-x-2">
          {ev.marketing_club_name && <span>{ev.marketing_club_name}</span>}
          {ev.location && <span>· 📍 {ev.location}</span>}
          {ev.owner_name && <span>· {ev.owner_name}</span>}
          {ev.contact_name && <span>· {ev.contact_name}</span>}
          {/* The linked deal's title duplicates the club name shown at the
              start of the line, so only surface it for a deal with no club. */}
          {!ev.marketing_club_name && ev.deal_title && <span>· deal: {ev.deal_title}</span>}
        </div>
      )}
      {!compact && alerts.length > 0 && (
        <div className="text-pb-faintest text-[10.5px] mt-0.5">Alerts: {alerts.join(', ')}</div>
      )}
      {!compact && ev.body && <p className="text-pb-text text-[12px] mt-1">{ev.body}</p>}
    </div>
  )
}

// A calendar chip: time + type + title on the first line, then club name, then
// contact name. `compact` (month grid, where cells are kept short so the whole
// month fits the viewport) shows the first line only; week columns show all
// three lines. The full detail is always in the title tooltip and on click.
export function EventChip({ ev, onClick, compact }) {
  const line1 = `${fmtTime(ev.starts_at)} ${eventTypeLabel(ev.event_type)}${ev.title ? ` · ${ev.title}` : ''}`
  const tip = [line1, ev.marketing_club_name, ev.contact_name].filter(Boolean).join('\n')
  return (
    <button type="button" onClick={onClick} title={tip}
      className="block w-full text-left leading-tight px-1.5 py-0.5 rounded"
      style={{ background: 'rgba(139,124,246,0.14)', color: EVENT_COLOR }}>
      <div className="text-[10px] font-medium truncate">{line1}</div>
      {!compact && ev.marketing_club_name && <div className="text-[9.5px] truncate opacity-90">{ev.marketing_club_name}</div>}
      {!compact && ev.contact_name && <div className="text-[9.5px] truncate opacity-75">{ev.contact_name}</div>}
    </button>
  )
}

// ─── calendar month grid ─────────────────────────────────────────────────────
export function MonthView({ cursor, events, onPick, onDayAdd }) {
  const first = startOfMonth(cursor)
  const gridStart = startOfWeek(first)
  const cells = Array.from({ length: 42 }, (_, i) => addDays(gridStart, i))
  const byDay = useMemo(() => {
    const m = {}
    for (const e of events) { const k = startOfDay(e.starts_at).toDateString(); (m[k] ||= []).push(e) }
    return m
  }, [events])
  return (
    <div className="pb-card overflow-hidden">
      <div className="grid grid-cols-7 text-[10.5px] font-mono uppercase tracking-wide text-pb-faint border-b border-pb-hairline">
        {WEEKDAYS.map(d => <div key={d} className="px-2 py-1.5 text-center">{d}</div>)}
      </div>
      <div className="grid grid-cols-7">
        {cells.map((day, i) => {
          const inMonth = day.getMonth() === cursor.getMonth()
          const dayEvents = byDay[day.toDateString()] || []
          const today = isToday(day)
          // Compact fixed-height cell so all 6 rows of a month fit a laptop
          // viewport without scrolling past the end of the month. Overflow
          // inside a busy day scrolls within the cell.
          return (
            <div key={i} className={`h-[74px] overflow-y-auto border-b border-r border-pb-hairline p-1 ${inMonth ? '' : 'bg-pb-surface2/40'}`}>
              <div className="flex items-center justify-between">
                <button onClick={() => onDayAdd(day)} title="Add an event on this day"
                  className={`text-[11px] w-5 h-5 rounded-full flex items-center justify-center ${
                    today ? 'text-white font-bold' : inMonth ? 'text-pb-text hover:bg-pb-surface2' : 'text-pb-faintest'}`}
                  style={today ? { background: EVENT_COLOR } : undefined}>
                  {day.getDate()}
                </button>
              </div>
              <div className="space-y-0.5 mt-0.5">
                {dayEvents.slice(0, 2).map(e => (
                  <EventChip key={e.id} ev={e} onClick={() => onPick(e)} compact />
                ))}
                {dayEvents.length > 2 && (
                  <div className="text-[9px] text-pb-faint px-1">+{dayEvents.length - 2} more</div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── calendar week / day columns ─────────────────────────────────────────────
export function WeekDayView({ cursor, mode, events, onPick, onEdit, onDelete }) {
  const days = mode === 'day' ? [startOfDay(cursor)]
    : Array.from({ length: 7 }, (_, i) => addDays(startOfWeek(cursor), i))
  const byDay = useMemo(() => {
    const m = {}
    for (const e of events) { const k = startOfDay(e.starts_at).toDateString(); (m[k] ||= []).push(e) }
    for (const k of Object.keys(m)) m[k].sort((a, b) => new Date(a.starts_at) - new Date(b.starts_at))
    return m
  }, [events])
  return (
    <div className={`grid gap-2 ${mode === 'day' ? 'grid-cols-1' : 'grid-cols-1 md:grid-cols-7'}`}>
      {days.map((day, i) => {
        const dayEvents = byDay[day.toDateString()] || []
        const today = isToday(day)
        return (
          <div key={i} className="min-w-0">
            <div className={`text-[11px] font-mono uppercase tracking-wide mb-1 px-1 py-1 rounded flex items-center justify-between ${today ? 'font-bold' : 'text-pb-faint'}`}
              style={today ? { color: EVENT_COLOR, background: 'rgba(139,124,246,0.10)' } : undefined}>
              <span>{day.toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: mode === 'day' ? 'long' : 'short' })}</span>
              {today && <span>Today</span>}
            </div>
            <div className="space-y-1.5">
              {dayEvents.length === 0 && <div className="text-[10.5px] text-pb-faintest px-1 py-2">—</div>}
              {dayEvents.map(e => mode === 'day'
                ? <EventCard key={e.id} ev={e} onEdit={onEdit} onDelete={onDelete} />
                : <EventChip key={e.id} ev={e} onClick={() => onPick(e)} />)}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ─── the Events page (rendered as a view inside SuperCrm) ────────────────────
export default function CrmEventsView({ owners }) {
  const toast = useToast()
  const ownerOptions = owners || []
  const [allEvents, setAllEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [view, setView] = useState('calendar')     // calendar (default) | list
  const [calMode, setCalMode] = useState('month')  // month | week | day
  const [cursor, setCursor] = useState(() => new Date())

  // Filters (all client-side — the platform pipeline's event set is small).
  const [q, setQ] = useState('')
  const [ownerId, setOwnerId] = useState('')       // Assigned To
  const [userId, setUserId] = useState('')         // Created by
  const [clubId, setClubId] = useState('')
  const [date, setDate] = useState('')             // single day (list view)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const [modalOpen, setModalOpen] = useState(false)
  const [editEvent, setEditEvent] = useState(null)
  const [modalDefaultDate, setModalDefaultDate] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    api.superCrmListEvents({})
      .then(r => setAllEvents(r.events || []))
      .catch(e => toast.error(e.message || 'Could not load events'))
      .finally(() => setLoading(false))
  }, [toast])
  useEffect(() => { load() }, [load])

  // Club dropdown built from the events themselves (before the club filter).
  const clubOptions = useMemo(() => {
    const m = new Map()
    for (const e of allEvents) if (e.marketing_club_id) m.set(e.marketing_club_id, e.marketing_club_name || e.marketing_club_id)
    return [...m.entries()].map(([id, name]) => ({ id, name })).sort((a, b) => (a.name || '').localeCompare(b.name || ''))
  }, [allEvents])

  // Shared field filters (everything except the date window, which differs
  // between List and Calendar).
  const baseFiltered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return allEvents.filter(e => {
      if (ownerId && e.owner_user_id !== ownerId) return false
      if (userId && e.created_by_user_id !== userId) return false
      if (clubId && e.marketing_club_id !== clubId) return false
      if (needle) {
        const hay = [e.title, e.marketing_club_name, e.deal_title, e.contact_name, e.body]
          .filter(Boolean).join(' ').toLowerCase()
        if (!hay.includes(needle)) return false
      }
      return true
    })
  }, [allEvents, q, ownerId, userId, clubId])

  // List view honours the explicit Date / Date-range filters.
  const listEvents = useMemo(() => {
    return baseFiltered.filter(e => {
      const d = new Date(e.starts_at)
      if (date) { const day = new Date(date); if (!sameDay(d, day)) return false }
      if (dateFrom && d < startOfDay(new Date(dateFrom))) return false
      if (dateTo && d > endOfDay(new Date(dateTo))) return false
      return true
    })
  }, [baseFiltered, date, dateFrom, dateTo])

  // Calendar view honours the visible window instead.
  const calWindow = useMemo(() => {
    if (calMode === 'day') return [startOfDay(cursor), endOfDay(cursor)]
    if (calMode === 'week') { const s = startOfWeek(cursor); return [s, endOfDay(addDays(s, 6))] }
    const s = startOfWeek(startOfMonth(cursor)); return [s, endOfDay(addDays(s, 41))]
  }, [calMode, cursor])
  const calEvents = useMemo(() => baseFiltered.filter(e => {
    const d = new Date(e.starts_at); return d >= calWindow[0] && d <= calWindow[1]
  }), [baseFiltered, calWindow])

  const periodLabel = useMemo(() => {
    if (calMode === 'day') return cursor.toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
    if (calMode === 'week') {
      const s = startOfWeek(cursor), e = addDays(s, 6)
      return `${s.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })} – ${e.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}`
    }
    return cursor.toLocaleDateString('en-AU', { month: 'long', year: 'numeric' })
  }, [calMode, cursor])

  const step = (dir) => setCursor(c => calMode === 'month' ? addMonths(c, dir) : addDays(c, dir * (calMode === 'week' ? 7 : 1)))

  const openAdd = (defaultDate) => { setEditEvent(null); setModalDefaultDate(defaultDate || null); setModalOpen(true) }
  const openEdit = (ev) => { setEditEvent(ev); setModalDefaultDate(null); setModalOpen(true) }
  const remove = async (ev) => {
    if (!window.confirm('Delete this event?')) return
    try { await api.superCrmDeleteEvent(ev.id); load() }
    catch (e) { toast.error(e.message || 'Could not delete event') }
  }

  const pill = (active) => `px-2.5 py-1 rounded-full text-[11.5px] border transition ${
    active ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent' : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`

  // A newly-added event from a calendar day-cell gets that day pre-filled (9am).
  const seedEvent = modalDefaultDate ? { starts_at: (() => {
    const d = new Date(modalDefaultDate); d.setHours(9, 0, 0, 0); return d.toISOString()
  })() } : null

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <button onClick={() => setView('calendar')} className={pill(view === 'calendar')}>Calendar</button>
          <button onClick={() => setView('list')} className={pill(view === 'list')}>List</button>
        </div>
        <Btn variant="primary" sm onClick={() => openAdd()}>New event</Btn>
      </div>

      {/* Filters */}
      <div className="pb-card px-3 py-3 flex flex-wrap gap-3 items-end">
        <Field label="Search (title, club)" width="220px">
          <TextInput value={q} onChange={e => setQ(e.target.value)} placeholder="Search events…" />
        </Field>
        {ownerOptions.length > 0 && (
          <Field label="Assigned to" width="170px">
            <Select value={ownerId} onChange={e => setOwnerId(e.target.value)}>
              <option value="">Anyone</option>
              {ownerOptions.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
            </Select>
          </Field>
        )}
        {ownerOptions.length > 0 && (
          <Field label="Created by" width="170px">
            <Select value={userId} onChange={e => setUserId(e.target.value)}>
              <option value="">Anyone</option>
              {ownerOptions.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
            </Select>
          </Field>
        )}
        <Field label="Club" width="190px">
          <Select value={clubId} onChange={e => setClubId(e.target.value)}>
            <option value="">All clubs</option>
            {clubOptions.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
        </Field>
        {view === 'list' && (
          <>
            <Field label="On date" width="150px">
              <TextInput type="date" value={date} onChange={e => setDate(e.target.value)} />
            </Field>
            <Field label="From" width="150px">
              <TextInput type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
            </Field>
            <Field label="To" width="150px">
              <TextInput type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} />
            </Field>
          </>
        )}
        {(q || ownerId || userId || clubId || date || dateFrom || dateTo) && (
          <Btn variant="ghost" sm onClick={() => { setQ(''); setOwnerId(''); setUserId(''); setClubId(''); setDate(''); setDateFrom(''); setDateTo('') }}>
            Clear filters
          </Btn>
        )}
      </div>

      {loading ? <p className="text-pb-faint text-sm px-1">Loading events…</p> : view === 'list' ? (
        <div className="space-y-2">
          {listEvents.length === 0 && <div className="pb-card px-3 py-6 text-center text-[12.5px] text-pb-faintest">No events match.</div>}
          {listEvents.map(ev => <EventCard key={ev.id} ev={ev} onEdit={openEdit} onDelete={remove} />)}
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <button onClick={() => step(-1)} className="px-2 py-1 rounded border border-pb-hairline2 text-pb-faint hover:text-pb-text text-[13px]">‹</button>
              <button onClick={() => setCursor(new Date())} className="px-2.5 py-1 rounded-full text-[11.5px] border border-pb-hairline2 text-pb-faint hover:text-pb-accent">Today</button>
              <button onClick={() => step(1)} className="px-2 py-1 rounded border border-pb-hairline2 text-pb-faint hover:text-pb-text text-[13px]">›</button>
              <span className="font-display font-bold text-[14px] ml-1">{periodLabel}</span>
            </div>
            <div className="flex items-center gap-2">
              {['month', 'week', 'day'].map(m => (
                <button key={m} onClick={() => setCalMode(m)} className={pill(calMode === m)}>
                  {m[0].toUpperCase() + m.slice(1)}
                </button>
              ))}
            </div>
          </div>
          {calMode === 'month'
            ? <MonthView cursor={cursor} events={calEvents} onPick={openEdit} onDayAdd={openAdd} />
            : <WeekDayView cursor={cursor} mode={calMode} events={calEvents} onPick={openEdit} onEdit={openEdit} onDelete={remove} />}
        </div>
      )}

      <EventModal open={modalOpen} onClose={() => setModalOpen(false)} ownerOptions={ownerOptions}
        event={editEvent} seed={seedEvent} onSaved={load} />
    </div>
  )
}
