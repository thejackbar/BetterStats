import { useState, useEffect, useMemo, useCallback } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import { Modal, Field, TextInput, TextArea, Select, Btn, MultiSelect, ownerFilterGroups, ownerMatches } from './ui'
import DateTimePicker from './DateTimePicker'
import {
  EVENT_TYPE_OPTIONS, ALERT_OPTIONS, isoToLocalInput, localInputToIso,
} from './EventForm'
import {
  startOfDay, endOfDay, addDays, addMonths, startOfWeek, startOfMonth, sameDay,
  MonthView, WeekDayView, EventCard,
} from './CrmEventsView'

// The Sales Workspace's own Events tab — same List/Calendar shell as the
// Sales Pipeline's Events page (CrmEventsView.jsx, whose calendar grid and
// event-card rendering this reuses directly), narrowed to what a rep is
// allowed to do: link an event only to a club already in THEIR OWN queue
// (never a full Club Directory search — that's the Pipeline's job), and pick
// an owner from the staff pool rather than the whole platform. The backend
// (`GET/POST/PATCH/DELETE .../sales-workspace/events`) restricts a 'sales'
// caller to events they own or created; a super admin sees every event, same
// as the Pipeline's page.

const contactKey = (c) => c.directory_contact_id || c.crm_person_id

// A composite key `d:<uuid>` / `c:<uuid>` round-trips a merged contact
// (directory or CRM-only — see services/sales_workspace.merged_contacts)
// through a plain <select>, then splits back into the two ids the backend
// actually wants on submit.
function decodeContactKey(key) {
  if (!key) return { directory_contact_id: null, crm_person_id: null }
  const [kind, id] = key.split(':')
  return kind === 'd' ? { directory_contact_id: id, crm_person_id: null } : { directory_contact_id: null, crm_person_id: id }
}

function defaultStartsAt() {
  const d = new Date()
  d.setMinutes(0, 0, 0)
  d.setHours(d.getHours() + 1)
  return isoToLocalInput(d.toISOString())
}

