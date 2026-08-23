import { useState, useEffect, useCallback, useMemo } from 'react'
import QRCode from 'qrcode'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import BetterClubManagerLayout from '../../components/admin/BetterClubManagerLayout'
import { INPUT_CLS, Modal as UiModal } from '../../components/admin/ui'
import { PbSpinner } from '../../lib/presskit'
import Calendar from '../../components/admin/clubmanager/Calendar'
import DateTimePicker from '../../components/admin/crm/DateTimePicker'
import { PersonPicker } from '../../components/admin/clubmanager/pickers'

// One input look for the whole module — the same class the shared kit's
// TextInput/Select wear, so a hand-built control here matches a kit one.
const inp = INPUT_CLS
const EVENT_COLOR = '#8b7cf6'
const REGISTRATION_STATUSES = ['free', 'awaiting_payment', 'paid', 'cancelled']
const label = (s) => (s || '').split('_').map(w => w[0].toUpperCase() + w.slice(1)).join(' ')
const money = (cents) => `$${((cents || 0) / 100).toFixed(2)}`

const pill = (active) => `px-2.5 py-1 rounded-full text-[11.5px] border transition ${
  active ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent' : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`

const startOfDay = (d) => { const x = new Date(d); x.setHours(0, 0, 0, 0); return x }
const endOfDay = (d) => { const x = new Date(d); x.setHours(23, 59, 59, 999); return x }
const pad = (n) => String(n).padStart(2, '0')
const isoToLocal = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d)) return ''
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
const fmtTime = (iso) => new Date(iso).toLocaleTimeString('en-AU', { hour: 'numeric', minute: '2-digit' })
const fmtDateTime = (iso) => new Date(iso).toLocaleString('en-AU', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' })

// ─── modal shell ─────────────────────────────────────────────────────────────
// The house dialog, kept behind this screen's original `open`/`wide` props so
// every call site below is unchanged.
function Modal({ open, onClose, title, children, wide }) {
  return (
    <UiModal open={open} onClose={onClose} title={title} width={wide ? 760 : 600}>
      <div className="pb-4">{children}</div>
    </UiModal>
  )
}

// ─── registrations (public link + QR + list) — preserved feature ─────────────
function RegistrationRow({ reg, onChanged }) {
  const toast = useToast()
  async function setStatus(status) {
    try { await api.eventUpdateRegistration(reg.event_id, reg.id, { payment_status: status }); onChanged() } catch (e) { toast.error(e.message) }
  }
  async function remove() {
    if (!confirm(`Remove ${reg.full_name}'s registration?`)) return
    try { await api.eventDeleteRegistration(reg.event_id, reg.id); onChanged() } catch (e) { toast.error(e.message) }
  }
  return (
    <div className="flex items-center justify-between gap-2 bg-pb-surface2/40 border pb-hairline rounded px-3 py-2">
      <div>
        <div className="text-pb-text text-sm">{reg.full_name} {reg.quantity > 1 ? `×${reg.quantity}` : ''}</div>
        <div className="font-mono text-[10px] text-pb-faint">{reg.email || reg.phone || '—'}{reg.amount_cents > 0 ? ` · ${money(reg.amount_cents)}` : ''}</div>
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        <select className="bg-pb-surface2 text-pb-text text-[10px] font-mono border pb-hairline rounded px-1 py-1" value={reg.payment_status} onChange={e => setStatus(e.target.value)}>
          {REGISTRATION_STATUSES.map(s => <option key={s} value={s}>{label(s)}</option>)}
        </select>
        <button onClick={remove} className="pb-btn pb-btn-sm pb-btn-danger">✕</button>
      </div>
    </div>
  )
}

function NewRegistrationForm({ eventId, onAdded }) {
  const toast = useToast()
  const [form, setForm] = useState({ full_name: '', email: '', phone: '', quantity: 1 })
  const [busy, setBusy] = useState(false)
  async function submit() {
    if (!form.full_name.trim()) return
    setBusy(true)
    try {
      await api.eventCreateRegistration(eventId, form)
      setForm({ full_name: '', email: '', phone: '', quantity: 1 })
      onAdded()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  return (
    <div className="flex flex-wrap gap-2 mt-2">
      <input className={`${inp} flex-1 min-w-[120px]`} placeholder="Name" value={form.full_name} onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} />
      <input className={`${inp} w-40`} placeholder="Email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
      <input type="number" min="1" className={`${inp} w-20`} value={form.quantity} onChange={e => setForm(f => ({ ...f, quantity: Number(e.target.value) || 1 }))} />
      <button onClick={submit} disabled={busy || !form.full_name.trim()} className="pb-btn pb-btn-sm pb-btn-secondary">
        + Add (manual RSVP)
      </button>
    </div>
  )
}

function RegistrationsPanel({ event }) {
  const toast = useToast()
  const [regs, setRegs] = useState(null)
  const [registeredCount, setRegisteredCount] = useState(0)
  const [qr, setQr] = useState(null)
  const publicUrl = `${window.location.origin}/events/${event.id}`

  const loadRegs = useCallback(() => {
    api.eventListRegistrations(event.id).then(d => {
      setRegs(d.registrations || [])
      setRegisteredCount(d.registered_count || 0)
    }).catch(e => toast.error(e.message))
  }, [event.id, toast])

  useEffect(() => { loadRegs() }, [loadRegs])

  useEffect(() => {
    let alive = true
    QRCode.toDataURL(publicUrl, { margin: 1, width: 200, errorCorrectionLevel: 'M' })
      .then(u => { if (alive) setQr(u) }).catch(() => { if (alive) setQr(null) })
    return () => { alive = false }
  }, [publicUrl])

  function copyLink() {
    navigator.clipboard.writeText(publicUrl).then(() => toast.success('Link copied'))
  }

  return (
    <div className="border-t pb-hairline-t mt-4 pt-4 space-y-3">
      <div className="flex flex-wrap items-start gap-4">
        <div className="flex-1 min-w-[200px]">
          <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">PUBLIC REGISTRATION LINK</div>
          <div className="flex items-center gap-2">
            <input readOnly className={`${inp} text-[11px]`} value={publicUrl} onClick={e => e.target.select()} />
            <button onClick={copyLink} className="pb-btn pb-btn-sm pb-btn-secondary">Copy</button>
          </div>
          {!event.registration_open && <div className="font-mono text-[10px] text-pb-amber mt-1">Registration closed. The link won't accept new registrations.</div>}
        </div>
        {qr && <img src={qr} alt="QR code" className="w-24 h-24 rounded bg-white p-1" />}
      </div>

      <div>
        <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">
          REGISTRATIONS {event.capacity != null ? `(${registeredCount}/${event.capacity})` : `(${registeredCount})`}
        </div>
        {regs === null ? <PbSpinner message="Loading…" /> : (
          <div className="space-y-1.5">
            {regs.length === 0 && <div className="font-mono text-[10px] text-pb-faintest">No registrations yet.</div>}
            {regs.map(r => <RegistrationRow key={r.id} reg={{ ...r, event_id: event.id }} onChanged={loadRegs} />)}
          </div>
        )}
        <NewRegistrationForm eventId={event.id} onAdded={loadRegs} />
      </div>
    </div>
  )
}

// ─── event create/edit form ──────────────────────────────────────────────────
function EventForm({ event, seedDate, types, members, onSaved, onClose }) {
  const toast = useToast()
  const isEdit = !!event?.id
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState(() => {
    if (event) return {
      title: event.title || '',
      event_type_id: event.event_type_id || '',
      organiser_member_id: event.organiser_member_id || null,
      organiser_name: event.organiser_name || null,
      starts_at: isoToLocal(event.starts_at),
      ends_at: isoToLocal(event.ends_at),
      location: event.location || '',
      description: event.description || '',
      is_ticketed: !!event.is_ticketed,
      ticket_price: event.ticket_price_cents ? (event.ticket_price_cents / 100).toString() : '',
      capacity: event.capacity != null ? String(event.capacity) : '',
      registration_deadline: isoToLocal(event.registration_deadline),
      registration_open: event.registration_open !== false,
    }
    const start = seedDate ? (() => { const d = new Date(seedDate); d.setHours(9, 0, 0, 0); return isoToLocal(d.toISOString()) })() : ''
    return {
      title: '', event_type_id: '', organiser_member_id: null, organiser_name: null,
      starts_at: start, ends_at: '', location: '', description: '',
      is_ticketed: false, ticket_price: '', capacity: '', registration_deadline: '', registration_open: true,
    }
  })
  const set = (patch) => setForm(f => ({ ...f, ...patch }))

  async function submit() {
    if (!form.title.trim() || !form.starts_at) return
    setBusy(true)
    try {
      const payload = {
        title: form.title.trim(),
        event_type_id: form.event_type_id || null,
        organiser_member_id: form.organiser_member_id || null,
        organiser_name: form.organiser_member_id ? null : (form.organiser_name || null),
        starts_at: new Date(form.starts_at).toISOString(),
        ends_at: form.ends_at ? new Date(form.ends_at).toISOString() : null,
        location: form.location || null,
        description: form.description || null,
        is_ticketed: form.is_ticketed,
        ticket_price_cents: form.is_ticketed && form.ticket_price ? Math.round(Number(form.ticket_price) * 100) : 0,
        capacity: form.capacity ? Number(form.capacity) : null,
        registration_deadline: form.registration_deadline ? new Date(form.registration_deadline).toISOString() : null,
        registration_open: form.registration_open,
      }
      if (isEdit) await api.committeeUpdateEvent(event.id, payload)
      else await api.committeeCreateEvent(payload)
      toast.success(isEdit ? 'Event saved' : 'Event created')
      onSaved()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  const lbl = 'font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1 block'

  return (
    <div>
      <div className="space-y-3">
        <div>
          <label className={lbl}>TITLE</label>
          <input className={inp} placeholder="Event title" value={form.title} onChange={e => set({ title: e.target.value })} />
        </div>
        <div className="flex flex-wrap gap-3">
          <div className="flex-1 min-w-[180px]">
            <label className={lbl}>EVENT TYPE</label>
            <select className={inp} value={form.event_type_id} onChange={e => set({ event_type_id: e.target.value })}>
              <option value="">none</option>
              {types.map(t => <option key={t.id} value={t.id}>{t.name}{t.is_committee_only ? ' (committee)' : ''}</option>)}
            </select>
          </div>
          <div className="flex-1 min-w-[180px]">
            <label className={lbl}>ORGANISER</label>
            <PersonPicker members={members} memberId={form.organiser_member_id} name={form.organiser_name}
              onChange={({ member_id, name }) => set({ organiser_member_id: member_id, organiser_name: name })} />
          </div>
        </div>
        <div className="flex flex-wrap gap-3">
          <div className="flex-1 min-w-[200px]">
            <label className={lbl}>STARTS</label>
            <DateTimePicker value={form.starts_at} onChange={v => set({ starts_at: v })} required />
          </div>
          <div className="flex-1 min-w-[200px]">
            <label className={lbl}>ENDS (optional)</label>
            <DateTimePicker value={form.ends_at} onChange={v => set({ ends_at: v })} />
          </div>
        </div>
        <div>
          <label className={lbl}>LOCATION</label>
          <input className={inp} placeholder="Where is it?" value={form.location} onChange={e => set({ location: e.target.value })} />
        </div>
        <div>
          <label className={lbl}>DESCRIPTION</label>
          <textarea className={inp} rows={3} placeholder="Details (optional)" value={form.description} onChange={e => set({ description: e.target.value })} />
        </div>

        <div className="border-t pb-hairline-t pt-3">
          <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">TICKETING & REGISTRATION</div>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-1.5 font-mono text-[11px] text-pb-dim cursor-pointer select-none">
              <input type="checkbox" checked={form.is_ticketed} onChange={e => set({ is_ticketed: e.target.checked })} />
              Ticketed / priced
            </label>
            {form.is_ticketed && (
              <input type="number" min="0" step="0.01" className={`${inp} w-28`} placeholder="Price $" value={form.ticket_price}
                onChange={e => set({ ticket_price: e.target.value })} />
            )}
            <input type="number" min="0" className={`${inp} w-32`} placeholder="Capacity" value={form.capacity}
              onChange={e => set({ capacity: e.target.value })} />
            <label className="flex items-center gap-1.5 font-mono text-[11px] text-pb-dim cursor-pointer select-none">
              <input type="checkbox" checked={form.registration_open} onChange={e => set({ registration_open: e.target.checked })} />
              Registration open
            </label>
          </div>
          <div className="mt-3 max-w-xs">
            <label className={lbl}>REGISTRATION DEADLINE (optional)</label>
            <DateTimePicker value={form.registration_deadline} onChange={v => set({ registration_deadline: v })} />
          </div>
        </div>
      </div>

      <div className="flex justify-end gap-2 mt-5">
        <button onClick={onClose} className="pb-btn pb-btn-secondary">CANCEL</button>
        <button onClick={submit} disabled={busy || !form.title.trim() || !form.starts_at}
          className="pb-btn pb-btn-primary">
          {busy ? 'Saving…' : isEdit ? 'Save changes' : '+ Create event'}
        </button>
      </div>

      {isEdit && <RegistrationsPanel event={event} />}
    </div>
  )
}

// ─── Types management ────────────────────────────────────────────────────────
function TypeRow({ type, onChanged }) {
  const toast = useToast()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState({ name: type.name, description: type.description || '', is_committee_only: !!type.is_committee_only })
  const [busy, setBusy] = useState(false)

  async function save() {
    if (!draft.name.trim()) return
    setBusy(true)
    try {
      await api.eventUpdateType(type.id, { name: draft.name.trim(), description: draft.description || null, is_committee_only: draft.is_committee_only })
      setEditing(false); onChanged()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  async function remove() {
    if (!confirm(`Remove event type "${type.name}"?`)) return
    try { await api.eventArchiveType(type.id); onChanged() } catch (e) { toast.error(e.message) }
  }

  if (editing) return (
    <div className="pb-card p-3 space-y-2">
      <input className={inp} value={draft.name} onChange={e => setDraft(d => ({ ...d, name: e.target.value }))} placeholder="Name" />
      <input className={inp} value={draft.description} onChange={e => setDraft(d => ({ ...d, description: e.target.value }))} placeholder="Description" />
      <label className="flex items-center gap-1.5 font-mono text-[11px] text-pb-dim cursor-pointer select-none">
        <input type="checkbox" checked={draft.is_committee_only} onChange={e => setDraft(d => ({ ...d, is_committee_only: e.target.checked }))} />
        Committee-only
      </label>
      <div className="flex justify-end gap-2">
        <button onClick={() => setEditing(false)} className="pb-btn pb-btn-sm pb-btn-quiet">Cancel</button>
        <button onClick={save} disabled={busy || !draft.name.trim()} className="pb-btn pb-btn-sm pb-btn-primary">Save</button>
      </div>
    </div>
  )
  return (
    <div className="pb-card px-3 py-2 flex items-center justify-between gap-2">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-pb-text text-sm font-medium truncate">{type.name}</span>
          {type.is_committee_only && <span className="font-mono text-[9px] px-1.5 py-0.5 rounded-full bg-pb-accent/15 text-pb-accent">COMMITTEE</span>}
        </div>
        {type.description && <div className="font-mono text-[10px] text-pb-faint truncate">{type.description}</div>}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <button onClick={() => setEditing(true)} className="text-pb-faint hover:text-pb-accent text-[11px]">Edit</button>
        <button onClick={remove} className="text-pb-faint hover:text-pb-red text-[11px]">Remove</button>
      </div>
    </div>
  )
}

function TypesPanel({ types, onChanged }) {
  const toast = useToast()
  const [seeding, setSeeding] = useState(false)
  const [draft, setDraft] = useState({ name: '', description: '', is_committee_only: false })
  const [busy, setBusy] = useState(false)

  async function seed(committeeOnly) {
    setSeeding(true)
    try {
      const r = await api.eventSeedTypes(committeeOnly)
      toast.success(r.seeded > 0 ? `Added ${r.seeded} event ${r.seeded === 1 ? 'type' : 'types'}` : 'Already up to date')
      onChanged()
    } catch (e) { toast.error(e.message) } finally { setSeeding(false) }
  }
  async function add() {
    if (!draft.name.trim()) return
    setBusy(true)
    try {
      await api.eventCreateType({ name: draft.name.trim(), description: draft.description || null, is_committee_only: draft.is_committee_only })
      setDraft({ name: '', description: '', is_committee_only: false })
      toast.success('Event type added')
      onChanged()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  const general = types.filter(t => !t.is_committee_only)
  const committee = types.filter(t => t.is_committee_only)

  return (
    <div className="space-y-4">
      <div className="pb-card p-4">
        <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">STARTER SETS</div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => seed(false)} disabled={seeding}
            className="pb-btn pb-btn-secondary">
            + STARTER SET (11 TYPES)
          </button>
          <button onClick={() => seed(true)} disabled={seeding}
            className="pb-btn pb-btn-secondary">
            + COMMITTEE SET (8 TYPES)
          </button>
        </div>
      </div>

      <div className="pb-card p-4">
        <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">ADD AN EVENT TYPE</div>
        <div className="flex flex-wrap gap-2 items-center">
          <input className={`${inp} flex-1 min-w-[140px]`} placeholder="Name" value={draft.name} onChange={e => setDraft(d => ({ ...d, name: e.target.value }))} />
          <input className={`${inp} flex-1 min-w-[140px]`} placeholder="Description (optional)" value={draft.description} onChange={e => setDraft(d => ({ ...d, description: e.target.value }))} />
          <label className="flex items-center gap-1.5 font-mono text-[11px] text-pb-dim cursor-pointer select-none whitespace-nowrap">
            <input type="checkbox" checked={draft.is_committee_only} onChange={e => setDraft(d => ({ ...d, is_committee_only: e.target.checked }))} />
            Committee-only
          </label>
          <button onClick={add} disabled={busy || !draft.name.trim()}
            className="pb-btn pb-btn-primary">
            + ADD
          </button>
        </div>
      </div>

      {types.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">No event types yet. Seed a starter set or add one above.</div>
      ) : (
        <div className="space-y-4">
          {general.length > 0 && (
            <div>
              <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">GENERAL</div>
              <div className="space-y-1.5">{general.map(t => <TypeRow key={t.id} type={t} onChanged={onChanged} />)}</div>
            </div>
          )}
          {committee.length > 0 && (
            <div>
              <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">COMMITTEE-ONLY</div>
              <div className="space-y-1.5">{committee.map(t => <TypeRow key={t.id} type={t} onChanged={onChanged} />)}</div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── list row ────────────────────────────────────────────────────────────────
function ListRow({ ev, typeName, organiserLabel, onEdit, onDelete }) {
  return (
    <div className="pb-card px-4 py-3 flex items-center justify-between gap-3">
      <div className="min-w-0">
        <div className="text-pb-text font-semibold text-sm truncate">{ev.title}</div>
        <div className="font-mono text-[10px] text-pb-faint mt-0.5 flex flex-wrap gap-x-2">
          <span style={{ color: EVENT_COLOR }}>{fmtDateTime(ev.starts_at)}</span>
          {typeName(ev) && <span>· {typeName(ev)}</span>}
          {organiserLabel(ev) && <span>· {organiserLabel(ev)}</span>}
          {ev.location && <span>· 📍 {ev.location}</span>}
          {ev.is_ticketed && ev.ticket_price_cents > 0 && <span>· {money(ev.ticket_price_cents)}</span>}
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <button onClick={() => onEdit(ev)} className="text-pb-faint hover:text-pb-accent text-[11px]">Edit</button>
        <button onClick={() => onDelete(ev)} className="text-pb-faint hover:text-pb-red text-[11px]">Delete</button>
      </div>
    </div>
  )
}

// ─── page ────────────────────────────────────────────────────────────────────
export default function AdminEvents() {
  const toast = useToast()
  const [events, setEvents] = useState(null)
  const [types, setTypes] = useState([])
  const [members, setMembers] = useState([])

  const [screen, setScreen] = useState('events')   // events | types
  const [view, setView] = useState('calendar')      // calendar | list

  const [q, setQ] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [organiserFilter, setOrganiserFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const [modalOpen, setModalOpen] = useState(false)
  const [editEvent, setEditEvent] = useState(null)
  const [seedDate, setSeedDate] = useState(null)

  const loadEvents = useCallback(() => {
    api.committeeListEvents().then(d => setEvents(d.events || [])).catch(e => toast.error(e.message))
  }, [toast])
  const loadTypes = useCallback(() => {
    api.eventListTypes().then(d => setTypes(d.types || [])).catch(e => toast.error(e.message))
  }, [toast])

  useEffect(() => {
    loadEvents(); loadTypes()
    api.feeAllMembers().then(d => setMembers(d.members || [])).catch(() => setMembers([]))
  }, [loadEvents, loadTypes])

  const memberName = useCallback((id) => {
    const m = members.find(x => x.member_id === id)
    return m ? m.full_name : null
  }, [members])

  const organiserLabel = useCallback((ev) => {
    if (ev.organiser_member_id) return memberName(ev.organiser_member_id) || ev.organiser_name || 'Member'
    return ev.organiser_name || ''
  }, [memberName])
  const organiserKey = useCallback((ev) => {
    if (ev.organiser_member_id) return `m:${ev.organiser_member_id}`
    if (ev.organiser_name) return `n:${ev.organiser_name}`
    return ''
  }, [])
  const typeName = useCallback((ev) => {
    if (ev.event_type_id) {
      const t = types.find(x => x.id === ev.event_type_id)
      if (t) return t.name
    }
    return ev.event_type ? label(ev.event_type) : ''
  }, [types])

  // Organiser filter options built from distinct organisers on events.
  const organiserOptions = useMemo(() => {
    const m = new Map()
    for (const e of (events || [])) {
      const k = organiserKey(e)
      if (k && !m.has(k)) m.set(k, organiserLabel(e))
    }
    return [...m.entries()].map(([key, lbl]) => ({ key, label: lbl })).sort((a, b) => (a.label || '').localeCompare(b.label || ''))
  }, [events, organiserKey, organiserLabel])

  // Shared field filters (search / type / organiser). Date range is list-only.
  const baseFiltered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return (events || []).filter(e => {
      if (typeFilter && (e.event_type_id || '') !== typeFilter) return false
      if (organiserFilter && organiserKey(e) !== organiserFilter) return false
      if (needle && !(e.title || '').toLowerCase().includes(needle)) return false
      return true
    })
  }, [events, q, typeFilter, organiserFilter, organiserKey])

  const listEvents = useMemo(() => {
    return baseFiltered.filter(e => {
      const d = new Date(e.starts_at)
      if (dateFrom && d < startOfDay(new Date(dateFrom))) return false
      if (dateTo && d > endOfDay(new Date(dateTo))) return false
      return true
    }).sort((a, b) => new Date(a.starts_at) - new Date(b.starts_at))
  }, [baseFiltered, dateFrom, dateTo])

  const openCreate = () => { setEditEvent(null); setSeedDate(null); setModalOpen(true) }
  const openCreateOnDay = (day) => { setEditEvent(null); setSeedDate(day); setModalOpen(true) }
  const openEdit = (ev) => { setEditEvent(ev); setSeedDate(null); setModalOpen(true) }
  const remove = async (ev) => {
    if (!confirm(`Delete event "${ev.title}"?`)) return
    try { await api.committeeDeleteEvent(ev.id); loadEvents() } catch (e) { toast.error(e.message) }
  }

  const renderChip = (ev, { compact }) => (
    <div className="rounded px-1.5 py-0.5 leading-tight" style={{ background: 'rgba(139,124,246,0.14)', color: EVENT_COLOR }}>
      <div className="text-[10px] font-medium truncate">{ev.title}</div>
      {!compact && typeName(ev) && <div className="text-[9.5px] truncate opacity-90">{typeName(ev)}</div>}
      <div className="text-[9.5px] truncate opacity-75">{fmtTime(ev.starts_at)}{organiserLabel(ev) ? ` · ${organiserLabel(ev)}` : ''}</div>
    </div>
  )

  if (events === null) return <BetterClubManagerLayout title="Events" caption="Events, sign-ups and ticketing"><PbSpinner message="Loading events…" /></BetterClubManagerLayout>

  const anyFilter = q || typeFilter || organiserFilter || dateFrom || dateTo

  return (
    <BetterClubManagerLayout title="Events" caption="Events, sign-ups and ticketing">
      <div className="max-w-5xl">

        {/* Top bar */}
        <div className="flex items-center justify-between flex-wrap gap-2 mb-4">
          <div className="flex items-center gap-2">
            <button onClick={() => { setScreen('events'); setView('calendar') }} className={pill(screen === 'events' && view === 'calendar')}>Calendar</button>
            <button onClick={() => { setScreen('events'); setView('list') }} className={pill(screen === 'events' && view === 'list')}>List</button>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setScreen('types')} className={pill(screen === 'types')}>Types</button>
            <button onClick={openCreate}
              className="pb-btn pb-btn-primary">
              + NEW EVENT
            </button>
          </div>
        </div>

        {screen === 'types' ? (
          <TypesPanel types={types} onChanged={loadTypes} />
        ) : (
          <>
            {/* Filters */}
            <div className="pb-card p-3 flex flex-wrap gap-3 items-end mb-4">
              <div>
                <label className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1 block">SEARCH TITLE</label>
                <input className={`${inp} w-52`} placeholder="Search events…" value={q} onChange={e => setQ(e.target.value)} />
              </div>
              <div>
                <label className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1 block">EVENT TYPE</label>
                <select className={`${inp} w-48`} value={typeFilter} onChange={e => setTypeFilter(e.target.value)}>
                  <option value="">All types</option>
                  {types.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </div>
              <div>
                <label className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1 block">ORGANISER</label>
                <select className={`${inp} w-48`} value={organiserFilter} onChange={e => setOrganiserFilter(e.target.value)}>
                  <option value="">Anyone</option>
                  {organiserOptions.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
                </select>
              </div>
              {view === 'list' && (
                <>
                  <div>
                    <label className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1 block">FROM</label>
                    <input type="date" className={`${inp} w-40`} value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
                  </div>
                  <div>
                    <label className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1 block">TO</label>
                    <input type="date" className={`${inp} w-40`} value={dateTo} onChange={e => setDateTo(e.target.value)} />
                  </div>
                </>
              )}
              {anyFilter && (
                <button onClick={() => { setQ(''); setTypeFilter(''); setOrganiserFilter(''); setDateFrom(''); setDateTo('') }}
                  className="pb-btn pb-btn-sm pb-btn-quiet">Clear filters</button>
              )}
            </div>

            {view === 'calendar' ? (
              <Calendar items={baseFiltered} getStart={e => e.starts_at} getEnd={e => e.ends_at}
                renderChip={renderChip} onItemClick={openEdit} onDayAdd={openCreateOnDay} accent={EVENT_COLOR} />
            ) : (
              <div className="space-y-2">
                {listEvents.length === 0 ? (
                  <div className="pb-card p-6 text-center text-pb-dim text-sm">No events match.</div>
                ) : listEvents.map(ev => (
                  <ListRow key={ev.id} ev={ev} typeName={typeName} organiserLabel={organiserLabel} onEdit={openEdit} onDelete={remove} />
                ))}
              </div>
            )}
          </>
        )}
      </div>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} wide title={editEvent ? 'Edit event' : 'New event'}>
        <EventForm key={editEvent?.id || (seedDate ? `seed-${seedDate}` : 'new')}
          event={editEvent} seedDate={seedDate} types={types} members={members}
          onSaved={() => { loadEvents(); setModalOpen(false) }} onClose={() => setModalOpen(false)} />
      </Modal>
    </BetterClubManagerLayout>
  )
}
