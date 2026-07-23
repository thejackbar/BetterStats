import { useState, useEffect, useCallback } from 'react'
import QRCode from 'qrcode'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import AdminLayout from '../../components/admin/AdminLayout'
import { PbSpinner } from '../../lib/presskit'

const inp = 'w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
const EVENT_TYPES = ['committee_meeting', 'working_bee', 'registration_day', 'agm', 'awards_night', 'sponsor_function', 'fundraising', 'other']
const REGISTRATION_STATUSES = ['free', 'awaiting_payment', 'paid', 'cancelled']
const label = (s) => s.split('_').map(w => w[0].toUpperCase() + w.slice(1)).join(' ')
const money = (cents) => `$${((cents || 0) / 100).toFixed(2)}`

function NewEventForm({ onCreated }) {
  const toast = useToast()
  const [form, setForm] = useState({
    title: '', event_type: 'other', starts_at: '', location: '', description: '',
    is_ticketed: false, ticket_price: '', capacity: '', registration_deadline: '', registration_open: true,
  })
  const [busy, setBusy] = useState(false)

  async function submit() {
    if (!form.title.trim() || !form.starts_at) return
    setBusy(true)
    try {
      await api.committeeCreateEvent({
        title: form.title, event_type: form.event_type, location: form.location || null, description: form.description || null,
        starts_at: new Date(form.starts_at).toISOString(),
        is_ticketed: form.is_ticketed,
        ticket_price_cents: form.is_ticketed && form.ticket_price ? Math.round(Number(form.ticket_price) * 100) : 0,
        capacity: form.capacity ? Number(form.capacity) : null,
        registration_deadline: form.registration_deadline ? new Date(form.registration_deadline).toISOString() : null,
        registration_open: form.registration_open,
      })
      setForm({ title: '', event_type: 'other', starts_at: '', location: '', description: '', is_ticketed: false, ticket_price: '', capacity: '', registration_deadline: '', registration_open: true })
      onCreated()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="pb-card p-4 mb-4">
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">NEW EVENT</div>
      <div className="flex flex-wrap gap-2 mb-2">
        <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Title" value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
        <select className={`${inp} w-48`} value={form.event_type} onChange={e => setForm(f => ({ ...f, event_type: e.target.value }))}>
          {EVENT_TYPES.map(t => <option key={t} value={t}>{label(t)}</option>)}
        </select>
        <input type="datetime-local" className={`${inp} w-56`} value={form.starts_at} onChange={e => setForm(f => ({ ...f, starts_at: e.target.value }))} />
        <input className={`${inp} w-40`} placeholder="Location" value={form.location} onChange={e => setForm(f => ({ ...f, location: e.target.value }))} />
      </div>
      <textarea className={`${inp} mb-2`} placeholder="Description (optional)" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
      <div className="flex flex-wrap items-center gap-3 mb-1">
        <label className="flex items-center gap-1.5 font-mono text-[11px] text-pb-dim cursor-pointer select-none">
          <input type="checkbox" checked={form.is_ticketed} onChange={e => setForm(f => ({ ...f, is_ticketed: e.target.checked }))} />
          Ticketed / priced
        </label>
        {form.is_ticketed && (
          <input type="number" min="0" step="0.01" className={`${inp} w-28`} placeholder="Price $" value={form.ticket_price}
            onChange={e => setForm(f => ({ ...f, ticket_price: e.target.value }))} />
        )}
        <input type="number" min="0" className={`${inp} w-32`} placeholder="Capacity" value={form.capacity}
          onChange={e => setForm(f => ({ ...f, capacity: e.target.value }))} />
        <label className="font-mono text-[10px] text-pb-faintest">Reg. deadline</label>
        <input type="datetime-local" className={`${inp} w-56`} value={form.registration_deadline}
          onChange={e => setForm(f => ({ ...f, registration_deadline: e.target.value }))} />
      </div>
      <div className="flex justify-end mt-2">
        <button onClick={submit} disabled={busy || !form.title.trim() || !form.starts_at}
          className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
          {busy ? 'CREATING…' : '+ EVENT'}
        </button>
      </div>
    </div>
  )
}

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
        <button onClick={remove} className="font-mono text-[10px] text-pb-faintest hover:text-pb-red">✕</button>
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
      <button onClick={submit} disabled={busy || !form.full_name.trim()} className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text whitespace-nowrap">
        + Add (manual RSVP)
      </button>
    </div>
  )
}