function SalesEventModal({ open, onClose, dealOptions, staffOptions, event, seed, onSaved }) {
  const toast = useToast()
  const isEdit = !!event?.id
  const [dealId, setDealId] = useState('')
  const [contactOptions, setContactOptions] = useState([])
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState(null)

  useEffect(() => {
    if (!open) return
    setForm({
      event_type: event?.event_type || seed?.event_type || 'call',
      starts_at: event?.starts_at ? isoToLocalInput(event.starts_at) : (seed?.starts_at ? isoToLocalInput(seed.starts_at) : defaultStartsAt()),
      title: event?.title || '',
      location: event?.location || '',
      body: event?.body || '',
      owner_user_id: event?.owner_user_id || '',
      contactSel: '',
      first_alert: event?.first_alert || '',
      second_alert: event?.second_alert || '',
    })
    setDealId(event?.deal_id || '')
  }, [open, event, seed])

  // The contact picker loads whenever a club is selected — for an existing
  // event this re-derives the same list its own club offers, then seeds the
  // select once the options (and the event's own contact) are both known.
  useEffect(() => {
    if (!dealId) { setContactOptions([]); return }
    let alive = true
    api.salesWorkspaceClubContacts(dealId)
      .then(r => { if (alive) setContactOptions(r.contacts || []) })
      .catch(() => { if (alive) setContactOptions([]) })
    return () => { alive = false }
  }, [dealId])

  useEffect(() => {
    if (!event?.contact_person_id || contactOptions.length === 0) return
    const match = contactOptions.find(c => c.crm_person_id === event.contact_person_id)
    if (match) setForm(f => (f ? { ...f, contactSel: `${match.directory_contact_id ? 'd' : 'c'}:${contactKey(match)}` } : f))
  }, [event, contactOptions])

  if (!open || !form) return null
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    if (!form.starts_at) { toast.error('Pick a date and time for the event'); return }
    const { directory_contact_id, crm_person_id } = decodeContactKey(form.contactSel)
    const payload = {
      event_type: form.event_type,
      starts_at: localInputToIso(form.starts_at),
      title: form.title.trim() || null,
      location: form.location.trim() || null,
      body: form.body.trim() || null,
      owner_user_id: form.owner_user_id || null,
      first_alert: form.first_alert || null,
      second_alert: form.second_alert || null,
    }
    if (isEdit) {
      payload.directory_contact_id = directory_contact_id
      payload.crm_person_id = crm_person_id
    } else {
      payload.deal_id = dealId || null
      payload.directory_contact_id = directory_contact_id
      payload.crm_person_id = crm_person_id
    }
    setSaving(true)
    try {
      if (isEdit) await api.salesWorkspaceUpdateEvent(event.id, payload)
      else await api.salesWorkspaceCreateEvent(payload)
      onSaved()
      onClose()
    } catch (err) { toast.error(err.message || 'Could not save event') } finally { setSaving(false) }
  }

  return (
    <Modal open={open} onClose={onClose} wide title={isEdit ? 'Edit event' : 'New event'}>
      <form onSubmit={submit} className="space-y-3">
        <Field label="Club (optional)" hint={isEdit ? "Fixed once created — delete and recreate to move it to a different club." : 'Only clubs already in your queue.'}>
          {isEdit ? (
            <TextInput value={event.marketing_club_name || 'No club linked'} disabled readOnly />
          ) : (
            <Select value={dealId} onChange={e => { setDealId(e.target.value); setForm(f => ({ ...f, contactSel: '' })) }}>
              <option value="">No club</option>
              {dealOptions.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </Select>
          )}
        </Field>
        <div className="flex flex-wrap gap-3">
          <Field label="Event type" width="150px">
            <Select value={form.event_type} onChange={set('event_type')}>
              {EVENT_TYPE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          </Field>
          <Field label="Date & time" width="210px">
            <DateTimePicker value={form.starts_at} onChange={(v) => setForm(f => ({ ...f, starts_at: v }))} required />
          </Field>
          <Field label="Title (optional)" width="230px">
            <TextInput value={form.title} onChange={set('title')} placeholder="e.g. Intro demo call" />
          </Field>
          <Field label="Location (optional)" width="200px">
            <TextInput value={form.location} onChange={set('location')} placeholder="e.g. Zoom / clubrooms" />
          </Field>
        </div>
        <div className="flex flex-wrap gap-3">
          <Field label="Owner (assigned to)" width="200px">
            <Select value={form.owner_user_id} onChange={set('owner_user_id')}>
              <option value="">Me</option>
              {staffOptions.map(o => <option key={o.id} value={o.id}>{o.display_name || o.username}</option>)}
            </Select>
          </Field>
          <Field label="Club contact (optional)" width="220px">
            <Select value={form.contactSel} onChange={set('contactSel')}
              disabled={!(isEdit ? event.marketing_club_id : dealId) || contactOptions.length === 0}>
              <option value="">{contactOptions.length === 0 ? 'No contacts available' : 'None'}</option>
              {contactOptions.map(c => (
                <option key={contactKey(c)} value={`${c.directory_contact_id ? 'd' : 'c'}:${contactKey(c)}`}>
                  {c.full_name}{c.role ? ` (${c.role})` : ''}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div className="flex flex-wrap gap-3">
          <Field label="First alert (optional)" width="200px">
            <Select value={form.first_alert} onChange={set('first_alert')}>
              {ALERT_OPTIONS.map(o => <option key={o.value || 'none'} value={o.value}>{o.label}</option>)}
            </Select>
          </Field>
          <Field label="Second alert (optional)" width="200px">
            <Select value={form.second_alert} onChange={set('second_alert')}>
              {ALERT_OPTIONS.map(o => <option key={o.value || 'none'} value={o.value}>{o.label}</option>)}
            </Select>
          </Field>
        </div>
        <Field label="Note (optional)">
          <TextArea value={form.body} onChange={set('body')} placeholder="Anything to remember for this event…" style={{ minHeight: '80px' }} />
        </Field>
        <div className="flex items-center gap-2">
          <Btn type="submit" variant="primary" sm disabled={saving}>{isEdit ? 'Save changes' : 'Create event'}</Btn>
          <Btn type="button" variant="ghost" sm onClick={onClose} disabled={saving}>Cancel</Btn>
        </div>
      </form>
    </Modal>
  )
}

export default function SalesEventsView({ dealOptions, staffOptions, ownerOptions }) {
  const toast = useToast()
  const [allEvents, setAllEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [view, setView] = useState('calendar')
  const [calMode, setCalMode] = useState('month')
  const [cursor, setCursor] = useState(() => new Date())

  const owners = useMemo(() => ownerOptions || [], [ownerOptions])
  const [q, setQ] = useState('')
  const [clubId, setClubId] = useState('')
  const [ownerIds, setOwnerIds] = useState([])
  const [date, setDate] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const [modalOpen, setModalOpen] = useState(false)
  const [editEvent, setEditEvent] = useState(null)
  const [modalDefaultDate, setModalDefaultDate] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    api.salesWorkspaceListEvents()
      .then(r => setAllEvents(r.events || []))
      .catch(e => toast.error(e.message || 'Could not load events'))
      .finally(() => setLoading(false))
  }, [toast])
  useEffect(() => { load() }, [load])

  const clubOptions = useMemo(() => {
    const m = new Map()
    for (const e of allEvents) if (e.marketing_club_id) m.set(e.marketing_club_id, e.marketing_club_name || e.marketing_club_id)
    return [...m.entries()].map(([id, name]) => ({ id, name })).sort((a, b) => (a.name || '').localeCompare(b.name || ''))
  }, [allEvents])

  const baseFiltered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return allEvents.filter(e => {
      if (clubId && e.marketing_club_id !== clubId) return false
      if (!ownerMatches(ownerIds, owners, e.owner_user_id)) return false
      if (needle) {
        const hay = [e.title, e.marketing_club_name, e.deal_title, e.contact_name, e.body].filter(Boolean).join(' ').toLowerCase()
        if (!hay.includes(needle)) return false
      }
      return true
    })
  }, [allEvents, q, clubId, ownerIds, owners])

  const listEvents = useMemo(() => baseFiltered.filter(e => {
    const d = new Date(e.starts_at)
    if (date) { const day = new Date(date); if (!sameDay(d, day)) return false }
    if (dateFrom && d < startOfDay(new Date(dateFrom))) return false
    if (dateTo && d > endOfDay(new Date(dateTo))) return false
    return true
  }), [baseFiltered, date, dateFrom, dateTo])

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
    try { await api.salesWorkspaceDeleteEvent(ev.id); load() }
    catch (e) { toast.error(e.message || 'Could not delete event') }
  }

  const pill = (active) => `px-2.5 py-1 rounded-full text-[11.5px] border transition ${
    active ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent' : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`

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

      <div className="pb-card px-3 py-3 flex flex-wrap gap-3 items-end">
        <Field label="Search (title, club)" width="220px">
          <TextInput value={q} onChange={e => setQ(e.target.value)} placeholder="Search events…" />
        </Field>
        <Field label="Club" width="190px">
          <Select value={clubId} onChange={e => setClubId(e.target.value)}>
            <option value="">All clubs</option>
            {clubOptions.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
        </Field>
        {owners.length > 0 && (
          <Field label="Responsible" width="170px" composite>
            <MultiSelect value={ownerIds} onChange={setOwnerIds} allLabel="Anyone"
              groups={ownerFilterGroups(owners)} />
          </Field>
        )}
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
        {(q || clubId || ownerIds.length > 0 || date || dateFrom || dateTo) && (
          <Btn variant="ghost" sm onClick={() => { setQ(''); setClubId(''); setOwnerIds([]); setDate(''); setDateFrom(''); setDateTo('') }}>
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

      <SalesEventModal open={modalOpen} onClose={() => setModalOpen(false)} dealOptions={dealOptions} staffOptions={staffOptions}
        event={editEvent} seed={seedEvent} onSaved={load} />
    </div>
  )
}