function EventCard({ event, onChanged }) {
  const toast = useToast()
  const [expanded, setExpanded] = useState(false)
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

  useEffect(() => {
    if (expanded && regs === null) loadRegs()
  }, [expanded, regs, loadRegs])

  useEffect(() => {
    if (!expanded) { setQr(null); return }
    let alive = true
    QRCode.toDataURL(publicUrl, { margin: 1, width: 200, errorCorrectionLevel: 'M' })
      .then(u => { if (alive) setQr(u) }).catch(() => { if (alive) setQr(null) })
    return () => { alive = false }
  }, [expanded, publicUrl])

  async function remove() {
    if (!confirm(`Delete event "${event.title}"?`)) return
    try { await api.committeeDeleteEvent(event.id); onChanged() } catch (e) { toast.error(e.message) }
  }
  function copyLink() {
    navigator.clipboard.writeText(publicUrl).then(() => toast.success('Link copied'))
  }

  return (
    <div className="pb-card">
      <button onClick={() => setExpanded(x => !x)} className="w-full flex items-center justify-between px-4 py-3 hover:bg-pb-surface2 transition text-left">
        <div>
          <div className="text-pb-text font-semibold text-sm">{event.title}</div>
          <div className="font-mono text-[10px] text-pb-faint mt-0.5">
            {new Date(event.starts_at).toLocaleString()} · {label(event.event_type)}{event.location ? ` · ${event.location}` : ''}
            {event.is_ticketed && event.ticket_price_cents > 0 && ` · ${money(event.ticket_price_cents)}`}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {event.capacity != null && <span className="font-mono text-[9px] text-pb-faintest">{registeredCount || 0}/{event.capacity}</span>}
          <span onClick={(e) => { e.stopPropagation(); remove() }} className="font-mono text-[10px] text-pb-faintest hover:text-pb-red">✕</span>
          <span className="font-mono text-[9px] text-pb-faintest">{expanded ? '▾' : '▸'}</span>
        </div>
      </button>
      {expanded && (
        <div className="border-t pb-hairline-t px-4 py-3 space-y-3">
          <div className="flex flex-wrap items-start gap-4">
            <div className="flex-1 min-w-[200px]">
              <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">PUBLIC REGISTRATION LINK</div>
              <div className="flex items-center gap-2">
                <input readOnly className={`${inp} text-[11px]`} value={publicUrl} onClick={e => e.target.select()} />
                <button onClick={copyLink} className="px-2.5 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text whitespace-nowrap">Copy</button>
              </div>
              {!event.registration_open && <div className="font-mono text-[10px] text-pb-amber mt-1">Registration closed — the link won't accept new registrations.</div>}
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
      )}
    </div>
  )
}

export default function AdminEvents() {
  const toast = useToast()
  const [events, setEvents] = useState(null)

  const load = useCallback(() => {
    api.committeeListEvents().then(d => setEvents(d.events || [])).catch(e => toast.error(e.message))
  }, [toast])
  useEffect(() => { load() }, [load])

  if (events === null) return <AdminLayout><PbSpinner message="Loading events…" /></AdminLayout>
  return (
    <AdminLayout>
      <div className="max-w-4xl">
        <h1 className="font-display text-2xl font-bold text-pb-text mb-1">Events & Ticketing</h1>
        <p className="font-mono text-[11px] text-pb-faint mb-5">
          Working bees, fundraisers, sponsor functions — with registration, capacity and a QR-shareable public sign-up
          link. Priced events aren't charged online yet — a registration lands "awaiting payment" and the club follows
          up to reconcile it, the same way match fees are reconciled by hand.
        </p>
        <NewEventForm onCreated={load} />
        {events.length === 0 ? (
          <div className="pb-card p-6 text-center text-pb-dim text-sm">No events yet — create one above.</div>
        ) : (
          <div className="space-y-2">
            {events.map(e => <EventCard key={e.id} event={e} onChanged={load} />)}
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
